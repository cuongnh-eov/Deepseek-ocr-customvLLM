# #!/usr/bin/env bash
# export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# echo "🧹 Đang dọn dẹp các tiến trình cũ..."
# pkill -f uvicorn
# pkill -f celery

# echo "🐳 Đang khởi động các dịch vụ Docker..."
# # Thêm ocr-redis vào danh sách start
# docker start ocr-postgres ocr-rabbit ocr-redis 2>/dev/null

# # Chờ 3 giây để Docker khởi động hẳn
# sleep 3

# # Các biến môi trường
# export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
# export RABBIT_URL="amqp://guest:guest@localhost:5672//"
# export REDIS_URL="redis://:infini_rag_flow@127.0.0.1:6379/0"

# echo "🚀 Khởi chạy API và Worker..."
# uvicorn app.main:app --host 0.0.0.0 --port 8001 &
# celery -A app.tasks worker --loglevel=info -P solo 
# # --concurrency=1


#!/usr/bin/env bash

# 1. Cấu hình GPU và Python Path
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# QUAN TRỌNG: Thêm thư mục hiện tại vào PYTHONPATH để các module app.xxx và worker.xxx có thể tìm thấy nhau
export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "🧹 Đang dọn dẹp các tiến trình cũ (Uvicorn & Celery)..."
pkill -f uvicorn
pkill -f celery

echo "🐳 Đang khởi động các dịch vụ Docker (Postgres, RabbitMQ, Redis)..."
docker start ocr-postgres ocr-rabbit ocr-redis 2>/dev/null

# Chờ 3 giây để các dịch vụ Docker sẵn sàng kết nối
sleep 3

# 2. Các biến môi trường (Nên để trong file .env nhưng khai báo ở đây cũng được)
export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
export RABBIT_URL="amqp://guest:guest@localhost:5672//"
export REDIS_URL="redis://:infini_rag_flow@127.0.0.1:6379/0"

echo "🚀 Đang khởi chạy hệ thống OCR..."

# 3. Khởi chạy FastAPI (Chạy ngầm với &)
# Chú ý: Trỏ vào app.api.main vì bạn đã dời main.py vào thư mục api
uvicorn app.api.main:app --host 0.0.0.0 --port 8001 &

# 4. Khởi chạy Celery Worker (Chạy foreground để xem log)
# Chú ý: Trỏ vào app.core.celery_app vì đối tượng Celery nằm ở đó
# Sử dụng -P solo và --concurrency=1 để tối ưu VRAM cho DeepSeek-OCR
celery -A app.core.celery_app worker --loglevel=info -P solo --concurrency=1