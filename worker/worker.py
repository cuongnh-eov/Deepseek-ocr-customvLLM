"""
worker/worker.py
================
Vai trò: chạy OCR "nặng" (GPU) theo message từ RabbitMQ.
Luồng:
1) Consume message {"job_id": "..."} từ queue.
2) Load job từ DB -> lấy input_path.
3) Update DB: status=RUNNING + (gpu_name, gpu_total_mb).
4) Reset peak VRAM stats -> chạy pipeline.
5) Save outputs (md/json) -> update DB: SUCCESS + metrics.
6) Nếu lỗi -> update DB: FAILED + error + (VRAM peak nếu đọc được).
Ghi metrics:
- processing_time: tổng thời gian job
- t_pdf2img, t_preprocess, t_infer, t_postprocess: theo stage (nếu DB có cột)
- vram_peak_mb / vram_reserved_peak_mb: peak memory stats (torch.cuda)
"""
from datetime import datetime, timezone
import os
import time
import re
import torch
import json as pyjson
from pathlib import Path
from typing import Optional, Tuple
from sqlalchemy.orm import Session

# --- Import từ Core ---
from app.core.db import SessionLocal
from app.core.models import OCRJob, JobStatus
from app.core.config import (
    PROMPT, OUTPUT_PATH, 
    MINIO_ENDPOINT, MINIO_BUCKET_NAME
)

# --- Import từ Services & Utils ---
# Lưu ý: Kiểm tra chính xác processor.py nằm ở đâu (Tree của bạn ghi services)
from app.services.processor import preprocess_batch, generate_ocr, run_tesseract_fallback
from app.services.publisher import send_finished_notification

from app.utils.utils import pdf_to_images_high_quality
from app.utils.postprocess_md import process_ocr_output, upload_to_minio
from app.utils.postprocess_json import process_ocr_to_blocks

# --- Import từ Worker (Cùng folder) ---
from worker.model_init import llm, sampling_params
def get_gpu_info() -> Tuple[Optional[str], Optional[int]]:
    """
    Lấy thông tin GPU đang dùng.
    Return: (gpu_name, total_mb) hoặc (None, None) nếu không có CUDA.
    """
    if not torch.cuda.is_available():
        return None, None
    idx = torch.cuda.current_device()
    name = torch.cuda.get_device_name(idx)
    total_mb = int(torch.cuda.get_device_properties(idx).total_memory / (1024 * 1024))
    return name, total_mb
def reset_gpu_peak():
    """
    Reset peak memory stats để đo "peak VRAM" chính xác cho từng job.
    """
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
def read_gpu_peak_mb() -> Tuple[Optional[int], Optional[int]]:
    """
    Read peak memory used during job.
    - allocated: memory do tensors allocate
    - reserved : memory cached by CUDA allocator
    """
    if not torch.cuda.is_available():
        return None, None
    peak_alloc = int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    peak_resv = int(torch.cuda.max_memory_reserved() / (1024 * 1024))
    return peak_alloc, peak_resv


def extract_content(text: str, job_id: str) -> str:
    """
    Làm sạch output raw của model theo logic bạn đang dùng:
    - bỏ end-of-sentence token
    - thay <|ref|>image... bằng markdown image placeholder
    - xoá các ref/det khác
    - chuẩn hoá ký hiệu latex
    """
    if "<｜end▁of▁sentence｜>" in text:
        text = text.replace("<｜end▁of▁sentence｜>", "")
    pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
    matches = re.findall(pattern, text, re.DOTALL)
    matches_image, matches_other = [], []
    for a_match in matches:
        if "<|ref|>image<|/ref|>" in a_match[0]:
            matches_image.append(a_match[0])
        else:
            matches_other.append(a_match[0])
    for img_idx, match in enumerate(matches_image):
        text = text.replace(match, f"![](./{job_id}/images/{img_idx}.jpg)\n")
    for match in matches_other:
        text = text.replace(match, "")
    text = text.replace("\\coloneqq", ":=").replace("\\eqqcolon", "=:")
    text = text.replace("\n\n\n\n", "\n\n").replace("\n\n\n", "\n\n")
    return text
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

        # 3. PDF -> Images
        t_pdf2img0 = time.time()
        images = pdf_to_images_high_quality(job.input_path)
        t_pdf2img = time.time() - t_pdf2img0
        total_pages = len(images)

        # 4. AI Inference
        t_pre0 = time.time()
        batch_inputs = preprocess_batch(images, PROMPT)
        t_preprocess = time.time() - t_pre0

        t_inf0 = time.time()
        outputs = generate_ocr(llm, batch_inputs, sampling_params)
        t_infer = time.time() - t_inf0

        # 5. HẬU XỬ LÝ (Sử dụng lại logic JSON ổn định của bạn)
        t_post0 = time.time()
        
        # 5.1) Tạo file Markdown
        # Lưu ý: Hàm này của bạn thường tự lưu vào output_dir
        markdown_text, _, _ = process_ocr_output(outputs, images, out_path=output_dir)
        markdown_path = os.path.join(output_dir, f"{job_id}.md")
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        # 5.2) Tạo file JSON (Sử dụng logic từ file cũ bạn gửi)
        content_pages = []
        for page_num, output in enumerate(outputs):
            # Lấy text raw từ output của vLLM
            raw_text = output.outputs[0].text if hasattr(output, 'outputs') else str(output)
            # Làm sạch bằng hàm extract_content có sẵn trong file này
            cleaned = extract_content(raw_text, job_id)
            # Chuyển đổi sang blocks
            blocks = process_ocr_to_blocks(cleaned)
            content_pages.append({"page_number": page_num + 1, "blocks": blocks})

        response_data = {
            "document": {
                "metadata": {
                    "source_filename": job.filename,
                    "total_pages": total_pages,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
                "content": content_pages,
            }
        }

        json_path = os.path.join(output_dir, f"{job_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            pyjson.dump(response_data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno()) # Đảm bảo file được ghi xuống đĩa trước khi upload

        # 6. Tải lên MinIO (Sử dụng hàm quét toàn bộ thư mục của bạn)
        print(f"🚀 Đang đẩy kết quả Job {job_id} lên MinIO...")
        upload_to_minio(output_dir, job_id)

        t_postprocess = time.time() - t_post0
        vram_peak_mb, vram_resv = read_gpu_peak_mb()

        # 7. Cập nhật thành công
        update_job(
            db, job,
            status=JobStatus.SUCCESS,
            num_pages=total_pages,
            processing_time=round(time.time() - t0, 3),
            vram_peak_mb=vram_peak_mb,
            t_pdf2img=round(t_pdf2img, 3),
            t_preprocess=round(t_preprocess, 3),
            t_infer=round(t_infer, 3),
            t_postprocess=round(t_postprocess, 3),
            result_path=f"{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{job_id}/{job_id}.md",
            minio_json_url=f"{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{job_id}/{job_id}.json"
        )
        
        # 8. Thông báo (Nếu bạn đã sửa lỗi vhost RabbitMQ)
        try:
            from app.publisher import send_finished_notification
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