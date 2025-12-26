import logging
import sys
import os
from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="tasks.process_ocr_document")
def process_ocr_document_task(self, job_id: str):
    """
    Task Celery để điều phối xử lý OCR.
    """
    try:
        # 1. Đảm bảo môi trường Python tìm thấy các module trong dự án
        project_root = os.getcwd()
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            
        # 2. Import logic xử lý thực tế
        from app.services.ocr_service import process_one_job
        
        logger.info(f"=== [CELERY START] Nhận Job ID: {job_id} ===")
        
        # 3. Cập nhật trạng thái Task (tùy chọn - giúp hiển thị trên dashboard)
        self.update_state(state='PROGRESS', meta={'job_id': job_id})
        
        # 4. Gọi "trái tim" của hệ thống xử lý
        result = process_one_job(job_id)
        
        logger.info(f"=== [CELERY SUCCESS] Hoàn thành Job ID: {job_id} ===")
        return f"SUCCESS: {result}"
        
    except Exception as exc:
        # Ghi log chi tiết lỗi bao gồm cả dòng lỗi trong worker.py
        logger.error(f"❌ [CELERY ERROR] Lỗi khi thực hiện Job {job_id}: {exc}", exc_info=True)
        # Thông báo cho Celery rằng task này đã thất bại
        return f"FAILED: {str(exc)}"