# Sử dụng image cơ sở từ NVIDIA với CUDA 11.8 và Ubuntu 22.04
FROM nvidia/cuda:11.8.1-cudnn8-runtime-ubuntu22.04

# Cài đặt các dependencies hệ thống cần thiết
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    build-essential \
    libgl1-mesa-glx \
    poppler-utils \
    wget \
    curl

# Cài đặt pip mới nhất
RUN python3 -m pip install --upgrade pip

# Cài đặt PyTorch tương thích với CUDA 11.8
RUN pip install torch==2.6.0+cu118 --extra-index-url https://download.pytorch.org/whl/cu118

# Cài đặt các thư viện Python cần thiết
RUN pip install \
    fastapi \
    uvicorn \
    pdf2image \
    pillow \
    opencv-python \
    pydantic \
    pytest \
    python-multipart \
    numpy \
    tqdm \
    transformers==4.46.3 \
    tokenizers==0.20.3 \
    PyMuPDF \
    img2pdf \
    einops \
    easydict \
    addict

# Cài đặt Flash Attention (nếu cần thiết, bạn có thể bỏ dòng này nếu không sử dụng)
RUN pip install flash-attn==2.7.3 --no-build-isolation

# Tạo thư mục làm việc và copy mã nguồn vào container
WORKDIR /app
COPY . /app

# Expose cổng để chạy FastAPI
EXPOSE 8000

# Cài đặt và chạy ứng dụng
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
