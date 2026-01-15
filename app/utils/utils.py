import os
import fitz
import img2pdf
import io
import re
from tqdm import tqdm


import torch
from typing import Optional, Tuple


from concurrent.futures import ThreadPoolExecutor
 

from app.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, SKIP_REPEAT, MAX_CONCURRENCY, NUM_WORKERS, CROP_MODE

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from app.core.engine.ocr_engine import DeepseekOCRForCausalLM

from vllm.model_executor.models.registry import ModelRegistry

from vllm import LLM, SamplingParams
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor



class Colors:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    RESET = '\033[0m' 

# def pdf_to_images_high_quality(pdf_path, dpi=144, image_format="PNG"):
#     """
#     pdf2images
#     """
#     images = []
    
#     pdf_document = fitz.open(pdf_path)
    
#     zoom = dpi / 72.0
#     matrix = fitz.Matrix(zoom, zoom)
    
#     for page_num in range(pdf_document.page_count):
#         page = pdf_document[page_num]

#         pixmap = page.get_pixmap(matrix=matrix, alpha=False)
#         Image.MAX_IMAGE_PIXELS = None

#         if image_format.upper() == "PNG":
#             img_data = pixmap.tobytes("png")
#             img = Image.open(io.BytesIO(img_data))
#         else:
#             img_data = pixmap.tobytes("png")
#             img = Image.open(io.BytesIO(img_data))
#             if img.mode in ('RGBA', 'LA'):
#                 background = Image.new('RGB', img.size, (255, 255, 255))
#                 background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
#                 img = background
        
#         images.append(img)
    
#     pdf_document.close()
#     return images
#
def pdf_to_images_high_quality(pdf_path, dpi=144, image_format="PNG", start_page=0, end_page=None):
    images = []
    pdf_document = fitz.open(pdf_path)
    total_pages = pdf_document.page_count
    
    # Giới hạn trang theo batch
    if end_page is None or end_page > total_pages:
        end_page = total_pages

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    
    # Chỉ render đoạn 20 trang
    for page_num in range(start_page, end_page):
        page = pdf_document[page_num]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        Image.MAX_IMAGE_PIXELS = None

        # --- LOGIC GỐC CỦA CƯƠNG ---
        if image_format.upper() == "PNG":
            img_data = pixmap.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
        else:
            img_data = pixmap.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
        images.append(img)
    
    pdf_document.close()
    return images

def pil_to_pdf_img2pdf(pil_images, output_path):

    if not pil_images:
        return
    
    image_bytes_list = []
    
    for img in pil_images:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=95)
        img_bytes = img_buffer.getvalue()
        image_bytes_list.append(img_bytes)
    
    try:
        pdf_bytes = img2pdf.convert(image_bytes_list)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    except Exception as e:
        print(f"error: {e}")

    
def get_gpu_info() -> Tuple[Optional[str], Optional[int]]:
    """
    Lấy thông tin GPU đang dùng.
    Return: (gpu_name, total_mb) hoặc (None, None) nếu không có CUDA.
    """
    if not torch.cuda.is_available():
        return None, None
    idx = torch.cuda.current_device()
    name = torch.cuda.get_device_name(idx)
    total_mb = int(torch.cuda.get_device_properties(idx).total_memory / (1024 * 1024))
    return name, total_mb
def reset_gpu_peak():
    """
    Reset peak memory stats để đo "peak VRAM" chính xác cho từng job.
    """
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
def read_gpu_peak_mb() -> Tuple[Optional[int], Optional[int]]:
    """
    Read peak memory used during job.
    - allocated: memory do tensors allocate
    - reserved : memory cached by CUDA allocator
    """
    if not torch.cuda.is_available():
        return None, None
    peak_alloc = int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    peak_resv = int(torch.cuda.max_memory_reserved() / (1024 * 1024))
    return peak_alloc, peak_resv





import re

def apply_regex_heuristics(text: str) -> str:
    if not text or not text.strip():
        return text
    
    date_pattern = r"(\d{1,2}/\d{1,2}/\d{4})"
    match = re.search(date_pattern, text)
    if match:
        start, end = match.span()
        prefix = text[:start].strip()
        date_val = match.group(1)
        suffix = text[end:].strip()
        
        parts = []
        if prefix: parts.append(prefix)
        parts.append(date_val)
        if suffix: parts.append(suffix)
        return " | ".join(parts)
    
    # Tách số dính chữ an toàn
    return re.sub(r'([a-zA-Z])(\d)', r'\1 | \2', text)

def validate_financial_rows(rows: list) -> str:
    try:
        data_values = []
        total_value = 0
        has_total_row = False

        for row in rows:
            # Join các cột, bỏ dấu phân cách
            row_str = " ".join(row).replace('.', '').replace(',', '')
            # Tìm tất cả số
            nums = re.findall(r'[-+]?\d+', row_str)
            
            # KIỂM TRA AN TOÀN: Nếu hàng không có số nào thì bỏ qua
            if not nums: 
                continue
            
            # Lấy số cuối cùng an toàn
            current_val = int(nums[-1])

            if any(kw in row_str.lower() for kw in ["cộng", "tổng cộng", "total"]):
                total_value = current_val
                has_total_row = True
            else:
                data_values.append(current_val)

        if has_total_row and data_values:
            calculated_sum = sum(data_values)
            if abs(calculated_sum - total_value) > 2:
                return "Low Confidence Table (Column Shift Detected)"
        
        return "High"
    except (ValueError, IndexError, Exception):
        # Trả về Indeterminate thay vì làm sập cả Job
        return "Indeterminate"