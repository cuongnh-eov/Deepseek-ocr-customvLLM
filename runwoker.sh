#!/usr/bin/env bash

# Đảm bảo các dịch vụ nền đã chạy
docker start ocr-postgres ocr-rabbit 2>/dev/null

export DATABASE_URL="postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db"
export RABBIT_URL="amqp://guest:guest@localhost:5672/"
export OUTPUT_PATH="./outputs"

# Tạo thư mục output nếu chưa có
mkdir -p ./outputs

echo "🛠️ Starting OCR Worker (GPU mode)..."
# Chạy worker
python -m worker.worker