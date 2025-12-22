"""
app/main.py (FastAPI)
=====================
Vai trò: "điều phối" (orchestration), KHÔNG chạy OCR nặng.
- POST /jobs:
    Nhận file PDF -> lưu vào uploads/ -> tạo job_id -> ghi DB -> push RabbitMQ -> trả job_id ngay.
- GET /jobs/{job_id}:
    Client poll để xem trạng thái và metrics (VRAM, timing, số trang... do Worker ghi vào DB).
- GET /jobs/{job_id}/result/markdown:
    Khi SUCCESS -> tải file .md
- GET /jobs/{job_id}/result/json:
    Khi SUCCESS -> tải file .json

Tại sao API không ghi VRAM?
- Vì VRAM tăng khi Worker chạy model, không phải khi API nhận file.
- API chỉ đọc metrics từ DB do Worker đã cập nhật.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db, Base, engine
from app.models import OCRJob, JobStatus
from app.queue import publish_job

# Đường dẫn mặc định (bạn có thể set qua ENV)
UPLOAD_PATH = os.getenv("UPLOAD_PATH", "./uploads")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "./outputs")

# Giới hạn dung lượng upload (tuỳ bạn, đơn vị MB)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

os.makedirs(UPLOAD_PATH, exist_ok=True)
os.makedirs(OUTPUT_PATH, exist_ok=True)
Base.metadata.create_all(bind=engine)
app = FastAPI(title="Async OCR Service", version="2.1.0")


def _safe_filename(name: str) -> str:
    """
    Tránh các ký tự path traversal; giữ đơn giản.
    """
    return Path(name).name


@app.post("/jobs")
async def submit_job(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Nhận PDF, lưu file, tạo job và đẩy sang queue.
    Trả job_id ngay, không chờ OCR.
    """

    # 1) Validate loại file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF is supported")

    # 2) Validate kích thước (cách đơn giản: đọc toàn bộ vào memory -> check)
    #    Nếu file rất lớn, bạn có thể chuyển sang stream chunk.
    data = await file.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"File too large (> {MAX_UPLOAD_MB} MB)")

    # 3) Tạo job_id
    job_id = uuid.uuid4().hex

    # 4) Lưu file vào uploads/
    clean_name = _safe_filename(file.filename)
    saved_pdf = f"{UPLOAD_PATH}/{job_id}_{clean_name}"
    with open(saved_pdf, "wb") as f:
        f.write(data)

    # 5) Ghi DB trạng thái QUEUED
    job = OCRJob(
        job_id=job_id,
        filename=clean_name,
        input_path=saved_pdf,
        status=JobStatus.QUEUED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        # bạn có thể lưu size_mb vào DB nếu đã tạo cột; nếu chưa thì bỏ
    )
    db.add(job)
    db.commit()

    # 6) Push message sang RabbitMQ (Worker sẽ xử lý)
    publish_job({"job_id": job_id})

    return {"job_id": job_id, "status": job.status}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """
    Client poll endpoint này để xem:
    - status: QUEUED/RUNNING/SUCCESS/FAILED
    - metrics: num_pages, processing_time, VRAM peak/reserved peak, stage timing...
      (metrics do Worker ghi vào DB)
    """
    job = db.get(OCRJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Trả đầy đủ các field quan trọng. Tuỳ DB model của bạn có field nào thì bật field đó.
    return {
        "job_id": job.job_id,
        "status": job.status,
        "filename": job.filename,

        # Core metrics
        "num_pages": job.num_pages,
        "processing_time": job.processing_time,

        # GPU metrics (Worker ghi)
        "gpu_name": getattr(job, "gpu_name", None),
        "gpu_total_mb": getattr(job, "gpu_total_mb", None),
        "vram_peak_mb": getattr(job, "vram_peak_mb", None),
        "vram_reserved_peak_mb": getattr(job, "vram_reserved_peak_mb", None),

        # Per-stage timing (nếu bạn có cột trong DB)
        "t_pdf2img": getattr(job, "t_pdf2img", None),
        "t_preprocess": getattr(job, "t_preprocess", None),
        "t_infer": getattr(job, "t_infer", None),
        "t_postprocess": getattr(job, "t_postprocess", None),

        "error": job.error,

        # Output paths
        "output_dir": job.output_dir,
        "markdown_path": job.markdown_path,
        "json_path": job.json_path,

        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@app.get("/jobs/{job_id}/result/markdown")
def download_markdown(job_id: str, db: Session = Depends(get_db)):
    """
    Tải Markdown khi job SUCCESS.
    """
    job = db.get(OCRJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.SUCCESS or not job.markdown_path:
        raise HTTPException(status_code=400, detail="Result not ready")

    if not os.path.exists(job.markdown_path):
        raise HTTPException(status_code=404, detail="Markdown file missing on disk")

    return FileResponse(
        job.markdown_path,
        media_type="text/markdown",
        filename=Path(job.markdown_path).name,
    )


@app.get("/jobs/{job_id}/result/json")
def download_json(job_id: str, db: Session = Depends(get_db)):
    """
    Tải JSON khi job SUCCESS.
    """
    job = db.get(OCRJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.SUCCESS or not job.json_path:
        raise HTTPException(status_code=400, detail="Result not ready")

    if not os.path.exists(job.json_path):
        raise HTTPException(status_code=404, detail="JSON file missing on disk")

    return FileResponse(
        job.json_path,
        media_type="application/json",
        filename=Path(job.json_path).name,
    )
