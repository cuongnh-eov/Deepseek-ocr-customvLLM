📑 DeepSeek-OCR Custom vLLM Deployment
Dự án cung cấp giải pháp OCR tài chính chất lượng cao bằng model DeepSeek-OCR, được đóng gói hoàn toàn trong môi trường Docker để xử lý Batch Processing qua Celery & RabbitMQ.

🚀 Tính năng nổi bật
Gundam Mode: Tối ưu hóa độ phân giải ảnh (Crop-mode) cho các bảng tài chính phức tạp.

Asynchronous Workflow: Tách biệt API (FastAPI) và Worker (Celery) giúp hệ thống không bị treo khi xử lý PDF dài.

Resource Management: Tự động cấu hình VRAM và tối ưu hóa GPU qua Docker Nvidia Runtime.

Production Ready: Triển khai nhanh chóng với 1 lệnh duy nhất.

🛠 Yêu cầu hệ thống
Hardware: NVIDIA GPU (Khuyên dùng 12GB VRAM trở lên cho chế độ Gundam).

Driver: NVIDIA Container Toolkit đã được cài đặt.

Software: Docker & Docker Compose.

📥 Hướng dẫn cài đặt
1. Clone Project
Bash

git clone https://github.com/cuongnh-eov/Deepseek-ocr-customvLLM.git
cd Deepseek-ocr-customvLLM
2. Chuẩn bị Model
Do kích thước model lớn, bạn cần copy folder model vào thư mục project:

Bash

# Đảm bảo cấu trúc như sau:
# /Deepseek-ocr-customvLLM/DeepSeek-OCRR/<files_model>
3. Khởi chạy hệ thống
Sử dụng Docker Compose để tự động xây dựng môi trường và kết nối các dịch vụ:

Bash

docker-compose up --build
📋 Luồng thực thi (Architecture Flow)
Client gửi file PDF/Image qua Endpoint POST /process.

API lưu file vào MinIO và đẩy Task ID vào RabbitMQ.

Worker (Celery) nhận task, gọi DeepSeek-OCR (GPU) để chuyển đổi sang Markdown/JSON.

Result được cập nhật vào Postgres và gửi thông báo hoàn tất.