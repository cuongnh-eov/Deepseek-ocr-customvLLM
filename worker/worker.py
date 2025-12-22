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
import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import pika
import torch
import json as pyjson
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import OCRJob, JobStatus

# ===== Reuse pipeline bạn đang có =====
from configs.config import PROMPT  # prompt OCR
from app.utils import pdf_to_images_high_quality
from app.processor import preprocess_batch, generate_ocr
from app.model_init import llm, sampling_params
from app.postprocess_md import process_ocr_output
from app.postprocess_json import process_ocr_to_blocks
from app.postprocess_md import upload_to_minio

from configs.config import RABBIT_URL, QUEUE_NAME, OUTPUT_PATH

from app.postprocess_md import upload_to_minio


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
    """
    Xử lý 1 job theo job_id: PDF -> Images -> AI -> Crop -> MD -> Cleanup
    """
    db = SessionLocal()
    job = db.get(OCRJob, job_id)

    if not job:
        db.close()
        return

    gpu_name, gpu_total_mb = get_gpu_info()

    try:
        # 1. Update trạng thái đang chạy
        # Lấy file size để ghi metrics
        file_size = 0
        if os.path.exists(job.input_path):
            file_size = round(os.path.getsize(job.input_path) / (1024 * 1024), 2)

        update_job(
            db, job,
            status=JobStatus.RUNNING,
            error=None,
            gpu_name=gpu_name,
            gpu_total_mb=gpu_total_mb,
            file_size_mb=file_size
        )

        reset_gpu_peak()
        t0 = time.time()

        # 2. Tạo thư mục output
        output_dir = os.path.join(OUTPUT_PATH, job_id)
        os.makedirs(output_dir, exist_ok=True)

        # 3. PDF -> Images
        t_pdf2img0 = time.time()
        images = pdf_to_images_high_quality(job.input_path)
        t_pdf2img = time.time() - t_pdf2img0
        total_pages = len(images)

        # 4. AI Inference (Preprocess + Model)
        t_pre0 = time.time()
        batch_inputs = preprocess_batch(images, PROMPT)
        t_preprocess = time.time() - t_pre0

        t_inf0 = time.time()
        outputs = generate_ocr(llm, batch_inputs, sampling_params)
        t_infer = time.time() - t_inf0

        # 5. Hậu xử lý (Post-process)
        t_post0 = time.time()
        
        # --- QUAN TRỌNG ---
        # Hàm này sẽ tự CROP ảnh nhỏ và TỰ LƯU file Markdown vào output_dir
        markdown_text, _, _ = process_ocr_output(outputs, images, out_path=output_dir)
        
        # Xác định đường dẫn file MD (tên file gốc + .md)
      # worker.py
        markdown_path = os.path.join(output_dir, f"{job_id}.md")
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        
        # 5.2) Tạo JSON blocks cấu trúc
        content_pages = []
        for page_num, output in enumerate(outputs):
            # Sử dụng nội dung đã sạch từ hàm extract_content
            cleaned = extract_content(output.outputs[0].text, job_id)
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

        # BƯỚC MỚI: ĐẨY LÊN MINIO TỪ WORKER
        # =======================================================
        print(f"🚀 Đang đẩy kết quả Job {job_id} lên MinIO...")
        try:
            # upload_dir chính là output_dir chứa cả md, json và images
            upload_to_minio(output_dir, job_id)
            print(f"✅ Đã tải lên MinIO thành công.")
        except Exception as minio_err:
            print(f"⚠️ Lỗi Upload MinIO nhưng vẫn tiếp tục: {minio_err}")

        # =======================================================
        t_postprocess = time.time() - t_post0
        processing_time = time.time() - t0
        vram_peak_mb, vram_reserved_peak_mb = read_gpu_peak_mb()

        # 6. Cập nhật DB thành công
        update_job(
            db, job,
            status=JobStatus.SUCCESS,
            num_pages=total_pages,
            processing_time=round(processing_time, 3),
            vram_peak_mb=vram_peak_mb,
            vram_reserved_peak_mb=vram_reserved_peak_mb,
            t_pdf2img=round(t_pdf2img, 3),
            t_preprocess=round(t_preprocess, 3),
            t_infer=round(t_infer, 3),
            t_postprocess=round(t_postprocess, 3),
            output_dir=output_dir,
            markdown_path=markdown_path,
            json_path=json_path,
        )

        # --- DỌN DẸP FILE TẠM ---
        # Sau khi SUCCESS, xóa file PDF gốc trong uploads để tiết kiệm ổ cứng
        if os.path.exists(job.input_path):
            os.remove(job.input_path)
            print(f"✅ Đã dọn dẹp file PDF gốc: {job.input_path}")

    except Exception as e:
        print(f"❌ Lỗi xử lý Job {job_id}: {str(e)}")
        vram_peak_mb, vram_reserved_peak_mb = read_gpu_peak_mb()
        update_job(
            db, job,
            status=JobStatus.FAILED,
            error=str(e),
            vram_peak_mb=vram_peak_mb,
            vram_reserved_peak_mb=vram_reserved_peak_mb,
        )
    finally:
        db.close()

def main():
    """
    Worker loop:
    - prefetch_count=1 => mỗi worker xử 1 job tại 1 thời điểm.
      RẤT quan trọng nếu bạn chạy 1 GPU nhỏ (RTX 3060) để tránh nhiều job ăn VRAM cùng lúc.
    - ack sau khi xử lý xong -> nếu worker chết giữa chừng thì RabbitMQ có thể requeue message.
    """
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()

    # durable queue: queue không mất khi restart (tuỳ cấu hình persistence RabbitMQ)
    ch.queue_declare(queue=QUEUE_NAME, durable=True)

    # Mỗi worker chỉ nhận 1 job tại 1 thời điểm
    ch.basic_qos(prefetch_count=1)

    def callback(ch, method, properties, body):
        msg = json.loads(body.decode("utf-8"))
        job_id = msg.get("job_id")
        if not job_id:
            # message lỗi format -> ack và bỏ
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        process_one_job(job_id)

        # ACK sau khi làm xong
        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    print(f"✅ Worker listening: queue={QUEUE_NAME}")
    ch.start_consuming()


if __name__ == "__main__":
    main()
