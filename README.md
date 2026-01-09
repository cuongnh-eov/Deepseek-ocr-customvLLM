# 🚀 DeepSeek OCR System

Hệ thống OCR phân tán, chuyển đổi PDF/ảnh sang Markdown bằng DeepSeek-OCR + vLLM.

## 🎯 Tính năng

- **AI-Powered OCR**: DeepSeek-OCR với vLLM optimization (~760 tokens/s)
- **Distributed Processing**: Celery + RabbitMQ + MinIO
- **Async Jobs**: FastAPI + Celery worker pattern
- **GPU Optimized**: CUDA 11.8, Flash-Attention, KV Cache
- **LaTeX Support**: Nhận diện công thức toán học
- **Layout Aware**: Duy trì cấu trúc tài liệu

## 🏗 Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Celery |
| AI/ML | DeepSeek-OCR, vLLM, PyTorch, CUDA 11.8 |
| Queue | RabbitMQ, Redis |
| Storage | MinIO, PostgreSQL |
| DevOps | Docker, Docker Compose |

## 📦 Quick Start

### Docker (Recommended)

```bash
# 1. Chuẩn bị .env
cp .env.example .env
# Edit .env với giá trị của bạn

# 2. Start infrastructure
docker-compose -f docker-compose.infra.yml up -d

# 3. Start services
docker-compose -f docker-compose.services.yml up -d

# 4. Check status
docker ps
docker logs -f ocr-worker
```

### Local Development

```bash
# Setup
conda create -n ocr python=3.12 -y
conda activate ocr

# Install PyTorch
pip install torch==2.6.0+cu118 torchvision==0.21.0+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# Install vLLM wheel
pip install ./wheels/vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl

# Install deps
pip install -r requirements.txt

# Run
chmod +x run_ocr.sh
./run_ocr.sh
```

## 📡 Services

| Service | Port | Purpose |
|---------|------|---------|
| API | 8001 | FastAPI endpoint |
| RabbitMQ | 5672 | Message queue |
| RabbitMQ Console | 15672 | Web UI |
| Redis | 6379 | Cache |
| PostgreSQL | 5432 | Database |
| MinIO API | 9000 | Object storage |
| MinIO Console | 9001 | Web UI |

## 🔌 API Endpoints

```bash
# Docs
GET /docs

# Health
GET /health

# Upload file
POST /ocr/upload

# Check status
GET /ocr/status/{job_id}

# Get result
GET /ocr/result/{job_id}
```

## 📁 Project Structure

```
app/
├── main.py              # FastAPI entry
├── core/
│   ├── celery_app.py    # Celery config
│   ├── ocr_engine.py    # vLLM + DeepSeek
│   └── config.py        # Settings
├── services/            # Business logic
└── tasks/               # Celery tasks

docker-compose.infra.yml    # Infrastructure
docker-compose.services.yml # App services
.env                        # Configuration (secrets)
.env.example                # Configuration template
```

## ⚙️ Configuration

All config via `.env`:

```env
# Database
POSTGRES_USER=ocr_cuong
POSTGRES_PASSWORD=your_password
POSTGRES_DB=ocr_cuong_db

# Model
MODEL_PATH=/models/DeepSeek-OCRR

# Storage
MINIO_ENDPOINT=http://ocr-minio:9000
MINIO_ACCESS_KEY=rag_flow
MINIO_SECRET_KEY=your_secret_key

# Message Queue
RABBIT_URL=amqp://guest:guest@ocr-rabbit:5672/

# Cache
REDIS_URL=redis://:password@ocr-redis:6379/0
```

## 🐳 Docker Commands

```bash
# View logs
docker logs -f ocr-worker
docker logs -f ocr-api

# Check GPU
docker exec -it ocr-worker nvidia-smi

# Stop all
docker-compose -f docker-compose.services.yml down
docker-compose -f docker-compose.infra.yml down

# Clean everything (⚠️ removes data)
docker-compose -f docker-compose.infra.yml down -v
```

## 🎯 Usage Example

```python
import requests

# Upload file
files = {'file': open('document.pdf', 'rb')}
r = requests.post('http://localhost:8001/ocr/upload', files=files)
job_id = r.json()['job_id']

# Check status
r = requests.get(f'http://localhost:8001/ocr/status/{job_id}')
print(r.json())

# Get result
r = requests.get(f'http://localhost:8001/ocr/result/{job_id}')
markdown = r.json()['markdown']
```

## 📊 Performance

- Input: ~500 tokens/s
- Output: ~760 tokens/s  
- GPU Memory: ~8GB
- Supports: Multiple concurrent jobs (queue-based)

## 📄 License

MIT

## 👨‍💻 Author

Nguyen Huy Cuong