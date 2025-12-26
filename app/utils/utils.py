import os
import fitz
import img2pdf
import io
import re
from tqdm import tqdm


import torch
from typing import Optional, Tuple


from concurrent.futures import ThreadPoolExecutor
 

from app.core.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, SKIP_REPEAT, MAX_CONCURRENCY, NUM_WORKERS, CROP_MODE

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from app.core.deepseek_ocr import DeepseekOCRForCausalLM

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

def pdf_to_images_high_quality(pdf_path, dpi=144, image_format="PNG"):
    """
    pdf2images
    """
    images = []
    
    pdf_document = fitz.open(pdf_path)
    
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    
    for page_num in range(pdf_document.page_count):
        page = pdf_document[page_num]

        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        Image.MAX_IMAGE_PIXELS = None

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

