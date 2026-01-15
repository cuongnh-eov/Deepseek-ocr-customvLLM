# configs/config.py (hoặc app/core/config.py)

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ═══════════════════════════════════════════════════════════════════
# MODEL SETTINGS
# ═══════════════════════════════════════════════════════════════════
BASE_SIZE = 1024
IMAGE_SIZE = 640
CROP_MODE = True
MIN_CROPS = 2
MAX_CROPS = 6
MAX_CONCURRENCY = 32
NUM_WORKERS = 64
PRINT_NUM_VIS_TOKENS = False
SKIP_REPEAT = True
#
# Đọc từ biến môi trường
MODEL_PATH = os.getenv('MODEL_PATH', '')

# ═══════════════════════════════════════════════════════════════════
# INPUT/OUTPUT PATHS
# ═══════════════════════════════════════════════════════════════════
INPUT_PATH = os.getenv('INPUT_PATH', './uploads')
OUTPUT_PATH = os.getenv('OUTPUT_PATH', './outputs')
UPLOAD_PATH = os.getenv('UPLOAD_PATH', './uploads')

# ═══════════════════════════════════════════════════════════════════
# MINIO SETTINGS
# ═══════════════════════════════════════════════════════════════════
# Đọc từ biến môi trường
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', '')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', '')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', '')
MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME', '')

# ═══════════════════════════════════════════════════════════════════
# DATABASE & MESSAGE QUEUE
# ═══════════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv('DATABASE_URL', '')

# RabbitMQ - clean up URL
raw_rabbit = os.getenv('RABBIT_URL', '')
RABBIT_URL = (raw_rabbit.strip().rstrip('/') + '/') if raw_rabbit else ''

# Redis
REDIS_URL = os.getenv('REDIS_URL', '')

# ═══════════════════════════════════════════════════════════════════
# OTHER SETTINGS
# ═══════════════════════════════════════════════════════════════════
QUEUE_NAME = os.getenv('QUEUE_NAME', 'ocr_jobs')
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '200'))
PROMPT = '<image>\n<|grounding|>Convert the document to markdown.'
_IMAGE_TOKEN = "<image>"
CHUNK_SIZE = 40

# ═══════════════════════════════════════════════════════════════════
# OCR ENGINE SELECTION
# ═══════════════════════════════════════════════════════════════════
# Chọn engine chính: "auto", "deepseek", "mineru", hoặc "docling"
# 
# "auto" (mặc định):
#   - PDF >2MB: MinerU (tốc độ, tóm tắt tốt)
#   - PDF <2MB: Deepseek (chi tiết, fine-grained)
#   - Image: Deepseek (OCR optimized)
#   - Fallback: Docling nếu engine chính bị lỗi
#
# Cố định engine: "deepseek", "mineru", "docling"
#   - Dùng engine cố định cho tất cả files
#   - Fallback: Docling nếu engine chính bị lỗi
#
OCR_ENGINE = os.getenv('OCR_ENGINE', 'auto').lower()
if OCR_ENGINE not in ['auto', 'deepseek', 'mineru', 'docling']:
    raise ValueError(f"Invalid OCR_ENGINE: {OCR_ENGINE}. Must be 'auto', 'deepseek', 'mineru', or 'docling'")

# ═══════════════════════════════════════════════════════════════════
# TOKENIZER INITIALIZATION
# ═══════════════════════════════════════════════════════════════════
try:
    from transformers import AutoTokenizer
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    print(f"✅ Tokenizer loaded from: {MODEL_PATH}")
except Exception as e:
    TOKENIZER = None
    print(f"⚠️ Không load được Tokenizer DeepSeek: {e}. Worker sẽ chạy ở chế độ dự phòng.")