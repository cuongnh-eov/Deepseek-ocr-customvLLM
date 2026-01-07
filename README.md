# 🚀 Advanced OCR Pipeline & Distributed Processing System

Hệ thống xử lý OCR tài liệu nâng cao, tích hợp trí tuệ nhân tạo (DeepSeek-OCR) và kiến trúc phân tán (Celery + RabbitMQ + MinIO) để chuyển đổi PDF/Hình ảnh sang Markdown chất lượng cao.

---

## 📑 Mục lục

- [Tính năng nổi bật](#-tính-năng-nổi-bật)
- [Công nghệ sử dụng](#-công-nghệ-sử-dụng)
- [Cấu trúc dự án](#-cấu-trúc-dự-án)
- [Cài đặt & Chạy](#-cài-đặt--chạy)
  - [Chạy Local](#-chạy-local)
  - [Chạy Docker](#-chạy-docker)
- [Kết nối từ máy khác](#-kết-nối-từ-máy-khác)
- [API Endpoints](#-api-endpoints)
- [Hiệu suất](#-hiệu-suất)

---

## 🌟 Tính năng nổi bật

### 1. Xử lý thị giác máy tính (Computer Vision)

| Tính năng | Mô tả |
|-----------|-------|
| **Deskewing & Orientation** | Tự động nhận diện góc nghiêng và xoay trang giấy về trạng thái thẳng |
| **Coordinate Mapping** | Chuyển đổi tọa độ từ hệ chuẩn AI sang kích thước thực tế của ảnh gốc |
| **Smart Cropping** | Tự động cắt hình ảnh và bảng biểu, lọc ảnh rỗng và box diện tích = 0 |

### 2. Trí tuệ nhân tạo & OCR (AI Engine)

| Tính năng | Mô tả |
|-----------|-------|
| **DeepSeek-OCR** | Mô hình ngôn ngữ thị giác mạnh mẽ cho văn bản phức tạp |
| **LaTeX Support** | Nhận diện và trích xuất công thức toán học chính xác |
| **Layout Awareness** | Duy trì cấu trúc tài liệu, phân cấp Heading xuyên suốt các trang |
| **vLLM Optimization** | Tối ưu GPU với Batch Processing và KV Cache (>700 tokens/s) |

### 3. Kiến trúc phân tán (Distributed Architecture)

| Thành phần | Mô tả |
|------------|-------|
| **Celery + RabbitMQ** | Task queue bất đồng bộ, xử lý hàng trăm file cùng lúc |
| **MinIO** | Object storage S3-compatible lưu trữ kết quả |
| **Real-time Notification** | Tự động thông báo qua RabbitMQ khi hoàn tất Job |

---

## 🏗 Công nghệ sử dụng

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   Backend        │  FastAPI, Celery, RabbitMQ                              │
│   AI/ML          │  DeepSeek-OCR, vLLM, PyTorch, CUDA 11.8                 │
│   Image          │  OpenCV, Pillow, Tesseract, PyMuPDF                     │
│   Storage        │  MinIO, PostgreSQL, Redis                               │
│   DevOps         │  Docker, Docker Compose                                  │
│   Language       │  Python 3.12                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Cấu trúc dự án

```
Deepseek-ocr-customvLLM/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── core/
│   │   ├── celery_app.py       # Celery configuration
│   │   ├── ocr_engine.py       # vLLM + DeepSeek OCR
│   │   └── config.py           # Environment config
│   ├── services/
│   │   ├── ocr_service.py      # OCR processing logic
│   │   └── publisher.py        # RabbitMQ notification
│   └── tasks/
│       └── tasks.py            # Celery tasks
├── configs/
│   └── config.py               # Model & system config
├── docker-compose.infra.yml    # Infra services (DB, Redis, RabbitMQ, MinIO)
├── docker-compose.services.yml # App services (API, Worker)
├── Dockerfile                  # Docker image build
├── requirements.txt            # Python dependencies
├── run_ocr.sh                  # Local run script
└── wheels/
    └── vllm-0.8.5+cu118-*.whl  # vLLM wheel for CUDA 11.8
```

---

## 🚀 Cài đặt & Chạy

### Prerequisites

- **GPU:** NVIDIA GPU với CUDA 11.8+ (RTX 3060 hoặc cao hơn)
- **RAM:** 16GB+ recommended
- **Disk:** 50GB+ cho model và data
- **Docker:** Docker Engine 20.10+ với NVIDIA Container Toolkit

---

### 🖥 Chạy Local

#### 1. Tạo môi trường Conda

```bash
conda create -n Vllm python=3.12 -y
conda activate Vllm
```

#### 2. Cài đặt dependencies

```bash
# PyTorch với CUDA 11.8
pip install torch==2.6.0+cu118 torchvision==0.21.0+cu118 torchaudio==2.6.0+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# vLLM wheel
pip install ./wheels/vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl

# xformers & flash-attn
pip install xformers==0.0.29.post2 --index-url https://download.pytorch.org/whl/cu118
pip install flash-attn==2.7.3 --no-build-isolation

# Các dependencies còn lại
pip install -r requirements.txt
```

#### 3. Chạy hệ thống

```bash
# Cấp quyền thực thi
chmod +x run_ocr.sh

# Chạy (tự động start Docker containers cho infra + chạy API & Worker)
./run_ocr.sh
```

#### 4. Kiểm tra

```bash
# API docs
curl http://localhost:8001/docs

# Health check
curl http://localhost:8001/health
```

---

### 🐳 Chạy Docker

#### 1. Chuẩn bị wheel vLLM

```bash
mkdir -p ./wheels
cp /path/to/vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl ./wheels/
```

#### 2. Khởi động hạ tầng (Infra)

```bash
docker compose -f docker-compose.infra.yml up -d
```

Chờ 15 giây để các services sẵn sàng:

```bash
sleep 15
docker ps
```

**Các containers sẽ chạy:**

| Container | Port | Mô tả |
|-----------|------|-------|
| ocr-postgres | 5432 | PostgreSQL Database |
| ocr-rabbit | 5672, 15672 | RabbitMQ Message Broker |
| ocr-redis | 6379 | Redis Cache |
| ocr-minio | 9000, 9001 | MinIO Object Storage |

#### 3. Build và chạy Services

```bash
docker compose -f docker-compose.services.yml up -d --build
```

**Các containers sẽ chạy:**

| Container | Port | Mô tả |
|-----------|------|-------|
| ocr-api | 8001 | FastAPI Server |
| ocr-worker | - | Celery Worker (GPU) |

#### 4. Kiểm tra logs

```bash
# Xem tất cả containers
docker ps

# Xem log API
docker logs -f ocr-api

# Xem log Worker
docker logs -f ocr-worker

# Kiểm tra GPU trong worker
docker exec -it ocr-worker nvidia-smi
```

#### 5. Dừng hệ thống

```bash
# Dừng services
docker compose -f docker-compose.services.yml down

# Dừng infra (giữ data)
docker compose -f docker-compose.infra.yml down

# Dừng infra và XÓA data
docker compose -f docker-compose.infra.yml down -v
```

---

## 📡 Kết nối từ máy khác

### Thông tin kết nối (LAN)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   🖥️  SERVER IP: 10.0.0.156                                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  📦 MINIO (Object Storage)                                          │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │  Console:    http://10.0.0.156:9001                                 │  │
│   │  API:        http://10.0.0.156:9000                                 │  │
│   │  Username:   rag_flow                                               │  │
│   │  Password:   infini_rag_flow                                        │  │
│   │  Bucket:     ocr-results                                            │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  🐰 RABBITMQ (Message Queue)                                        │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │  AMQP:       amqp://guest:guest@10.0.0.156:5672/                    │  │
│   │  Console:    http://10.0.0.156:15672                                │  │
│   │  Username:   guest                                                  │  │
│   │  Password:   guest                                                  │  │
│   │  Queue:      job_finished                                           │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  🚀 OCR API                                                         │  │
│   ├─────────────────────────────────────────────────────────────────────┤  │
│   │  Endpoint:   http://10.0.0.156:8001                                 │  │
│   │  Docs:       http://10.0.0.156:8001/docs                            │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Ví dụ: Tải file từ MinIO (Python)

```python
from minio import Minio

client = Minio(
    "10.0.0.156:9000",
    access_key="rag_flow",
    secret_key="infini_rag_flow",
    secure=False
)

# Liệt kê files
for obj in client.list_objects("ocr-results", recursive=True):
    print(f"📄 {obj.object_name}")

# Tải file
client.fget_object("ocr-results", "job_123/result.md", "./result.md")
```

---

### Ví dụ: Nhận thông báo qua RabbitMQ (Python)

```python
import pika
import json

def callback(ch, method, properties, body):
    msg = json.loads(body)
    print(f"✅ Job {msg['job_id']} hoàn thành!")
    print(f"📁 File: {msg.get('file_path')}")

connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host='10.0.0.156',
        port=5672,
        credentials=pika.PlainCredentials('guest', 'guest')
    )
)
channel = connection.channel()
channel.queue_declare(queue='job_finished', durable=True)
channel.basic_consume(queue='job_finished', on_message_callback=callback, auto_ack=True)

print("🎧 Đang lắng nghe thông báo...")
channel.start_consuming()
```

---

## 📚 API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/docs` | Swagger UI Documentation |
| `GET` | `/health` | Health check |
| `POST` | `/ocr/upload` | Upload PDF/Image để OCR |
| `GET` | `/ocr/status/{job_id}` | Kiểm tra trạng thái job |
| `GET` | `/ocr/result/{job_id}` | Lấy kết quả OCR |

---

## 📈 Hiệu suất

| Metric | Giá trị |
|--------|---------|
| **Input Speed** | ~500 tokens/s |
| **Output Speed** | ~760 tokens/s |
| **GPU Memory** | ~8GB (RTX 3060 12GB) |
| **Concurrent Jobs** | Unlimited (queue-based) |

---

## 🛠 Luồng hoạt động (Workflow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   1. INPUT                                                                  │
│      User upload PDF qua FastAPI                                           │
│      │                                                                      │
│      ▼                                                                      │
│   2. QUEUE                                                                  │
│      File đưa vào RabbitMQ → Celery Worker nhận task                       │
│      │                                                                      │
│      ▼                                                                      │
│   3. INFERENCE                                                              │
│      vLLM load ảnh → DeepSeek-OCR trích xuất Text + Tọa độ                │
│      │                                                                      │
│      ▼                                                                      │
│   4. POST-PROCESS                                                           │
│      Cắt ảnh, sửa tọa độ, chuẩn hóa Markdown                              │
│      │                                                                      │
│      ▼                                                                      │
│   5. OUTPUT                                                                 │
│      Lưu vào MinIO → Gửi thông báo qua queue "job_finished"               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📄 License

MIT License

---

## 👥 Tác giả

- **Nguyen Huy Cuong** - *Initial work*

---

## 🙏 Acknowledgments

- [DeepSeek-AI](https://github.com/deepseek-ai) - OCR Model
- [vLLM](https://github.com/vllm-project/vllm) - Inference Engine
- [MinIO](https://min.io/) - Object Storage