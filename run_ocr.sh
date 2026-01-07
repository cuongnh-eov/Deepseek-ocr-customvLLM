#!/usr/bin/env bash

# 1. Cấu hình GPU và Python Path
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "🧹 Đang dọn dẹp các tiến trình cũ (Uvicorn & Celery)..."
pkill -f uvicorn
pkill -f celery

echo "🐳 Đang kiểm tra và khởi động các dịch vụ Docker..."

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
            "ocr-minio")
                # Lệnh tạo mới MinIO chuẩn
                docker run -d --name ocr-minio \
                  -p 9000:9000 -p 9001:9001 \
                  -e "MINIO_ROOT_USER=rag_flow" \
                  -e "MINIO_ROOT_PASSWORD=infini_rag_flow" \
                  minio/minio server /data --console-address ":9001"
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
run_service "ocr-minio" # Đã thêm MinIO vào đây

echo "⏳ Chờ 10 giây để các dịch vụ Docker sẵn sàng..."
sleep 5

# 2. Các biến môi trường (Khớp với cấu hình Docker ở trên)
export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
export RABBIT_URL="amqp://guest:guest@localhost:5672//"
export REDIS_URL="redis://:infini_rag_flow@127.0.0.1:6379/0"
export MINIO_ENDPOINT="http://localhost:9000"

echo "🚀 Đang khởi chạy hệ thống OCR..."

# 3. Khởi chạy FastAPI (Chạy ngầm)
uvicorn app.main:app --host 0.0.0.0 --port 8001 &

# 4. Khởi chạy Celery Worker
celery -A app.core.celery_app worker --loglevel=info -P solo --concurrency=1