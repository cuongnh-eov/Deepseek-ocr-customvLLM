#!/usr/bin/env bash

# Tự động bật Docker containers nếu chúng đang tắt
echo "Checking Docker services..."
docker start ocr-postgres ocr-rabbit 2>/dev/null

export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
export RABBIT_URL="amqp://guest:guest@localhost:5672/"
export UPLOAD_PATH="./uploads"

# Tạo thư mục upload nếu chưa có
mkdir -p ./uploads

echo "🚀 Starting FastAPI on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000