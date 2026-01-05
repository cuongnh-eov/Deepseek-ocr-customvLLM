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

from minio.deleteobjects import DeleteObject
from minio import Minio # Giả sử bạn dùng thư viện minio
from app.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_NAME
# Khởi tạo client (nên để trong file config hoặc dependency)
endpoint = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")

minio_client = Minio(
    endpoint,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

@ocr_router.delete("/documents/{id}")
def delete_document(id: str, db: Session = Depends(get_db)):
    """
    Xóa tài liệu:
    1. Tìm trong DB.
    2. Xóa tất cả object trên MinIO có prefix là Job ID.
    3. Xóa thư mục/file cục bộ (nếu có).
    4. Xóa bản ghi trong DB.
    """
    # 1. Kiểm tra tồn tại trong Database
    job = db.query(OCRJob).filter(OCRJob.job_id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại trong Database.")

    # 2. XÓA TRÊN MINIO (Sử dụng MINIO_BUCKET_NAME đã import)
    try:
        # Prefix thường là ID của tài liệu/job
        prefix = f"{id}/"
        
        # Lấy danh sách tất cả file bên trong "thư mục" này
        objects_to_delete = minio_client.list_objects(
            MINIO_BUCKET_NAME, 
            prefix=prefix, 
            recursive=True
        )
        
        # Chuyển đổi danh sách để xóa hàng loạt
        delete_list = [DeleteObject(obj.object_name) for obj in objects_to_delete]
        
        if delete_list:
            # Lưu ý: remove_objects trả về một iterator, phải duyệt qua nó thì lệnh xóa mới thực thi
            errors = minio_client.remove_objects(MINIO_BUCKET_NAME, delete_list)
            for error in errors:
                print(f"❌ Lỗi khi xóa object {error.object_name} trên MinIO: {error}")
            print(f"✅ Đã xóa các tệp trên MinIO tại prefix: {prefix}")
        else:
            print(f"ℹ️ Không tìm thấy tệp nào trên MinIO với prefix: {prefix}")

    except Exception as e:
        print(f"❌ Lỗi kết nối hoặc xử lý MinIO: {str(e)}")

    # 3. XÓA TRÊN LOCAL STORAGE
    # Xóa thư mục output cục bộ
    if job.output_dir and os.path.exists(job.output_dir):
        try:
            shutil.rmtree(job.output_dir)
            print(f"✅ Đã xóa thư mục cục bộ: {job.output_dir}")
        except Exception as e:
            print(f"❌ Lỗi xóa output_dir: {e}")

    # Xóa file input cục bộ
    if job.input_path and os.path.exists(job.input_path):
        try:
            if os.path.isfile(job.input_path):
                os.remove(job.input_path)
                print(f"✅ Đã xóa file input cục bộ: {job.input_path}")
        except Exception as e:
            print(f"❌ Lỗi xóa input_path: {e}")

    # 4. XÓA TRONG DATABASE
    try:
        db.delete(job)
        db.commit()
        print(f"✅ Đã xóa bản ghi Job ID {id} trong DB.")
    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi Database: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi khi xóa dữ liệu trong Database.")

    return {
        "status": "success",
        "message": f"Dữ liệu của Job ID {id} đã được dọn dẹp sạch sẽ.",
        "details": {
            "minio_bucket": MINIO_BUCKET_NAME,
            "minio_prefix": f"{id}/"
        }
    }