import re
from typing import List, Dict, Any
from app.utils.utils import apply_regex_heuristics, validate_financial_rows
from app.utils.table_continuity_detector import TableContinuityDetector


def process_ocr_to_blocks(markdown_text: str, page_number: int = 1) -> List[Dict[str, Any]]:
    blocks = []
    lines = markdown_text.strip().split('\n')
    
    in_markdown_table = False
    current_markdown_lines = []
    table_id_counter = 1
    current_paragraph = ""
    detector = TableContinuityDetector()
    
    def finalize_paragraph():
        nonlocal current_paragraph
        if current_paragraph.strip():
            # ÁP DỤNG REGEX TẠI ĐÂY
            processed_text = apply_regex_heuristics(current_paragraph.strip())
            blocks.append({
                "type": "paragraph",
                "text": processed_text,
                "page_number": page_number,
                "metadata": {
                    "page_number": page_number,
                    "block_index": len(blocks),
                    "is_continuation": False,
                    "parent_block_id": None
                }
            })
            current_paragraph = ""
            
    def finalize_markdown_table():
        nonlocal in_markdown_table, current_markdown_lines, table_id_counter
        if current_markdown_lines:
            try:
                data_rows = [line.strip('|').split('|') for line in current_markdown_lines if not line.strip().startswith('|---|')]
                cleaned_rows = [[cell.strip() for cell in row] for row in data_rows]
                
                if len(cleaned_rows) >= 1:
                    # ✅ NEW: Detect header repetition
                    header_idx, is_repeated = detector.detect_header_repetition(cleaned_rows)
                    
                    if is_repeated and header_idx == 0:
                        # Remove repeated header (từ dòng thứ 2 trở đi)
                        cleaned_rows = cleaned_rows[1:]
                    
                    # Extract header
                    header_row = cleaned_rows[0] if cleaned_rows else []
                    
                    # ÁP DỤNG VALIDATION TẠI ĐÂY
                    val_result = validate_financial_rows(cleaned_rows)
                    blocks.append({
                        "type": "table",
                        "table_id": f"tbl_{table_id_counter:02d}",
                        "header_row": header_row,
                        "rows": cleaned_rows,
                        "is_header_repeated": is_repeated,
                        "page_number": page_number,
                        "validation": val_result,
                        "metadata": {
                            "page_number": page_number,
                            "block_index": len(blocks),
                            "is_continuation": False,
                            "parent_block_id": None
                        }
                    })
                    table_id_counter += 1
            except Exception as e:
                finalize_paragraph()
                blocks.append({
                    "type": "paragraph",
                    "text": "\n".join(current_markdown_lines),
                    "page_number": page_number,
                    "metadata": {
                        "page_number": page_number,
                        "block_index": len(blocks),
                        "is_continuation": False,
                        "parent_block_id": None
                    }
                })
        in_markdown_table = False
        current_markdown_lines = []
    
    for line in lines:
        line = line.strip()
        
        # 1. Heading
        heading_match = re.match(r'^(#+)\s*(.*)', line)
        if heading_match:
            finalize_markdown_table(); finalize_paragraph()
            blocks.append({
                "type": "heading",
                "level": len(heading_match.group(1)),
                "text": heading_match.group(2).strip(),
                "page_number": page_number,
                "metadata": {
                    "page_number": page_number,
                    "block_index": len(blocks),
                    "is_continuation": False,
                    "parent_block_id": None
                }
            })
            continue
            
        # 2. HTML Table
        if re.search(r'<table', line, re.IGNORECASE):
            finalize_markdown_table(); finalize_paragraph()
            try:
                table_rows = parse_html_table(line)
                if table_rows and len(table_rows) > 0:
                    # ✅ NEW: Detect header repetition for HTML too
                    header_idx, is_repeated = detector.detect_header_repetition(table_rows)
                    if is_repeated and header_idx == 0:
                        table_rows = table_rows[1:]
                    
                    header_row = table_rows[0] if table_rows else []
                    val_result = validate_financial_rows(table_rows)
                    
                    blocks.append({
                        "type": "table",
                        "table_id": f"tbl_{table_id_counter:02d}",
                        "header_row": header_row,
                        "rows": table_rows,
                        "is_header_repeated": is_repeated,
                        "page_number": page_number,
                        "validation": val_result,
                        "metadata": {
                            "page_number": page_number,
                            "block_index": len(blocks),
                            "is_continuation": False,
                            "parent_block_id": None
                        }
                    })
                    table_id_counter += 1
                    continue  # ✅ Important! Skip the rest, don't fall back to paragraph
                else:
                    # If parse fails, treat as paragraph
                    current_paragraph = line
            except Exception as e:
                print(f"Error parsing HTML table: {e}")
                current_paragraph = line
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
            if current_paragraph: finalize_paragraph()
            continue
            
        image_match = re.match(r'^!\[.*?\]\((.*?)\)', line)
        if image_match:
            finalize_markdown_table(); finalize_paragraph()
            blocks.append({
                "type": "image",
                "source": image_match.group(1).strip(),
                "page_number": page_number,
                "metadata": {
                    "page_number": page_number,
                    "block_index": len(blocks),
                    "is_continuation": False,
                    "parent_block_id": None,
                    "confidence": 1.0
                }
            })
            continue

        if not in_markdown_table:
            current_paragraph = (current_paragraph + " " + line) if current_paragraph else line
        else:
            finalize_markdown_table()
            current_paragraph = line 
            
    finalize_markdown_table()
    finalize_paragraph()
    return blocks


def parse_html_table(html_text: str) -> List[List[str]]:
    """
    Parse HTML table từ text và convert thành list of rows.
    
    Xử lý:
    - <table>...<tr><td>...</td></tr>...</table>
    - rowspan và colspan (simplify bằng cách expand)
    
    Args:
        html_text: HTML table string
        
    Returns:
        List[List[str]] của rows
    """
    rows = []
    
    try:
        # Extract all <tr> tags
        tr_pattern = r'<tr[^>]*>(.*?)</tr>'
        tr_matches = re.findall(tr_pattern, html_text, re.IGNORECASE | re.DOTALL)
        
        if not tr_matches:
            return []
        
        for tr_content in tr_matches:
            # Extract all <td> và <th> tags
            td_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
            td_matches = re.findall(td_pattern, tr_content, re.IGNORECASE | re.DOTALL)
            
            if td_matches:
                # Clean mỗi cell: remove HTML tags, decode entities
                cells = []
                for td_content in td_matches:
                    # Remove inner HTML tags
                    cell_text = re.sub(r'<[^>]+>', '', td_content)
                    # Decode HTML entities
                    cell_text = cell_text.replace('&nbsp;', ' ')
                    cell_text = cell_text.replace('&lt;', '<')
                    cell_text = cell_text.replace('&gt;', '>')
                    cell_text = cell_text.replace('&amp;', '&')
                    # Strip whitespace
                    cell_text = cell_text.strip()
                    cells.append(cell_text)
                
                if cells:  # Only add non-empty rows
                    rows.append(cells)
        
        return rows
    
    except Exception as e:
        print(f"Error parsing HTML table: {e}")
        return []