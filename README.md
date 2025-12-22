# Hướng dẫn cài đặt và chạy chương trình DeepSeek OCR

## 1. Clone dự án

Trước tiên, clone repository về máy của bạn:

```bash
git clone https://github.com/cuongnh-eov/Deepseek-ocr-customvLLM.git
cd TTS-01
git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
cd DeepSeek-OCR-master/DeepSeek-OCR-vllm 
conda create -n deepseek-ocr python=3.12.9 -y  
conda activate deepseek-ocr   # môi trường conda
wget https://github.com/vllm-project/vllm/releases/download/v0.8.5/vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118  
pip install vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl 
pip install -r requirements.txt  
pip install flash-attn==2.7.3 --no-build-isolation
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
