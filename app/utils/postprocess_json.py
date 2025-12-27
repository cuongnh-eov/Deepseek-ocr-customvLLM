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

# def process_ocr_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
#     """
#     Phân tích chuỗi đầu ra DeepSeek-OCR (có thể là Markdown hoặc HTML nhúng) 
#     thành danh sách các khối cấu trúc (Blocks).
#     """
    
#     blocks = []
#     lines = markdown_text.strip().split('\n')
    
#     # Biến trạng thái để xử lý bảng Markdown
#     in_markdown_table = False
#     current_markdown_lines = []
#     table_id_counter = 1
    
#     # Biến trạng thái để xử lý đoạn văn (gộp nhiều dòng đơn lẻ)
#     current_paragraph = ""
    
#     def finalize_paragraph():
#         """Lưu đoạn văn hiện tại vào blocks nếu có nội dung."""
#         nonlocal current_paragraph
#         if current_paragraph.strip():   
#             blocks.append({
#                 "type": "paragraph",
#                 "text": current_paragraph.strip()
#             })
#             current_paragraph = ""
            
#     def finalize_markdown_table():
#         """Phân tích và lưu bảng Markdown hiện tại vào blocks."""
#         nonlocal in_markdown_table, current_markdown_lines, table_id_counter
#         if current_markdown_lines:
#             try:
#                 # Logic phân tích bảng Markdown cũ (giữ nguyên hoặc tùy chỉnh nếu cần)
#                 data_rows = [line.strip('|').split('|') for line in current_markdown_lines if not line.strip().startswith('|---|')]
                
#                 cleaned_rows = [
#                     [cell.strip() for cell in row] 
#                     for row in data_rows
#                 ]
                
#                 if len(cleaned_rows) >= 1:
#                     blocks.append({
#                         "type": "table",
#                         "table_id": f"tbl_{table_id_counter:02d}",
#                         "rows": cleaned_rows
#                     })
#                     table_id_counter += 1

#             except Exception:
#                 # Nếu parsing lỗi, đẩy nội dung thô vào paragraph
#                 finalize_paragraph()
#                 blocks.append({"type": "paragraph", "text": "\n".join(current_markdown_lines)})

#         in_markdown_table = False
#         current_markdown_lines = []
    
#     for line in lines:
#         line = line.strip()
        
#         # 1. Phát hiện Heading (Tiêu đề Markdown)
#         heading_match = re.match(r'^(#+)\s*(.*)', line)
#         if heading_match:
#             finalize_markdown_table() # Đảm bảo bảng MD trước đó đã được xử lý
#             finalize_paragraph() # Đảm bảo đoạn văn trước đó đã được xử lý
            
#             level = len(heading_match.group(1))
#             text = heading_match.group(2).strip()
            
#             blocks.append({
#                 "type": "heading",
#                 "level": level,
#                 "text": text
#             })
#             continue
            
#         # 2. Phát hiện HTML Table (Logic MỚI cho trường hợp bảng Cân Đối Kế Toán)
#         if re.search(r'<table', line, re.IGNORECASE):
#             finalize_markdown_table() # Đảm bảo bảng MD trước đó đã được xử lý
#             finalize_paragraph() # Đảm bảo đoạn văn trước đó đã được xử lý
            
#             try:
#                 table_rows = parse_html_table(line)
#                 if table_rows:
#                     blocks.append({
#                         "type": "table",
#                         "table_id": f"tbl_{table_id_counter:02d}",
#                         "rows": table_rows
#                     })
#                     table_id_counter += 1
#                 else:
#                     # Nếu không trích xuất được hàng nào, coi là paragraph
#                     current_paragraph = line
#                     finalize_paragraph()
#             except Exception:
#                 # Nếu parsing lỗi, coi là paragraph
#                 current_paragraph = line
#                 finalize_paragraph()
            
#             continue # Đã xử lý dòng này

#         # 3. Phát hiện Bảng Markdown
#         if line.startswith('|'):
#             if not in_markdown_table:
#                 finalize_paragraph()
#                 in_markdown_table = True
            
#             current_markdown_lines.append(line)
#             continue
        
#         # Nếu đang ở trong bảng MD nhưng gặp một dòng trống/không phải '|', kết thúc bảng
#         if in_markdown_table and not line:
#             finalize_markdown_table()
#             continue
            
