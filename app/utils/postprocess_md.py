import os
import fitz
import img2pdf
import io
import re
from tqdm import tqdm
import torch
from concurrent.futures import ThreadPoolExecutor


from app.core.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, SKIP_REPEAT, MAX_CONCURRENCY, NUM_WORKERS, CROP_MODE

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from app.core.deepseek_ocr import DeepseekOCRForCausalLM

from vllm.model_executor.models.registry import ModelRegistry

from vllm import LLM, SamplingParams
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor
from process.image_process import detect_and_correct_skew, crop_pixels_all_sides



def extract_content(text: str, job_id: str) -> str:
    """
    Làm sạch output raw của model theo logic bạn đang dùng:
    - bỏ end-of-sentence token
    - thay <|ref|>image... bằng markdown image placeholder
    - xoá các ref/det khác
    - chuẩn hoá ký hiệu latex
    """
    if "<｜end▁of▁sentence｜>" in text:
        text = text.replace("<｜end▁of▁sentence｜>", "")
    pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
    matches = re.findall(pattern, text, re.DOTALL)
    matches_image, matches_other = [], []
    for a_match in matches:
        if "<|ref|>image<|/ref|>" in a_match[0]:
            matches_image.append(a_match[0])
        else:
            matches_other.append(a_match[0])
    for img_idx, match in enumerate(matches_image):
        text = text.replace(match, f"![](./{job_id}/images/{img_idx}.jpg)\n")
    for match in matches_other:
        text = text.replace(match, "")
    text = text.replace("\\coloneqq", ":=").replace("\\eqqcolon", "=:")
    text = text.replace("\n\n\n\n", "\n\n").replace("\n\n\n", "\n\n")
    return text


def re_match(text):
    pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
    matches = re.findall(pattern, text, re.DOTALL)


    mathes_image = []
    mathes_other = []
    for a_match in matches:
        if '<|ref|>image<|/ref|>' in a_match[0]:
            mathes_image.append(a_match[0])
        else:
            mathes_other.append(a_match[0])
    return matches, mathes_image, mathes_other


def extract_coordinates_and_label(ref_text, image_width, image_height):


    try:
        label_type = ref_text[1]
        cor_list = eval(ref_text[2])
    except Exception as e:
        print(e)
        return None

    return (label_type, cor_list)


def draw_bounding_boxes(image, refs, jdx, out_path):
    """
    Hàm thực hiện Crop ảnh dựa trên hệ số 999 (Chuẩn DeepSeek).
    """
    image_width, image_height = image.size
    img_idx = 0
    # Đảm bảo lưu vào thư mục images bên trong out_path của job
    img_save_dir = os.path.join(out_path, "images")
    os.makedirs(img_save_dir, exist_ok=True)

    for ref in refs:
        # TRUYỀN ĐỦ 3 THAM SỐ VÀO ĐÂY ĐỂ FIX LỖI
        result = extract_coordinates_and_label(ref, image_width, image_height)
        
        if result:
            label_type, points_list = result
            for points in points_list:
                # TOẠ ĐỘ CHUẨN DEEPSEEK: x1, y1, x2, y2
                x1, y1, x2, y2 = points

                # QUY ĐỔI HỆ 999
                left = int(x1 / 999 * image_width)
                top = int(y1 / 999 * image_height)
                right = int(x2 / 999 * image_width)
                bottom = int(y2 / 999 * image_height)

                if label_type == 'image':
                    try:
                        cropped = image.crop((left, top, right, bottom))
                        img_name = f"{jdx}_{img_idx}.jpg"
                        cropped.save(os.path.join(img_save_dir, img_name), "JPEG", quality=95)
                        img_idx += 1
                    except Exception as e:
                        print(f"Lỗi crop: {e}")
    return image

