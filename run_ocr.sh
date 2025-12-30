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
#!/usr/bin/env bash

# 1. Cấu hình GPU và Python Path
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "🧹 Đang dọn dẹp các tiến trình cũ (Uvicorn & Celery)..."
pkill -f uvicorn
pkill -f celery

echo "🐳 Đang kiểm tra và khởi động các dịch vụ Docker..."

# Hàm kiểm tra và chạy container (Tránh lỗi No such container)
run_service() {
    if [ ! "$(docker ps -a -q -f name=$1)" ]; then
        echo "  -> Đang tạo mới $1..."
        case $1 in
            "ocr-postgres")
                docker run -d --name ocr-postgres -p 5432:5432 -e POSTGRES_USER=ocr_cuong -e POSTGRES_PASSWORD=ocr_cuong -e POSTGRES_DB=ocr_cuong_db postgres
                ;;
            "ocr-rabbit")
                docker run -d --name ocr-rabbit -p 5672:5672 -p 15672:15672 rabbitmq:3-management
                ;;
            "ocr-redis")
                docker run -d --name ocr-redis -p 6379:6379 redis:alpine redis-server --requirepass infini_rag_flow
                ;;
        esac
    else
        echo "  -> Đang khởi động lại $1..."
        docker start $1
    fi
}

# Chạy lần lượt các dịch vụ
run_service "ocr-postgres"
run_service "ocr-rabbit"
run_service "ocr-redis"

# Khởi động thêm MinIO nếu cần (tên container của bạn là docker-minio-1)
docker start docker-minio-1 2>/dev/null

echo "⏳ Chờ 5 giây để các dịch vụ Docker sẵn sàng..."
sleep 5

# 2. Các biến môi trường
export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
export RABBIT_URL="amqp://guest:guest@localhost:5672//"
export REDIS_URL="redis://:infini_rag_flow@127.0.0.1:6379/0"

echo "🚀 Đang khởi chạy hệ thống OCR..."

# 3. Khởi chạy FastAPI (Chạy ngầm)
uvicorn app.main:app --host 0.0.0.0 --port 8001 &

# 4. Khởi chạy Celery Worker
# Chú ý: Đảm bảo đường dẫn app.core.celery_app là chính xác trong cấu trúc thư mục của bạn
celery -A app.core.celery_app worker --loglevel=info -P solo --concurrency=1