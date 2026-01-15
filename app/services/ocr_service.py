
import os
import time
import fitz  # PyMuPDF
import torch
import json as pyjson
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

# --- Core & Database ---
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.documents import OCRJob, JobStatus

# --- Config ---
from app.config import (
    PROMPT, OUTPUT_PATH, OCR_ENGINE,
    MINIO_ENDPOINT, MINIO_BUCKET_NAME, CHUNK_SIZE
)

# --- Factory ---
from app.core.factory import OCREngineFactory

# --- Utils ---
from app.utils.utils import (
    get_gpu_info, reset_gpu_peak, read_gpu_peak_mb, 
    pdf_to_images_high_quality
)
from app.utils.postprocess_md import extract_content, process_ocr_output, upload_to_minio
from app.utils.postprocess_json import process_ocr_to_blocks

# --- AI/Inference ---
from app.services.processor import preprocess_batch, generate_ocr
from app.core.model_init import llm, sampling_params
from app.services.publisher import send_finished_notification

# from app.services.ocr_service import get_db_session, update_job_status, cleanup_input, get_file_info, setup_output_dir, clear_gpu_cache, process_single_batch, save_final_results, upload_results_to_minio_and_get_urls 
# # =============================================================================
# PHẦN 1: HELPER FUNCTIONS (DB, FILE, GPU)
# =============================================================================

def get_db_session() -> Session:
    """Tạo session kết nối database."""
    return SessionLocal()

def update_job_status(db: Session, job: OCRJob, status: JobStatus, **kwargs) -> None:
    """
    Cập nhật trạng thái job và các thông số khác vào DB.
    Tự động cập nhật updated_at.
    """
    for key, value in kwargs.items():
        if hasattr(job, key):
            setattr(job, key, value)
    
    job.status = status
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()

def get_file_info(file_path: str) -> Tuple[float, int]:
    """Lấy kích thước file (MB) và số trang PDF."""
    file_size = 0.0
    page_count = 0
    
    if os.path.exists(file_path):
        file_size = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        try:
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
        except Exception as e:
            print(f"Lỗi đọc PDF count: {e}")
            
    return file_size, page_count

def setup_output_dir(job_id: str) -> str:
    """Tạo thư mục lưu kết quả nếu chưa tồn tại."""
    output_dir = os.path.join(OUTPUT_PATH, job_id)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def cleanup_input(file_path: str) -> None:
    """Xóa file input sau khi đã xử lý xong."""
    if os.path.exists(file_path):
        os.remove(file_path)

