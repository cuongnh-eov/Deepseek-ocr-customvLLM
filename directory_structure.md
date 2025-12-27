```text
.
├── app/                            # [TẦNG CORE ỨNG DỤNG] - Quản lý logic chính
│   ├── api/                        # Tầng Giao tiếp (Communication Layer)
│   │   ├── routes/                 
│   │   │   └── ocr.py              # Endpoint xử lý: Upload, Check Status, Get Results
│   │   └── schemas/                
│   │       └── schemas.py          # Định nghĩa cấu trúc vào/ra chuẩn Pydantic
│   ├── config.py                   # Cấu hình hệ thống (Paths, Max Size, GPU Settings)
│   ├── core/                       # Cấu hình lõi (System Config)
│   │   ├── celery_app.py           # Cấu hình hàng đợi: Điều phối tác vụ bất đồng bộ
│   │   ├── database.py             # Kết nối DB: Quản lý phiên làm việc với CSDL
│   │   └── ocr_engine.py           # Lõi AI: Nạp Model DeepSeek và thực hiện Inference
│   ├── main.py                     # Entry Point: Khởi tạo FastAPI và đăng ký Routes
│   ├── models/                     # Thực thể dữ liệu
│   │   └── documents.py            # Định nghĩa bảng CSDL (SQLAlchemy) cho OCR Jobs
│   ├── services/                   # Tầng Điều phối (Orchestration)
│   │   ├── file_handler.py         # Xử lý File: Lưu trữ vật lý, validate, dọn dẹp
│   │   ├── ocr_service.py          # Logic nghiệp vụ trung tâm kết nối API & Tasks
│   │   ├── processor.py            # Xử lý logic dữ liệu đặc thù
│   │   └── publisher.py            # Gửi thông báo/kết quả sau khi hoàn thành
│   ├── tasks/                      # Tầng Thực thi (Execution)
│   │   └── tasks.py                # Định nghĩa Celery Tasks chạy ngầm trên Worker
│   └── utils/                      # Công cụ bổ trợ
│       ├── postprocess_json.py     # Hậu xử lý: Chuẩn hóa cấu trúc JSON từ AI
│       ├── postprocess_md.py       # Hậu xử lý: Định dạng và làm sạch Markdown
│       └── utils.py                # Hàm dùng chung: Logger, xử lý chuỗi, Timer
│
├── deepencoder/                    # [TẦNG THẤP - AI MODEL] - Kiến trúc DeepLearning
│   ├── build_linear.py             # Khởi tạo các lớp tuyến tính cho mô hình
│   ├── clip_sdpa.py                # Tối ưu hóa Attention bằng cơ chế SDPA
│   └── sam_vary_sdpa.py            # Module SAM: Trích xuất đặc trưng vùng ảnh
│
├── process/                        # [TIỀN & HẬU XỬ LÝ ẢNH] - Thuật toán bổ trợ
│   ├── image_process.py            # Xử lý ảnh: Cắt, xoay, tăng cường chất lượng
│   └── ngram_norepeat.py           # Thuật toán khử lặp từ khi AI sinh nội dung
│
├── worker/                         # [QUẢN LÝ TÀI NGUYÊN] - Runtime Environment
│   ├── model_init.py               # Singleton Logic: Đảm bảo model load 1 lần lên VRAM
│   └── model_runner.py             # Thực thi: Quản lý vòng đời chạy model trên Worker
│
├── run_ocr.sh                      # [ENTRY POINT] - Script khởi chạy toàn bộ hệ thống
├── requirements.txt                # Danh sách thư viện phụ thuộc
└── dockerfile                      # Cấu hình đóng gói triển khai (Containerization)