#         # 4. Phát hiện Paragraph (Đoạn văn) hoặc Image Links
        
#         if not line: # Gặp dòng trống
#             if current_paragraph:
#                 finalize_paragraph()
#             continue
            
#         # Kiểm tra nếu là Image Link (ví dụ: ![](images/0.jpg) )
#         image_match = re.match(r'^!\[.*?\]\((.*?)\)', line)
#         if image_match:
#             finalize_markdown_table()
#             finalize_paragraph()
            
#             blocks.append({
#                 "type": "image",
#                 "source": image_match.group(1).strip()
#             })
#             continue

#         # Nếu không phải heading, table, hay link ảnh, nó là paragraph
#         if not in_markdown_table:
#             if current_paragraph:
#                 current_paragraph += " " + line
#             else:
#                 current_paragraph = line
#         else:
#             # Lỗi: nội dung lạ trong khi đang ở trạng thái bảng MD, kết thúc bảng và bắt đầu đoạn văn mới
#             finalize_markdown_table()
#             current_paragraph = line 
            
#     # Xử lý nội dung còn sót lại sau khi duyệt hết file
#     finalize_markdown_table()
#     finalize_paragraph()
        
#     return blocks



from typing import List, Dict, Any
from app.utils.utils import apply_regex_heuristics, validate_financial_rows # Import từ utils

def process_ocr_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    blocks = []
    lines = markdown_text.strip().split('\n')
    
    in_markdown_table = False
    current_markdown_lines = []
    table_id_counter = 1
    current_paragraph = ""
    
    def finalize_paragraph():
        nonlocal current_paragraph
        if current_paragraph.strip():
            # ÁP DỤNG REGEX TẠI ĐÂY
            processed_text = apply_regex_heuristics(current_paragraph.strip())
            blocks.append({"type": "paragraph", "text": processed_text})
            current_paragraph = ""
            
    def finalize_markdown_table():
        nonlocal in_markdown_table, current_markdown_lines, table_id_counter
        if current_markdown_lines:
            try:
                data_rows = [line.strip('|').split('|') for line in current_markdown_lines if not line.strip().startswith('|---|')]
                cleaned_rows = [[cell.strip() for cell in row] for row in data_rows]
                
                if len(cleaned_rows) >= 1:
                    # ÁP DỤNG VALIDATION TẠI ĐÂY
                    val_result = validate_financial_rows(cleaned_rows)
                    blocks.append({
                        "type": "table",
                        "table_id": f"tbl_{table_id_counter:02d}",
                        "rows": cleaned_rows,
                        "validation": val_result
                    })
                    table_id_counter += 1
            except Exception:
                finalize_paragraph()
                blocks.append({"type": "paragraph", "text": "\n".join(current_markdown_lines)})
        in_markdown_table = False
        current_markdown_lines = []
    
    for line in lines:
        line = line.strip()
        
        # 1. Heading
        heading_match = re.match(r'^(#+)\s*(.*)', line)
        if heading_match:
            finalize_markdown_table(); finalize_paragraph()
            blocks.append({"type": "heading", "level": len(heading_match.group(1)), "text": heading_match.group(2).strip()})
            continue
            
        # 2. HTML Table
        if re.search(r'<table', line, re.IGNORECASE):
            finalize_markdown_table(); finalize_paragraph()
            try:
                table_rows = parse_html_table(line)
                if table_rows:
                    val_result = validate_financial_rows(table_rows) # Validation cho HTML Table
                    blocks.append({"type": "table", "table_id": f"tbl_{table_id_counter:02d}", "rows": table_rows, "validation": val_result})
                    table_id_counter += 1
                else:
                    current_paragraph = line; finalize_paragraph()
            except Exception:
                current_paragraph = line; finalize_paragraph()
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
            
        # 4. Image/Paragraph
        if not line:
            if current_paragraph: finalize_paragraph()
            continue
            
        image_match = re.match(r'^!\[.*?\]\((.*?)\)', line)
        if image_match:
            finalize_markdown_table(); finalize_paragraph()
            blocks.append({"type": "image", "source": image_match.group(1).strip()})
            continue

        if not in_markdown_table:
            current_paragraph = (current_paragraph + " " + line) if current_paragraph else line
        else:
            finalize_markdown_table()
            current_paragraph = line 
            
    finalize_markdown_table()
    finalize_paragraph()
    return blocks