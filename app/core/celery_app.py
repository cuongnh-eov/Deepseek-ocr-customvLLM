from celery import Celery
from app.config import RABBIT_URL, REDIS_URL

#
celery_app = Celery(
    "ocr_system",
    broker=RABBIT_URL,
    backend=REDIS_URL,
    # QUAN TRỌNG: Trỏ chính xác vào module tasks theo cấu trúc mới
    include=['app.tasks.tasks'] 
)

# Cấu hình tối ưu cho DeepSeek-OCR và tránh lỗi kết nối
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,

    # --- CHỐNG LỖI MẤT KẾT NỐI (OSError: Server unexpectedly closed connection) ---
    broker_heartbeat=0,                   # Tắt heartbeat để không bị ngắt khi GPU đang bận
    broker_connection_timeout=60,         # Tăng thời gian chờ kết nối
    event_queue_expires=60,               # Thời gian hết hạn của event queue
    worker_prefetch_multiplier=1,         # Mỗi worker chỉ nhận 1 task mỗi lần
    
    # --- ĐỊNH NGHĨA QUEUE ---
    task_default_queue='celery',          # Đảm bảo trùng khớp với routing_key trong log lỗi của bạn
    
    # --- CẤU HÌNH CẢNH BÁO ---
    worker_cancel_long_running_tasks_on_connection_loss=True,
)