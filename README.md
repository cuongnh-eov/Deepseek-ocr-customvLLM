# Hướng dẫn cài đặt và chạy chương trình DeepSeek OCR

## 1. Clone dự án

Trước tiên, clone repository về máy của bạn:

```bash
git clone https://github.com/cuongnh-eov/Deepseek-ocr-customvLLM.git
cd TTS-01
2. Tạo môi trường ảo và cài đặt các thư viện yêu cầu
Tạo môi trường conda với Python 3.12.9 và kích hoạt môi trường:


conda create -n deepseek-ocr python=3.12.9 -y
conda activate deepseek-ocr
Cài đặt các thư viện yêu cầu với CUDA 11.8:

pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu118
pip install transformers==4.46.3 tokenizers==0.20.3 einops addict easydict
pip install flash-attn==2.7.3 --no-build-isolation
Nếu gặp lỗi khi cài đặt flash-attn, bạn có thể thử cài đặt lại với lệnh sau:

TMPDIR=/home/cuongnh/.cache/pip pip install flash-attn==2.7.3
3. Cài đặt các thư viện khác từ requirements.txt
Tiếp theo, cài đặt tất cả các thư viện khác từ file requirements.txt:
pip install -r requirements.txt
4. Kiểm thử chương trình
Chạy mô hình OCR
Sau khi cài đặt xong, bạn có thể kiểm thử mô hình OCR bằng cách chạy lệnh dưới đây:
cd TTS-01
python app.model_runner.py
Triển khai API
Để triển khai API và sử dụng dịch vụ của chương trình, chạy lệnh sau:
python app.main.py
