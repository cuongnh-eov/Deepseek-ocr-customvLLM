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
from worker.model_init import llm, sampling_params 

# 9. Dịch vụ thông báo (RabbitMQ Publisher)
from app.services.publisher import send_finished_notification


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