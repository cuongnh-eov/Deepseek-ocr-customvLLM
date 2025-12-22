import os
import fitz
import img2pdf
import io
import re
from tqdm import tqdm
import torch
from concurrent.futures import ThreadPoolExecutor


from configs.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, SKIP_REPEAT, MAX_CONCURRENCY, NUM_WORKERS, CROP_MODE

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from deepseek_ocr import DeepseekOCRForCausalLM

from vllm.model_executor.models.registry import ModelRegistry

from vllm import LLM, SamplingParams
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor
from process.image_process import detect_and_correct_skew, crop_pixels_all_sides


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


def draw_bounding_boxes(image, refs, jdx):

    image_width, image_height = image.size
    img_draw = image.copy()
    draw = ImageDraw.Draw(img_draw)

    overlay = Image.new('RGBA', img_draw.size, (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(overlay)
    
    #     except IOError:
    font = ImageFont.load_default()

    img_idx = 0
    
    for i, ref in enumerate(refs):
        try:
            result = extract_coordinates_and_label(ref, image_width, image_height)
            if result:
                label_type, points_list = result
                
                color = (np.random.randint(0, 200), np.random.randint(0, 200), np.random.randint(0, 255))

                color_a = color + (20, )
                for points in points_list:
                    x1, y1, x2, y2 = points

                    x1 = int(x1 / 999 * image_width)
                    y1 = int(y1 / 999 * image_height)

                    x2 = int(x2 / 999 * image_width)
                    y2 = int(y2 / 999 * image_height)

                    if label_type == 'image':
                        try:
                            cropped = image.crop((x1, y1, x2, y2))
                            cropped.save(f"{OUTPUT_PATH}/images/{jdx}_{img_idx}.jpg")
                        except Exception as e:
                            print(e)
                            pass
                        img_idx += 1
                        
                    try:
                        if label_type == 'title':
                            draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
                            draw2.rectangle([x1, y1, x2, y2], fill=color_a, outline=(0, 0, 0, 0), width=1)
                        else:
                            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                            draw2.rectangle([x1, y1, x2, y2], fill=color_a, outline=(0, 0, 0, 0), width=1)

                        text_x = x1
                        text_y = max(0, y1 - 15)
                            
                        text_bbox = draw.textbbox((0, 0), label_type, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        draw.rectangle([text_x, text_y, text_x + text_width, text_y + text_height], 
                                    fill=(255, 255, 255, 30))
                        
                        draw.text((text_x, text_y), label_type, font=font, fill=color)
                    except:
                        pass
        except:
            continue
    img_draw.paste(overlay, (0, 0), overlay)
    return img_draw




def process_single_image(image, prompt):
    image = detect_and_correct_skew(image)   #them xu ly anh nghieng  
    """single image"""
    prompt_in = prompt
    cache_item = {
        "prompt": prompt_in,
        "multi_modal_data": {"image": DeepseekOCRProcessor().tokenize_with_images(images = [image], bos=True, eos=True, cropping=CROP_MODE)},
    }
    return cache_item


def process_image_with_refs(image, matches_ref, page_idx, save_dir):
    """
    Sửa lỗi name 'r' is not defined và thực hiện Crop ảnh chính xác.
    """
    width, height = image.size
    img_idx = 0
    
    # matches_ref là kết quả từ re_match, mỗi phần tử là 1 tuple (full_tag, label, coords_str)
    for ref in matches_ref:
        try:
            label_type = ref[1] # 'image', 'title', vv.
            if label_type != 'image':
                continue
                
            # Chuyển chuỗi "[[y1, x1, y2, x2]]" thành list
            points_list = eval(ref[2])
            
            for points in points_list:
                y1, x1, y2, x2 = points

                # Chuyển đổi tọa độ hệ 1000 sang pixel thực tế
                left = int(x1 / 1000 * width)
                top = int(y1 / 1000 * height)
                right = int(x2 / 1000 * width)
                bottom = int(y2 / 1000 * height)

                # Thực hiện CROP (Đây là phần quan trọng nhất để tiết kiệm dung lượng)
                cropped = image.crop((left, top, right, bottom))
                
                img_name = f"{page_idx}_{img_idx}.jpg"
                save_path = os.path.join(save_dir, img_name)
                cropped.save(save_path, "JPEG", quality=85)
                
                img_idx += 1
        except Exception as e:
            print(f"Lỗi Crop ảnh trang {page_idx}: {e}")
            continue
            
    return image # Trả về ảnh gốc nếu bạn vẫn muốn dùng cho việc khác

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