import re
import json
from typing import List, Dict, Any

def parse_html_table(html_string: str) -> List[List[str]]:
    """
    Hàm phụ trợ: Phân tích một chuỗi HTML Table đơn giản
    (<table><tr><td>...</td></tr>...</table>) thành List[List[str]].
    """
    rows = []
    
    # Sử dụng non-greedy regex để tìm tất cả các hàng (<tr>...</tr>)
    row_matches = re.findall(r'<tr.*?>(.*?)</tr>', html_string, re.IGNORECASE | re.DOTALL)
    
    for row_content in row_matches:
        # Sử dụng non-greedy regex để tìm tất cả các ô (<td>...</td>) trong hàng
        cell_matches = re.findall(r'<td.*?>(.*?)</td>', row_content, re.IGNORECASE | re.DOTALL)
        
        # Làm sạch và thêm vào hàng
        cleaned_cells = [cell.strip() for cell in cell_matches]
        rows.append(cleaned_cells)
        
    return rows


from typing import List, Dict, Any
from app.utils.utils import apply_regex_heuristics, validate_financial_rows # Import từ utils

def process_ocr_to_blocks(markdown_text: str, page_idx: int = 0) -> List[Dict[str, Any]]:
    """Process OCR output theo format content_list chuẩn."""
    content_list = []
    lines = markdown_text.strip().split('\n')
    
    in_markdown_table = False
    current_markdown_lines = []
    current_paragraph = ""
    table_caption = []
    image_caption = []
    image_counter = 0  # Track image index per page
    
    def finalize_paragraph():
        nonlocal current_paragraph
        if current_paragraph.strip():
            processed_text = apply_regex_heuristics(current_paragraph.strip())
            content_list.append({
                "type": "text",
                "text": processed_text,
                "page_idx": page_idx
            })
            current_paragraph = ""
            
    def finalize_markdown_table():
        nonlocal in_markdown_table, current_markdown_lines, table_caption
        if current_markdown_lines:
            try:
                data_rows = [line.strip('|').split('|') for line in current_markdown_lines if not line.strip().startswith('|---|')]
                cleaned_rows = [[cell.strip() for cell in row] for row in data_rows]
                
                if len(cleaned_rows) >= 1:
                    val_result = validate_financial_rows(cleaned_rows)
                    # Tạo markdown table string
                    table_body = '\n'.join(['|' + '|'.join(row) + '|' for row in cleaned_rows])
                    content_list.append({
                        "type": "table",
                        "table_body": table_body,
                        "table_caption": table_caption if table_caption else [],
                        "validation": val_result,
                        "page_idx": page_idx
                    })
                    table_caption = []
            except Exception:
                finalize_paragraph()
                content_list.append({
                    "type": "text",
                    "text": "\n".join(current_markdown_lines),
                    "page_idx": page_idx
                })
        in_markdown_table = False
        current_markdown_lines = []
    
    for line in lines:
        line = line.strip()
        
        # 1. Heading (kết hợp với paragraph tiếp theo)
        heading_match = re.match(r'^(#+)\s*(.*)', line)
        if heading_match:
            finalize_markdown_table()
            finalize_paragraph()
            # Heading coi như text
            current_paragraph = heading_match.group(2).strip()
            continue
            
        # 2. HTML Table
        if re.search(r'<table', line, re.IGNORECASE):
            finalize_markdown_table()
            finalize_paragraph()
            try:
                table_rows = parse_html_table(line)
                if table_rows:
                    val_result = validate_financial_rows(table_rows)
                    table_body = '\n'.join(['|' + '|'.join(row) + '|' for row in table_rows])
                    content_list.append({
                        "type": "table",
                        "table_body": table_body,
                        "table_caption": table_caption if table_caption else [],
                        "validation": val_result,
                        "page_idx": page_idx
                    })
                    table_caption = []
                else:
                    current_paragraph = line
                    finalize_paragraph()
            except Exception:
                current_paragraph = line
                finalize_paragraph()
            continue

        # 3. Markdown Table
        if line.startswith('|'):
            if not in_markdown_table:
                finalize_paragraph()
                in_markdown_table = True
            current_markdown_lines.append(line)
            continue
        
        if in_markdown_table and not line:
            finalize_markdown_table()
            continue
            
        # 4. Image
        if not line:
            if current_paragraph:
                finalize_paragraph()
            continue
            
        image_match = re.match(r'^!\[.*?\]\((.*?)\)', line)
        if image_match:
            finalize_markdown_table()
            finalize_paragraph()
            img_path = image_match.group(1).strip()
            
            # Reformat: images/something.png -> images/{page_idx}_{image_counter}.png
            # Extract file extension
            ext = img_path.split('.')[-1] if '.' in img_path else 'png'
            reformatted_path = f"images/{page_idx}_{image_counter}.{ext}"
            
            content_list.append({
                "type": "image",
                "img_path": reformatted_path,
                "image_caption": image_caption if image_caption else [],
                "page_idx": page_idx
            })
            image_counter += 1
            image_caption = []
            continue

        if not in_markdown_table:
            current_paragraph = (current_paragraph + " " + line) if current_paragraph else line
        else:
            finalize_markdown_table()
            current_paragraph = line 
            
    finalize_markdown_table()
    finalize_paragraph()
    return content_list