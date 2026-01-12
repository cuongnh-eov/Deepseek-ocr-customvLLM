from datetime import datetime, timezone  # Để tạo mốc thời gian updated_at
from sqlalchemy.orm import Session       # Để định nghĩa kiểu dữ liệu cho tham số db

# 1. Thư viện hệ thống & Python chuẩn
import os
import time
import re
import json as pyjson
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# 2. Thư viện bên thứ ba (Cần cài qua pip)
import torch
from sqlalchemy.orm import Session

# 3. Kết nối Core (Database, Models, Config)
from app.core.database import SessionLocal
from app.models.documents import OCRJob, JobStatus
from app.config import (
    PROMPT, OUTPUT_PATH, 
    MINIO_ENDPOINT, MINIO_BUCKET_NAME
)

# 4. Tiện ích GPU (Các hàm vừa tách sang app/utils/gpu_utils.py)
from app.utils.utils import get_gpu_info, reset_gpu_peak, read_gpu_peak_mb

# 5. Tiện ích xử lý văn bản (Hàm vừa tách sang app/utils/postprocess_md.py)
from app.utils.postprocess_md import extract_content

# 6. Tiện ích PDF & Post-process (Markdown, JSON, MinIO)
from app.utils.utils import pdf_to_images_high_quality
from app.utils.postprocess_md import process_ocr_output, upload_to_minio
from app.utils.postprocess_json import process_ocr_to_blocks

# 7. Logic xử lý AI (Inference)
from app.services.processor import preprocess_batch, generate_ocr

# 8. Khởi tạo Model (LLM)
# Lưu ý: Điều chỉnh path này tùy vào vị trí file model_init.py của bạn
from app.core.model_init import llm, sampling_params 

# 9. Dịch vụ thông báo (RabbitMQ Publisher)
from app.services.publisher import send_finished_notification


import fitz  # PyMuPDF để đọc PDF