def process_single_image(image, prompt):
    image = detect_and_correct_skew(image)   #them xu ly anh nghieng  
    """single image"""
    prompt_in = prompt
    cache_item = {
        "prompt": prompt_in,
        "multi_modal_data": {"image": DeepseekOCRProcessor().tokenize_with_images(images = [image], bos=True, eos=True, cropping=CROP_MODE)},
    }
    return cache_item


def process_image_with_refs(image, matches_ref, page_idx, out_path):
    """
    Hàm 'vỏ bọc' theo yêu cầu của bạn:
    Gọi draw_bounding_boxes để thực hiện công việc.
    """
    result_image = draw_bounding_boxes(image, matches_ref, page_idx, out_path)
    return result_image


from  app.core.config import MINIO_ACCESS_KEY, MINIO_BUCKET_NAME, MINIO_ENDPOINT, MINIO_SECRET_KEY
import boto3
from botocore.client import Config
def upload_to_minio(local_directory, job_id):
    """
    Tự động quét và đẩy tất cả: .md, .json và folder images lên MinIO
    """
    s3 = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1' 
    )

    # Đảm bảo Bucket tồn tại
    try:
        s3.head_bucket(Bucket=MINIO_BUCKET_NAME)
    except:
        s3.create_bucket(Bucket=MINIO_BUCKET_NAME)

    # Quét toàn bộ thư mục (bao gồm folder con 'images')
    for root, dirs, files in os.walk(local_directory):
        for filename in files:
            local_path = os.path.join(root, filename)
            
            # Giữ nguyên cấu trúc thư mục trên MinIO
            relative_path = os.path.relpath(local_path, local_directory)
            minio_path = f"{job_id}/{relative_path}"
            
            s3.upload_file(local_path, MINIO_BUCKET_NAME, minio_path)
    
    print(f"--- Đã đẩy toàn bộ dữ liệu Job {job_id} lên MinIO thành công ---")


    
def process_ocr_output(outputs, images, out_path):
    """
    Xử lý OCR và tự động ghi file Markdown xuống out_path.
    """
    # Tạo thư mục images bên trong out_path
    img_save_dir = os.path.join(out_path, "images")
    os.makedirs(img_save_dir, exist_ok=True)
    
    contents = ''
    contents_det = ''
    draw_images = []
    
    for idx, (output, image) in enumerate(zip(outputs, images)):
        content = output.outputs[0].text
        
        if '<｜end▁of▁sentence｜>' in content:
            content = content.replace('<｜end▁of▁sentence｜>', '')
        elif SKIP_REPEAT and not content.strip():
            continue
        
        page_num_marker = '\n<--- Page Split --->'
        contents_det += content + f'\n{page_num_marker}\n'
        
        # Lấy các refs (hình ảnh, tiêu đề...)
        matches_ref, matches_images, matches_other = re_match(content)
        
        # Gọi hàm CROP ảnh đã sửa ở trên
        process_image_with_refs(image, matches_ref, idx, img_save_dir)
        
        # Thay thế link ảnh trong nội dung Markdown
        for img_idx, match_tag in enumerate(matches_images):
            content = content.replace(match_tag, f'![](images/{idx}_{img_idx}.jpg)\n')
        
        # Dọn dẹp các tag khác
        for match in matches_other:
            content = content.replace(match, '')
        
        # Chuẩn hóa văn bản
        content = content.replace('\\coloneqq', ':=').replace('\\eqqcolon', '=: ')
        content = content.replace('\n\n\n\n', '\n\n').replace('\n\n\n', '\n\n')
        
        contents += content + f'\n{page_num_marker}\n'
        draw_images.append(image)

    # # TỰ ĐỘNG GHI FILE MARKDOWN (Khôi phục logic đã mất)
    # job_id = os.path.basename(out_path)
    # md_file_path = os.path.join(out_path, f"{job_id}.md")
    # with open(md_file_path, "w", encoding="utf-8") as f:
    #     f.write(contents)
    
    # print(f"--- Đã lưu Markdown tại: {md_file_path} ---")
    
    return contents, contents_det, draw_images