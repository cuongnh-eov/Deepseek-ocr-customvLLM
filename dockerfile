FROM nvidia/cuda:11.8.0-devel-ubuntu22.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-dev build-essential gcc g++ git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime ---
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

# Mặc định khi chạy container đơn lẻ sẽ bật API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]