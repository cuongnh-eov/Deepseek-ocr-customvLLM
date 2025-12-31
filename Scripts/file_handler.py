import os
from pathlib import Path
# Đảm bảo đường dẫn import utils chuẩn xác
from app.utils.utils import pil_to_pdf_img2pdf

def prepare_output_dirs(output_path):
    """Tạo cấu trúc thư mục lưu trữ kết quả"""
    os.makedirs(output_path, exist_ok=True)
    os.makedirs(os.path.join(output_path, 'images'), exist_ok=True)

def get_output_paths(job_id, output_path):
    """
    Lấy đường dẫn các file đầu ra dựa trên job_id để đồng bộ với Database.
    Sử dụng job_id làm tên file để tránh trùng lặp và dễ quản lý.
    """
    return {
        'mmd_det': os.path.join(output_path, f'{job_id}_det.mmd'),
        'mmd': os.path.join(output_path, f'{job_id}.md'), # Sửa .mmd thành .md để API dễ nhận diện
        'pdf': os.path.join(output_path, f'{job_id}_layouts.pdf'),
        'images': os.path.join(output_path, 'images')
    }

def save_outputs(contents, contents_det, draw_images, output_paths):
    """
    Ghi tất cả kết quả ra đĩa cứng.
    """
    try:
        # 1. Lưu các file Markdown
        with open(output_paths['mmd_det'], 'w', encoding='utf-8') as f:
            f.write(contents_det)
        
        with open(output_paths['mmd'], 'w', encoding='utf-8') as f:
            f.write(contents)
        
        # 2. Xuất PDF vẽ các ô nhận diện (Layout Detection) nếu có ảnh
        if draw_images and len(draw_images) > 0:
            pil_to_pdf_img2pdf(draw_images, output_paths['pdf'])
            print(f"✅ Saved PDF Layouts: {output_paths['pdf']}")
        
        print(f"✅ Saved Markdown: {output_paths['mmd']}")
        return True
    except Exception as e:
        print(f"❌ Error saving outputs: {e}")
        return False