def update_job(db: Session, job: OCRJob, **kwargs):
    """
    Helper cập nhật job + updated_at rồi commit.
    """
    for k, v in kwargs.items():
        # Nếu DB model không có field k thì bỏ qua (tránh crash khi bạn chưa migrate)
        if hasattr(job, k):
            setattr(job, k, v)
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
def process_one_job(job_id: str):
    db = SessionLocal()
    job = db.get(OCRJob, job_id)

    if not job:
        db.close()
        return

    gpu_name, gpu_total_mb = get_gpu_info()

    try:
        # 1. Khởi tạo và Update trạng thái RUNNING
        file_size = 0
        if os.path.exists(job.input_path):
            file_size = round(os.path.getsize(job.input_path) / (1024 * 1024), 2)

        update_job(db, job, status=JobStatus.RUNNING, gpu_name=gpu_name, gpu_total_mb=gpu_total_mb, file_size_mb=file_size)
        reset_gpu_peak()
        t0 = time.time()

        # 2. Thư mục output
        output_dir = os.path.join(OUTPUT_PATH, job_id)
        os.makedirs(output_dir, exist_ok=True)

        # 3. Chuẩn bị Batching (Ý tưởng của sếp: 20 trang/lần)
        temp_doc = fitz.open(job.input_path)
        total_pages = len(temp_doc)
        temp_doc.close()

        from app.config import CHUNK_SIZE
        all_json_blocks = [] # Để Merger gộp sau này
        full_raw_markdown = ""
        full_clean_markdown = ""
        
        t_pdf2img_total = 0
        t_preprocess_total = 0
        t_infer_total = 0

        # --- BẮT ĐẦU CHẠY CUỐN CHIẾU ---
        for i in range(0, total_pages, CHUNK_SIZE):
            start = i
            end = min(i + CHUNK_SIZE, total_pages)
            print(f"📦 Processing Batch: {start+1} -> {end}")

            # 3.1. PDF -> Images (Lazy Loading đúng 20 trang)
            t_p_start = time.time()
            # Lưu ý: Hàm pdf_to_images_high_quality cần được cập nhật start_page/end_page như đã hướng dẫn trước đó
            images_chunk = pdf_to_images_high_quality(job.input_path, start_page=start, end_page=end)
            t_pdf2img_total += (time.time() - t_p_start)

            # 4.1. Preprocess Batch
            t_pre_start = time.time()
            batch_inputs, processed_images = preprocess_batch(images_chunk, PROMPT)
            t_preprocess_total += (time.time() - t_pre_start)

            # 4.2. AI Inference
            t_inf_start = time.time()
            outputs = generate_ocr(llm, batch_inputs, sampling_params)
            t_infer_total += (time.time() - t_inf_start)

            # 5. HẬU XỬ LÝ CHO TỪNG BATCH
            
            # 5.1) Lấy bản RAW MARKDOWN
            for out in outputs:
                raw_text = out.outputs[0].text if hasattr(out, 'outputs') else str(out)
                full_raw_markdown += raw_text + "\n\n<--- Page Split --->\n\n"

            # 5.2) Lấy bản CLEAN MARKDOWN & Crop ảnh (Hàm của bạn sẽ crop ảnh vào output_dir/images)
            clean_chunk_md, _, _ = process_ocr_output(outputs, processed_images, out_path=output_dir)
            full_clean_markdown += clean_chunk_md + "\n"

            # 5.3) Thu thập blocks cho JSON Merger
            for page_offset, output in enumerate(outputs):
                raw_text = output.outputs[0].text if hasattr(output, 'outputs') else str(output)
                cleaned = extract_content(raw_text, job_id)
                # Tính page_idx chính xác: trang hiện tại trong batch + offset
                page_idx = start + page_offset
                blocks = process_ocr_to_blocks(cleaned, page_idx=page_idx)
                all_json_blocks.append(blocks)

            # GIẢI PHÓNG BỘ NHỚ SAU MỖI 20 TRANG
            del images_chunk
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # --- KẾT THÚC VÒNG LẶP: LƯU TỔNG HỢP ---
        t_post0 = time.time()

        # Lưu file Raw Markdown
        raw_md_path = os.path.join(output_dir, f"{job_id}_raw.md")
        with open(raw_md_path, "w", encoding="utf-8") as f:
            f.write(full_raw_markdown)

        # Lưu file Clean Markdown
        clean_md_path = os.path.join(output_dir, f"{job_id}.md")
        with open(clean_md_path, "w", encoding="utf-8") as f:
            f.write(full_clean_markdown)

        # JSON Merger: Đánh số trang liên tục + Fix image paths
        all_content_list = []
        for page_idx, blocks in enumerate(all_json_blocks):
            # Xử lý lại image paths cho mỗi block (blocks là list of dicts)
            processed_blocks = []
            for block in blocks:
                if block.get("type") == "image" and "img_path" in block:
                    # Fix image path từ ./job_id/images/X.jpg thành ocr-results/job_id/images/X.jpg
                    img_path = block["img_path"]
                    if img_path.startswith("./"):
                        img_path = img_path[2:]  # Loại bỏ "./"
                    block["img_path"] = f"ocr-results/{img_path}"
                processed_blocks.append(block)
            
            all_content_list.extend(processed_blocks)

        response_data = {
            "metadata": {
                "source_filename": job.filename,
                "total_pages": total_pages,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
            "content": all_content_list
        }

        json_path = os.path.join(output_dir, f"{job_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            pyjson.dump(response_data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # 6. Tải lên MinIO (Quét folder chứa: images/, .md, _raw.md, .json)
        print(f"🚀 Đang đẩy toàn bộ kết quả Job {job_id} lên MinIO...")
        upload_to_minio(output_dir, job_id)

        t_postprocess = time.time() - t_post0
        vram_peak_mb, vram_resv = read_gpu_peak_mb()

        # 7. Cập nhật thành công vào Database
        update_job(
            db, job,
            status=JobStatus.SUCCESS,
            num_pages=total_pages,
            processing_time=round(time.time() - t0, 3),
            vram_peak_mb=vram_peak_mb,
            t_pdf2img=round(t_pdf2img_total, 3),
            t_preprocess=round(t_preprocess_total, 3),
            t_infer=round(t_infer_total, 3),
            t_postprocess=round(t_postprocess, 3),
            result_path=f"{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{job_id}/{job_id}.md",
            minio_json_url=f"{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{job_id}/{job_id}.json"
        )
   #     
        # 8. Thông báo qua RabbitMQ
        try:
            send_finished_notification(job_id)
        except:
            pass

    except Exception as e:
        print(f"❌ Lỗi xử lý Job {job_id}: {str(e)}")
        vram_peak_mb, _ = read_gpu_peak_mb()
        update_job(db, job, status=JobStatus.FAILED, error=str(e), vram_peak_mb=vram_peak_mb)
    finally:
        if os.path.exists(job.input_path):
            os.remove(job.input_path)
        db.close()