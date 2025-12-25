import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, APIRouter
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db, Base, engine
from app.core.models import OCRJob, JobStatus
# from app.core.queue import publish_job
from app.core.config import UPLOAD_PATH, OUTPUT_PATH, MAX_UPLOAD_MB



os.makedirs(UPLOAD_PATH, exist_ok=True)
os.makedirs(OUTPUT_PATH, exist_ok=True)

# Khởi tạo Database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="EOV OCR Professional Service",
    description="Hệ thống OCR xử lý bất đồng bộ chuẩn REST API",
    version="1.0.0"
)

# Tạo Router với prefix theo yêu cầu của sếp
ocr_router = APIRouter(prefix="/api/v1/ocr", tags=["OCR Documents"])

def _safe_filename(name: str) -> str:
    return Path(name).name

# --- ENDPOINTS ---
@ocr_router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ định dạng PDF.")

    job_id = uuid.uuid4().hex
    
    try:
        data = await file.read()
        size_mb = round(len(data) / (1024 * 1024), 2)
        
        if size_mb > MAX_UPLOAD_MB:
            raise HTTPException(status_code=413, detail=f"File quá lớn. Giới hạn: {MAX_UPLOAD_MB}MB")
        
        clean_name = _safe_filename(file.filename)
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
        raise HTTPException(status_code=500, detail=f"Lỗi DB: {str(e)}")

    # Đẩy Job vào Celery - Dùng đúng đường dẫn module mới
    try:
        from app.tasks.tasks import process_ocr_document_task
        process_ocr_document_task.delay(job_id)
    except Exception as e:
        # Nếu đẩy vào RabbitMQ lỗi, cập nhật trạng thái job để user biết
        new_job.status = JobStatus.FAILED
        new_job.error = f"Queue Error: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail="Không thể đẩy job vào hàng đợi.")

    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED,
        "message": "Đã tiếp nhận."
    }


@ocr_router.get("/status/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    GET /api/v1/ocr/status/{job_id}
    Kiểm tra trạng thái xử lý và các chỉ số GPU (VRAM).
    """
    job = db.get(OCRJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã Job.")
    
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": {
            "num_pages": job.num_pages,
            "processing_time_sec": job.processing_time
        },
        "metrics": {
            "vram_peak_mb": job.vram_peak_mb,
            "gpu_name": job.gpu_name
        },
        "error": job.error
    }

@ocr_router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    """
    GET /api/v1/ocr/documents
    Liệt kê danh sách tất cả các tài liệu đã từng upload.
    """
    jobs = db.query(OCRJob).order_by(OCRJob.created_at.desc()).all()
    return jobs

@ocr_router.get("/documents/{id}")
def get_document_detail(id: str, db: Session = Depends(get_db)):
    """
    GET /api/v1/ocr/documents/{id}
    Lấy thông tin chi tiết và đường dẫn kết quả của một tài liệu.
    """
    job = db.get(OCRJob, id)
    if not job:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại.")
    return job

@ocr_router.delete("/documents/{id}")
def delete_document(id: str, db: Session = Depends(get_db)):
    """
    DELETE /api/v1/ocr/documents/{id}
    Xóa tài liệu khỏi hệ thống: Xóa DB + Xóa file kết quả + Xóa ảnh đã crop.
    """
    job = db.get(OCRJob, id)
    if not job:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại.")

    # 1. Xóa thư mục kết quả (chứa MD, JSON và thư mục images đã crop)
    if job.output_dir and os.path.exists(job.output_dir):
        shutil.rmtree(job.output_dir)
        print(f"--- Đã xóa thư mục output: {job.output_dir} ---")

    # 2. Xóa file PDF gốc nếu còn tồn tại trong uploads
    if job.input_path and os.path.exists(job.input_path):
        os.remove(job.input_path)

    # 3. Xóa bản ghi trong Database
    db.delete(job)
    db.commit()

    return {"message": f"Đã xóa hoàn toàn tài liệu và dữ liệu liên quan của ID: {id}"}

# --- Download Helpers ---
@ocr_router.get("/get-markdown/{id}")
def get_markdown(id: str, db: Session = Depends(get_db)):
    job = db.get(OCRJob, id)
    if not job or job.status != JobStatus.SUCCESS: 
        raise HTTPException(status_code=400, detail=f"Chưa có kết quả. Trạng thái hiện tại: {job.status if job else 'N/A'}")

    # Đường dẫn này phải khớp với cái bạn đã lưu ở Bước 1
    file_full_path = os.path.join(OUTPUT_PATH, id, f"{id}.md")

    if not os.path.exists(file_full_path):
        raise HTTPException(status_code=404, detail="File không tồn tại.")

    # Trả về phản hồi dạng 'attachment' để trình duyệt TỰ ĐỘNG TẢI
    return FileResponse(
        path=file_full_path, 
        filename=f"Ket_Qua_{id}.md", # Ép trình duyệt mở hộp thoại Save
        media_type="text/markdown"
    )

# Tích hợp Router vào App chính
app.include_router(ocr_router)

if __name__ == "__main__":
    import uvicorn
    # Chạy trên cổng 8001 theo sơ đồ flow
    uvicorn.run(app, host="0.0.0.0", port=8001)
