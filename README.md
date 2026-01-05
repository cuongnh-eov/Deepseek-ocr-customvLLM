Đây là bản thảo file **README.md** chuyên nghiệp cho dự án của bạn. Nó tóm tắt toàn bộ công trình từ xử lý ảnh, AI OCR cho đến hệ thống phân tán mà bạn đã dày công xây dựng.

---

# 🚀 Advanced OCR Pipeline & Distributed Processing System

Hệ thống xử lý OCR tài liệu nâng cao, tích hợp trí tuệ nhân tạo (DeepSeek-OCR) và kiến trúc phân tán (Celery + RabbitMQ + MinIO) để chuyển đổi PDF/Hình ảnh sang Markdown chất lượng cao.

## 🌟 Tính năng nổi bật

### 1. Xử lý thị giác máy tính (Computer Vision)

* **Deskewing & Orientation:** Tự động nhận diện góc nghiêng và xoay trang giấy về trạng thái thẳng, giúp AI nhận diện tọa độ chính xác.
* **Coordinate Mapping:** Chuyển đổi tọa độ từ hệ chuẩn  của mô hình AI sang kích thước thực tế của ảnh gốc (ví dụ: ).
* **Smart Cropping & Validation:** Tự động cắt (crop) hình ảnh và bảng biểu từ trang giấy. Tích hợp bộ lọc chặn ảnh rỗng (empty image) và box diện tích bằng 0 để đảm bảo hệ thống không bị crash.

### 2. Trí tuệ nhân tạo & OCR (AI Engine)

* **DeepSeek-OCR Integration:** Sử dụng mô hình ngôn ngữ thị giác mạnh mẽ để nhận diện văn bản phức tạp.
* ** Support:** Nhận diện và trích xuất công thức toán học, ký tự đặc biệt một cách chính xác.
* **Layout Awareness:** Duy trì cấu trúc tài liệu, phân cấp Heading (#, ##, ###) xuyên suốt giữa các trang, không bị reset ngữ cảnh khi sang trang mới.
* **vLLM Optimization:** Tối ưu hóa tốc độ suy luận (Inference) trên GPU RTX 3060, hỗ trợ Batch Processing và KV Cache để đạt tốc độ >700 tokens/s.

### 3. Kiến trúc hệ thống phân tán (Distributed Architecture)

* **Asynchronous Task Queue:** Sử dụng **Celery** và **RabbitMQ** để quản lý tác vụ bất đồng bộ. Hệ thống có thể tiếp nhận hàng trăm file PDF cùng lúc mà không gây nghẽn.
* **Object Storage:** Tích hợp **MinIO** (S3 Compatible) để lưu trữ tập trung file Markdown và các ảnh đã cắt theo từng Job ID riêng biệt.
* **Real-time Notification:** Hệ thống tự động phát tin nhắn qua RabbitMQ sau khi hoàn tất mỗi Job để thông báo cho các dịch vụ khác (như RAG hoặc UI) xử lý tiếp.

---

## 🏗 Công nghệ sử dụng

* **Ngôn ngữ:** Python 3.12
* **Backend Framework:** FastAPI (API Layer)
* **Distributed Task:** Celery, RabbitMQ (Broker)
* **AI/LLM:** DeepSeek-OCR, vLLM Engine, CUDA
* **Image Processing:** OpenCV, Pillow, Tesseract (Deskewing)
* **Storage:** MinIO
* **PDF Processing:** Pikepdf, pdf2image

---

## 🛠 Luồng hoạt động (Workflow)

1. **Input:** User upload file PDF qua FastAPI.
2. **Queue:** File được đưa vào hàng đợi RabbitMQ; Celery Worker nhận nhiệm vụ.
3. **Inference:** vLLM nạp ảnh  DeepSeek-OCR trích xuất Text + Tọa độ ảnh.
4. **Post-process:** Cắt ảnh, sửa lỗi tọa độ, chuẩn hóa Markdown.
5. **Output:** Lưu kết quả vào MinIO và bắn thông báo qua hàng đợi `job_finished`.

---

## 📡 Kết nối với các dịch vụ khác

Hệ thống hỗ trợ kết nối trực tiếp với các cộng sự hoặc dịch vụ tiêu thụ dữ liệu (Consumer) qua mạng nội bộ hoặc Internet:

* **Endpoint API:** `http://<YOUR_IP>:9000` (MinIO API)
* **Messaging:** `amqp://guest:guest@<YOUR_IP>:5672/` (RabbitMQ)
* **Access Key:** `rag_flow` / `infini_rag_flow`

---

## 📈 Hiệu suất thực tế

* **Tốc độ Input:** ~500 tokens/s.
* **Tốc độ Output:** ~760 tokens/s.
* **Độ ổn định:** Xử lý mượt mà các file PDF lỗi, ảnh nhiễu hoặc box tọa độ sai nhờ cơ chế Validation chặt chẽ.

---

