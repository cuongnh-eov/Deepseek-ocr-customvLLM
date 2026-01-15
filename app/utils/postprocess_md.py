import os
import fitz
import img2pdf
import io
import re
from tqdm import tqdm
import torch
from concurrent.futures import ThreadPoolExecutor


from app.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, SKIP_REPEAT, MAX_CONCURRENCY, NUM_WORKERS, CROP_MODE

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from app.core.engine.ocr_engine import DeepseekOCRForCausalLM

from vllm.model_executor.models.registry import ModelRegistry

from vllm import LLM, SamplingParams
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor
from process.image_process import detect_and_correct_skew, crop_flexible_pixels



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
    Đã sửa lỗi diện tích bằng 0 gây crash.
    """
    image_width, image_height = image.size
    img_idx = 0
    print(f"DEBUG: Processing Page {jdx} with image size: {image_width}x{image_height}")
    
    img_save_dir = os.path.join(out_path, "images")
    os.makedirs(img_save_dir, exist_ok=True)

    for ref in refs:
        result = extract_coordinates_and_label(ref, image_width, image_height)
        
        if result:
            label_type, points_list = result
            for points in points_list:
                # Toạ độ gốc từ model: x1, y1, x2, y2
                x1, y1, x2, y2 = points

                # 1. QUY ĐỔI VÀ ĐẢM BẢO KHÔNG VƯỢT QUÁ CẠNH ẢNH
                left = max(0, min(int(x1 / 999 * image_width), image_width))
                top = max(0, min(int(y1 / 999 * image_height), image_height))
                right = max(0, min(int(x2 / 999 * image_width), image_width))
                bottom = max(0, min(int(y2 / 999 * image_height), image_height))

                # 2. KIỂM TRA TỌA ĐỘ BỊ NGƯỢC (Nếu x1 > x2 thì swap lại)
                if left > right: left, right = right, left
                if top > bottom: top, bottom = bottom, top

                # 3. FIX LỖI "EMPTY IMAGE": Tính toán chiều rộng và cao
                width = right - left
                height = bottom - top

                if label_type == 'image':
                    # Chỉ lưu nếu ảnh có kích thước hữu dụng (ví dụ > 2px)
                    if width > 2 and height > 2:
                        try:
                            cropped = image.crop((left, top, right, bottom))
                            img_name = f"{jdx}_{img_idx}.jpg"
                            save_file_path = os.path.join(img_save_dir, img_name)
                            
                            cropped.save(save_file_path, "JPEG", quality=95)
                            img_idx += 1
                        except Exception as e:
                            print(f"⚠️ Lỗi khi lưu ảnh con tại trang {jdx}: {e}")
                    else:
                        print(f"⏩ Bỏ qua box quá nhỏ hoặc rỗng tại trang {jdx}: {width}x{height}")
                        
    return image

# def draw_bounding_boxes(image, refs, jdx, out_path):
#     # Lấy kích thước hiện tại (Nếu đã crop 85px, đây sẽ là kích thước mới)
#     image_width, image_height = image.size
#     img_idx = 0
#     img_save_dir = os.path.join(out_path, "images")
#     os.makedirs(img_save_dir, exist_ok=True)

#     for ref in refs:
#         result = extract_coordinates_and_label(ref, image_width, image_height)
        
#         if result:
#             label_type, points_list = result
#             for points in points_list:
#                 # Tọa độ từ hệ 999 của DeepSeek
#                 x1, y1, x2, y2 = points

#                 # Quy đổi dựa trên kích thước THỰC TẾ của tham số image truyền vào
#                 left = max(0, int(x1 / 999 * image_width))
#                 top = max(0, int(y1 / 999 * image_height))
#                 right = min(image_width, int(x2 / 999 * image_width))
#                 bottom = min(image_height, int(y2 / 999 * image_height))

#                 if label_type == 'image':
#                     # Kiểm tra diện tích vùng cắt có hợp lệ không
#                     if right > left and bottom > top:
#                         try:
#                             cropped = image.crop((left, top, right, bottom))
#                             img_name = f"{jdx}_{img_idx}.jpg"
#                             cropped.save(os.path.join(img_save_dir, img_name), "JPEG", quality=95)
#                             img_idx += 1
#                         except Exception as e:
#                             print(f"Lỗi crop tại trang {jdx}: {e}")
#     return image

#
def process_single_image(image, prompt):
    # print("trung binh anh size:", image.size)
    image = detect_and_correct_skew(image)   #them xu ly anh nghieng  
    # print("sau khi chinh nghieng:", image.size)
    image = crop_flexible_pixels(image)  # them ham crop linh dong
    # print("sau khi crop linh dong:", image.size)
    """single image"""
    prompt_in = prompt
    cache_item = {
        "prompt": prompt_in,
        "multi_modal_data": {"image": DeepseekOCRProcessor().tokenize_with_images(images = [image], bos=True, eos=True, cropping=CROP_MODE)},
    }
    return cache_item, image


def process_image_with_refs(image, matches_ref, page_idx, out_path):
    """
    Hàm 'vỏ bọc' theo yêu cầu của bạn:
    Gọi draw_bounding_boxes để thực hiện công việc.
    """
    result_image = draw_bounding_boxes(image, matches_ref, page_idx, out_path)
    return result_image


from  app.config import MINIO_ACCESS_KEY, MINIO_BUCKET_NAME, MINIO_ENDPOINT, MINIO_SECRET_KEY
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
    img_save_dir = os.path.join(out_path, "")
    os.makedirs(img_save_dir, exist_ok=True)
    
    contents = ''
    contents_det = ''
    draw_images = []
    
    # Context cho heading trang trước
    last_heading_level = 0 

    for idx, (output, image) in enumerate(zip(outputs, images)):
        content = output.outputs[0].text
        
        # 1. Clean token thừa
        content = content.replace('<｜end▁of▁sentence｜>', '').strip()
        if SKIP_REPEAT and not content:
            continue
        
        # 2. Xử lý Image/Ref (Sửa lỗi empty image)
        matches_ref, matches_images, matches_other = re_match(content)
        
        # Kiểm tra nội hàm process_image_with_refs hoặc filter matches ở đây
        valid_refs = []
        for ref in matches_ref:
            # Giả sử ref có định dạng tọa độ [ymin, xmin, ymax, xmax]
            # Nếu tọa độ rỗng hoặc diện tích = 0 thì không add vào valid_refs
            valid_refs.append(ref)
            
        try:
            # Chỉ truyền các ref hợp lệ để tránh lỗi "empty image"
            process_image_with_refs(image, valid_refs, idx, img_save_dir)
        except Exception as e:
            # Log cụ thể trang nào bị lỗi để debug
            print(f"⚠️ Warning: Trang {idx} gặp vấn đề khi crop: {e}")

        # 3. Chuẩn hóa Markdown Context
        # Tìm heading cuối cùng để duy trì cấu trúc cho trang sau (nếu cần dùng prompt)
        found_headings = re.findall(r'^(#+)\s+', content, re.MULTILINE)
        if found_headings:
            last_heading_level = len(found_headings[-1]) # Lưu cấp độ (số dấu #)

        # 4. Replace tags
        for img_idx, match_tag in enumerate(matches_images):
            # Kiểm tra xem file ảnh có tồn tại không trước khi đặt link (tránh link chết)
            img_name = f"{idx}_{img_idx}.jpg"
            content = content.replace(match_tag, f'![](images/{img_name})\n')
        
        for match in matches_other:
            content = content.replace(match, '')

        # 5. Fix Latex & Spacing
        content = content.replace('\\coloneqq', ':=').replace('\\eqqcolon', '=: ')
        # Gom các dòng trống thừa
        content = re.sub(r'\n{3,}', '\n\n', content)

        page_marker = f'\n\n\n\n'
        contents += content + page_marker
        contents_det += content + page_marker
        draw_images.append(image)

    # # --- TỰ ĐỘNG GHI FILE (Nên mở lại đoạn này để có kết quả ngay) ---
    # try:
    #     job_id = os.path.basename(out_path.strip('/'))
    #     md_file_path = os.path.join(out_path, f"{job_id}.md")
    #     with open(md_file_path, "w", encoding="utf-8") as f:
    #         f.write(contents)
    #     print(f"✅ Đã xuất file Markdown: {md_file_path}")
    # except Exception as e:
    #     print(f"❌ Lỗi ghi file MD: {e}")
    
    return contents, contents_det, draw_images