def clear_gpu_cache() -> None:
    """Giải phóng bộ nhớ GPU."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def detect_best_engine(file_path: str, ocr_engine_env: str = None) -> str:
    """
    Phát hiện engine tốt nhất dựa trên loại file.
    
    Logic:
    - PDF (>2MB): MinerU (tốc độ, accuracy cao)
    - PDF (<2MB): Deepseek (chi tiết, vLLM)
    - Image (PNG, JPG, etc): Deepseek (OCR fine-tuned)
    
    Args:
        file_path: Đường dẫn file
        ocr_engine_env: Engine từ .env (override nếu có)
        
    Returns:
        Engine name: "deepseek", "mineru", or "docling"
    """
    # Nếu .env đã set engine khác "auto", dùng engine đó
    if ocr_engine_env and ocr_engine_env.lower() not in ["auto", "none", ""]:
        return ocr_engine_env.lower()
    
    # Auto-detect
    file_ext = Path(file_path).suffix.lower()
    file_size_mb = 0
    
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except:
        pass
    
    # Chọn engine dựa trên file type
    if file_ext == ".pdf":
        # PDF lớn (>2MB): MinerU (fast, good summary)
        if file_size_mb > 2:
            return "mineru"
        # PDF nhỏ: Deepseek (detailed, fine-grained)
        else:
            return "deepseek"
    
    elif file_ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"]:
        # Image: Deepseek (OCR optimized)
        return "deepseek"
    
    else:
        # Unknown: Mặc định Deepseek
        return "deepseek"



# =============================================================================
# PHẦN 2: BATCH PROCESSING LOGIC (XỬ LÝ TỪNG LÔ)
# =============================================================================

def process_single_batch(
    pdf_path: str, 
    start_page: int, 
    end_page: int, 
    output_dir: str, 
    job_id: str
) -> Dict[str, Any]:
    """
    Xử lý một batch PDF (ví dụ: 20 trang).
    
    Returns:
        Dict chứa:
        - 'raw_md': Đoạn markdown thô của batch
        - 'clean_md': Đoạn markdown đã clean của batch
        - 'blocks': List các blocks JSON
        - 'timings': Dict thời gian xử lý (pdf2img, pre, infer)
    """
    # 1. PDF -> Images
    t_p_start = time.time()
    images_chunk = pdf_to_images_high_quality(pdf_path, start_page=start_page, end_page=end_page)
    t_pdf2img = time.time() - t_p_start

    # 2. Preprocess
    t_pre_start = time.time()
    batch_inputs, processed_images = preprocess_batch(images_chunk, PROMPT)
    t_preprocess = time.time() - t_pre_start

    # 3. Inference
    t_inf_start = time.time()
    outputs = generate_ocr(llm, batch_inputs, sampling_params)
    t_infer = time.time() - t_inf_start

    # 4. Xử lý Output (Post-process per batch)
    
    # 4.1 Raw Markdown
    raw_md_chunk = ""
    for out in outputs:
        text = out.outputs[0].text if hasattr(out, 'outputs') else str(out)
        raw_md_chunk += text + "\n\n"
    
    # 4.2 Clean Markdown & Crop Images
    # Hàm này sẽ tự crop ảnh lưu vào output_dir/images
    clean_md_chunk, _, _ = process_ocr_output(outputs, processed_images, out_path=output_dir)

    # 4.3 JSON Blocks
    batch_blocks = []
    for page_offset, output in enumerate(outputs):
        raw_text = output.outputs[0].text if hasattr(output, 'outputs') else str(output)
        cleaned = extract_content(raw_text, job_id)
        page_idx = start_page + page_offset
        
        blocks = process_ocr_to_blocks(cleaned, page_idx=page_idx)
        batch_blocks.extend(blocks) # blocks ở đây đã là list flat

    return {
        "raw_md": raw_md_chunk,
        "clean_md": clean_md_chunk,
        "blocks": batch_blocks,
        "timings": {
            "pdf2img": t_pdf2img,
            "preprocess": t_preprocess,
            "infer": t_infer
        }
    }


# =============================================================================
# PHẦN 3: RESULT BUILDER & STORAGE (TỔNG HỢP & LƯU TRỮ)
# =============================================================================

def save_final_results(
    output_dir: str, 
    job_id: str, 
    raw_md_full: str, 
    clean_md_full: str, 
    all_blocks: List[Dict],
    filename: str,
    total_pages: int
) -> Dict[str, str]:
    """
    Lưu kết quả ra file (.md, .json) và trả về đường dẫn local.
    """
    # 1. Save Raw Markdown
    raw_md_path = os.path.join(output_dir, f"{job_id}_raw.md")
    with open(raw_md_path, "w", encoding="utf-8") as f:
        f.write(raw_md_full)

    # 2. Save Clean Markdown
    clean_md_path = os.path.join(output_dir, f"{job_id}.md")
    with open(clean_md_path, "w", encoding="utf-8") as f:
        f.write(clean_md_full)

    # 3. Prepare & Save JSON
    # Fix image paths trong blocks
    for block in all_blocks:
        if block.get("type") == "image" and "img_path" in block:
            img_path = block["img_path"]
            if img_path.startswith("./"):
                img_path = img_path[2:]
            # Đổi path relative thành path chuẩn cho MinIO/Web access
            block["img_path"] = f"ocr-results/{job_id}/{img_path}"

    response_data = {
        "metadata": {
            "source_filename": filename,
            "total_pages": total_pages,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
        "content": all_blocks
    }

    json_path = os.path.join(output_dir, f"{job_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        pyjson.dump(response_data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())

    return {
        "raw_md": raw_md_path,
        "clean_md": clean_md_path,
        "json": json_path
    }

def upload_results_to_minio_and_get_urls(output_dir: str, job_id: str) -> Dict[str, str]:
    """
    Upload folder lên MinIO và trả về public URLs.
    """
    print(f"🚀 Đang đẩy toàn bộ kết quả Job {job_id} lên MinIO...")
    upload_to_minio(output_dir, job_id)
    
    base_url = f"{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{job_id}"
    return {
        "markdown": f"{base_url}/{job_id}.md",
        "json": f"{base_url}/{job_id}.json"
    }


# =============================================================================
# PHẦN 4: MAIN CONTROLLER (HÀM CHÍNH)
# =============================================================================

def process_one_job(job_id: str):
    """
    Hàm chính để xử lý một OCR Job từ đầu đến cuối.
    Hỗ trợ Deepseek hoặc Docling engine.
    """
    db = get_db_session()
    job = db.get(OCRJob, job_id)

    if not job:
        print(f"⚠️ Không tìm thấy Job {job_id}")
        db.close()
        return
    
    # --- 0. CHỌN ENGINE ---
    # Auto-detect best engine based on file type, or use OCR_ENGINE from env
    best_engine = detect_best_engine(job.input_path, OCR_ENGINE)
    
    engine = OCREngineFactory.get_engine(best_engine)
    is_deepseek_mode = OCREngineFactory.is_deepseek(best_engine)
    is_mineru_mode = OCREngineFactory.is_mineru(best_engine)
    is_docling_mode = OCREngineFactory.is_docling(best_engine)
    fallback_engine = OCREngineFactory.get_fallback_engine()  # Docling fallback
    
    print(f"🔧 Sử dụng OCR Engine chính: {best_engine.upper()}")
    print(f"   (File: {os.path.basename(job.input_path)}, Size: {os.path.getsize(job.input_path)/(1024*1024):.2f}MB)")
    print(f"📌 Fallback engine: DOCLING")
    
    # --- 1. KHỞI TẠO ---
    try:
        file_size_mb, total_pages = get_file_info(job.input_path)
        output_dir = setup_output_dir(job_id)
        
        # Lấy thông tin GPU (nếu Deepseek)
        gpu_name, gpu_total_mb = get_gpu_info() if is_deepseek_mode else ("N/A", 0)
        
        # Update DB: RUNNING
        update_job_status(
            db, job, JobStatus.RUNNING, 
            gpu_name=gpu_name, 
            gpu_total_mb=gpu_total_mb, 
            file_size_mb=file_size_mb
        )
        
        if is_deepseek_mode:
            reset_gpu_peak()
        
        t0 = time.time()

        # Biến tích hợp dữ liệu
        full_raw_md = ""
        full_clean_md = ""
        all_json_blocks = []
        
        # Biến tích hợp thời gian
        total_t_pdf2img = 0.0
        total_t_preprocess = 0.0
        total_t_infer = 0.0

        # --- 2. XỬ LÝ THEO ENGINE ---
        print(f"🚀 Bắt đầu xử lý Job {job_id} ({total_pages} trang) với {OCR_ENGINE.upper()}...")
        
        elif is_mineru_mode:
            # Mode MinerU: Gọi MinerU engine để parse PDF
            try:
                print(f"📦 Gọi MinerU engine...")
                all_json_blocks = engine.parse(job.input_path, output_dir)
                print(f"✅ MinerU hoàn tất. Số blocks: {len(all_json_blocks)}")
            except Exception as e:
                print(f"⚠️  MinerU lỗi: {e}")
                print(f"🔄 Fallback sang Docling...")
                try:
                    fallback_engine_docling = OCREngineFactory.get_engine("docling")
                    all_json_blocks = fallback_engine_docling.parse(job.input_path, output_dir)
                    print(f"✅ Docling (fallback) hoàn tất. Số blocks: {len(all_json_blocks)}")
                except Exception as fallback_error:
                    print(f"❌ Fallback Docling cũng lỗi: {fallback_error}")
                    raise fallback_error
        
        elif is_deepseek_mode:
            # Mode Deepseek: Xử lý batch-by-batch với vLLM
            try:
                for i in range(0, total_pages, CHUNK_SIZE):
                    start = i
                    end = min(i + CHUNK_SIZE, total_pages)
                    print(f"📦 Processing Batch: {start+1} -> {end}")

                    # Gọi hàm xử lý batch
                    result = process_single_batch(
                        pdf_path=job.input_path,
                        start_page=start,
                        end_page=end,
                        output_dir=output_dir,
                        job_id=job_id
                    )

                    # Gộp kết quả
                    full_raw_md += result['raw_md'] + "<--- Page Split --->\n\n"
                    full_clean_md += result['clean_md']
                    all_json_blocks.extend(result['blocks'])

                    # Cộng dọn thời gian
                    total_t_pdf2img += result['timings']['pdf2img']
                    total_t_preprocess += result['timings']['preprocess']
                    total_t_infer += result['timings']['infer']

                    # Dọn dẹp bộ nhớ GPU sau mỗi batch
                    clear_gpu_cache()
                    
                print(f"✅ Deepseek hoàn tất. Số blocks: {len(all_json_blocks)}")
                
            except Exception as e:
                print(f"⚠️  Deepseek lỗi: {e}")
                print(f"🔄 Fallback sang Docling...")
                try:
                    fallback_engine_docling = OCREngineFactory.get_engine("docling")
                    all_json_blocks = fallback_engine_docling.parse(job.input_path, output_dir)
                    print(f"✅ Docling (fallback) hoàn tất. Số blocks: {len(all_json_blocks)}")
                except Exception as fallback_error:
                    print(f"❌ Fallback Docling cũng lỗi: {fallback_error}")
                    raise fallback_error

        # --- 3. HẬU XỬ LÝ & LƯU FILE ---
        t_post_start = time.time()
        
        saved_paths = save_final_results(
            output_dir=output_dir,
            job_id=job_id,
            raw_md_full=full_raw_md,
            clean_md_full=full_clean_md,
            all_blocks=all_json_blocks,
            filename=job.filename,
            total_pages=total_pages
        )
        
        t_postprocess = time.time() - t_post_start

        # --- 4. UPLOAD MINIO ---
        minio_urls = upload_results_to_minio_and_get_urls(output_dir, job_id)

        # --- 5. CẬP NHẬT THÀNH CÔNG ---
        vram_peak_mb = 0
        if is_deepseek_mode:
            vram_peak_mb, _ = read_gpu_peak_mb()
        
        total_time = time.time() - t0

        update_job_status(
            db, job, JobStatus.SUCCESS,
            num_pages=total_pages,
            processing_time=round(total_time, 3),
            vram_peak_mb=vram_peak_mb,
            t_pdf2img=round(total_t_pdf2img, 3),
            t_preprocess=round(total_t_preprocess, 3),
            t_infer=round(total_t_infer, 3),
            t_postprocess=round(t_postprocess, 3),
            result_path=minio_urls['markdown'],
            minio_json_url=minio_urls['json']
        )

        # --- 6. GỬI THÔNG BÁO ---
        try:
            send_finished_notification(job_id)
        except Exception as e:
            print(f"⚠️ Lỗi gửi notification: {e}")

        print(f"✅ Job {job_id} hoàn tất trong {round(total_time, 2)}s")

    except Exception as e:
        print(f"❌ Lỗi xử lý Job {job_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        vram_peak_mb, _ = read_gpu_peak_mb()
        update_job_status(
            db, job, JobStatus.FAILED, 
            error=str(e), 
            vram_peak_mb=vram_peak_mb
        )
    
    finally:
        # Dọn dẹp file input tạm
        cleanup_input(job.input_path)
        db.close()