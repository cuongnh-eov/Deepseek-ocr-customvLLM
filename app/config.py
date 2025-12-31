# TODO: change modes
# Tiny: base_size = 512, image_size = 512, crop_mode = False
# Small: base_size = 640, image_size = 640, crop_mode = False
# Base: base_size = 1024, image_size = 1024, crop_mode = False
# Large: base_size = 1280, image_size = 1280, crop_mode = False
# Gundam: base_size = 1024, image_size = 640, crop_mode = True

BASE_SIZE = 1024
IMAGE_SIZE = 640
CROP_MODE = True
MIN_CROPS= 2
MAX_CROPS= 6 # max:9; If your GPU memory is small, it is recommended to set it to 6.
MAX_CONCURRENCY = 32 # If you have limited GPU memory, lower the concurrency count.
NUM_WORKERS = 64 # image pre-process (resize/padding) workers 
PRINT_NUM_VIS_TOKENS = False
SKIP_REPEAT = True
MODEL_PATH = '/home/cuongnh/PycharmProjects/TTTS_01/DeepSeek-OCRR' # change to your model path

# TODO: change INPUT_PATH
# .pdf: run_dpsk_ocr_pdf.py; 
# .jpg, .png, .jpeg: run_dpsk_ocr_image.py; 
# Omnidocbench images path: run_dpsk_ocr_eval_batch.py

INPUT_PATH = '/home/cuongnh/OCR_docs/data/1_kts_2025_10_23_23347e6_vi_baocaotaichinh_q1_2026.pdf'
# OUTPUT_PATH = './outputs'
OUTPUT_PATH = '/home/cuongnh/OCR_docs/outputsssssssssssssssssssssssssssssssss'
PROMPT = '<image>\n<|grounding|>Convert the document to markdown.'


import os
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "rag_flow"
MINIO_SECRET_KEY = "infini_rag_flow"
MINIO_BUCKET_NAME = "ocr-results"


UPLOAD_PATH = os.getenv("UPLOAD_PATH", "./uploads")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "./outputs")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

# Sửa lại dòng này trong app/core/config.py
raw_rabbit = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
# Xóa khoảng trắng và đảm bảo chỉ có 1 dấu / ở cuối
RABBIT_URL = raw_rabbit.strip().rstrip('/') + '/'


REDIS_URL = os.getenv("REDIS_URL", "redis://:infini_rag_flow@127.0.0.1:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "ocr_jobs")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "./outputs")
# Trong file configs/config.py
try:
    from transformers import AutoTokenizer
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    print("✅ Tokenizer loaded.")
except Exception as e:
    TOKENIZER = None
    print(f"⚠️ Không load được Tokenizer DeepSeek: {e}. Worker sẽ chạy ở chế độ dự phòng.")




DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db')


_IMAGE_TOKEN = "<image>"

CHUNK_SIZE = 40