import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# --- IMPORT SCHEMAS ---
from app.schemas.schemas import (
    OCRResponse, 
    DocumentResponseSchema
)

from app.core.database import get_db
from app.models.documents import OCRJob, JobStatus
from app.config import UPLOAD_PATH, OUTPUT_PATH, MAX_UPLOAD_MB

ocr_router = APIRouter(prefix="/api/v1/ocr", tags=["OCR Documents"])

def _safe_filename(name: str) -> str:
    return Path(name).name

# --- ENDPOINTS ---

@ocr_router.post("/upload", response_model=OCRResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Tiếp nhận file và đẩy vào hàng đợi.
    Sử dụng OCRResponse để validate đầu ra.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ định dạng PDF.")

    job_id = uuid.uuid4().hex
    
    try:
        data = await file.read()
        size_mb = round(len(data) / (1024 * 1024), 2)
        
        if size_mb > MAX_UPLOAD_MB:
            raise HTTPException(status_code=413, detail=f"File quá lớn. Giới hạn: {MAX_UPLOAD_MB}MB")
        
        clean_name = _safe_filename(file.filename)

        # Đảm bảo thư mục tồn tại trước khi ghi
        os.makedirs(UPLOAD_PATH, exist_ok=True)
        saved_pdf_path = os.path.join(UPLOAD_PATH, f"{job_id}_{clean_name}")
        
        with open(saved_pdf_path, "wb") as f:
            f.write(data)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu file: {str(e)}")

    try:
        new_job = OCRJob(
            job_id=job_id,
            filename=clean_name,
            input_path=saved_pdf_path,
            file_size_mb=size_mb,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_job)
        db.commit()
    except Exception as e:
        if os.path.exists(saved_pdf_path):
            os.remove(saved_pdf_path)
        raise HTTPException(status_code=500, detail=f"Lỗi Database: {str(e)}")

    try:
        from app.tasks.tasks import process_ocr_document_task
        process_ocr_document_task.delay(job_id)
    except Exception as e:
        new_job.status = JobStatus.FAILED
        new_job.error = f"Queue Error: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail="Không thể đẩy job vào hàng đợi.")

    # Trả về khớp với Schema OCRResponse
    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED,
        "message": "Tài liệu đã được tiếp nhận thành công."
    }


@ocr_router.get("/result/{job_id}", response_model=DocumentResponseSchema)
def get_full_result(job_id: str, db: Session = Depends(get_db)):
    """
    Endpoint mới: Trả về kết quả OCR chi tiết dưới dạng Structured JSON 
    Dựa trên bộ Schema phức tạp bạn đã viết.
    """
    job = db.query(OCRJob).filter(OCRJob.job_id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã Job.")
    
    # Nếu job thành công, FastAPI sẽ tự động map dữ liệu từ DB (job) 
    # vào DocumentResponseSchema nhờ cấu hình from_attributes = True
    return job


@ocr_router.get("/status/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Kiểm tra trạng thái xử lý đơn giản"""
    job = db.query(OCRJob).filter(OCRJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã Job.")
    
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": {
            "num_pages": job.num_pages,
            "processing_time_sec": job.processing_time
        },
        "error": job.error
    }


@ocr_router.delete("/documents/{id}")
def delete_document(id: str, db: Session = Depends(get_db)):
    """Xóa tài liệu và dữ liệu liên quan"""
    job = db.query(OCRJob).filter(OCRJob.job_id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại.")

    if job.output_dir and os.path.exists(job.output_dir):
        shutil.rmtree(job.output_dir)

    if job.input_path and os.path.exists(job.input_path):
        os.remove(job.input_path)

    db.delete(job)
    db.commit()

    return {"message": f"Đã xóa hoàn toàn dữ liệu của Job ID: {id}"}