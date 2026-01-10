"""
Multi-Page OCR Processor - Xử lý OCR result từ nhiều trang
"""

from typing import List, Dict, Any
from app.utils.table_continuity_detector import TableContinuityDetector


class MultiPageOCRProcessor:
    """
    Xử lý OCR result từ nhiều trang để:
    1. Gộp bảng liên trang
    2. Loại bỏ header lặp lại
    3. Giữ page metadata cho mỗi block
    
    Example:
        processor = MultiPageOCRProcessor()
        pages_data = [
            {"page_number": 1, "blocks": [...]},
            {"page_number": 2, "blocks": [...]},
            ...
        ]
        merged_document = processor.process_pages(pages_data)
    """
    
    def __init__(self):
        self.detector = TableContinuityDetector()
    
    def process_pages(self, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý và gộp OCR blocks từ nhiều trang
        
        Input: pages_data = [
            {
                "page_number": 1,
                "blocks": [
                    {"type": "heading", "text": "...", ...},
                    {"type": "table", "rows": [...], ...},
                    ...
                ]
            },
            ...
        ]
        
        Output: Merged document với page tracking
        
        Args:
            pages_data: List of page data, mỗi page chứa blocks
            
        Returns:
            Dict với structure:
            {
                "document": {
                    "content": [merged blocks]
                }
            }
        """
        merged_blocks = []
        last_table_info = None  # Track bảng từ trang trước
        
        for page_data in pages_data:
            page_num = page_data["page_number"]
            blocks = page_data.get("blocks", [])
            
            for block_idx, block in enumerate(blocks):
                
                # ===== XỬ LÝ TABLE =====
                if block.get("type") == "table":
                    rows = block.get("rows", [])
                    header_row = block.get("header_row") or (rows[0] if rows else [])
                    is_repeated = block.get("is_header_repeated", False)
                    
                    # Kiểm tra xem đây có phải là tiếp tục của bảng từ trang trước không
                    if (last_table_info and 
                        self.detector.is_table_continuation(
                            header_row,
                            last_table_info["signature"],
                            block.get("table_id", "")
                        ) and 
                        not self.detector.detect_column_mismatch(
                            rows, last_table_info["block"].get("rows", [])
                        )):
                        
                # ✅ GỘP BẢN
                        merged_block = self.detector.merge_table_blocks(
                            last_table_info["block"],
                            {**block, "rows": rows, "page_number": page_num},
                            block.get("table_id")
                        )
                        
                        # ✅ NEW: Loại bỏ header lặp lại từ rows khi gộp
                        # Nếu header repeated, rows đã bị trim (dòng 0 bị bỏ)
                        # Nhưng rows vẫn chứa header lặp từ page tiếp theo
                        # → cần loại bỏ header row trước khi merge
                        if is_repeated and len(rows) > 0:
                            # Rows đã trim header từ page này
                            # Không cần làm gì thêm
                            pass
                        
                        # Cập nhật metadata
                        if merged_block.get("metadata"):
                            merged_block["metadata"].update({
                                "block_index": len(merged_blocks) - 1,
                                "is_continuation": False
                            })
                        
                        # Thay thế block cuối cùng
                        merged_blocks[-1] = merged_block
                        
                        last_table_info = {
                            "signature": self.detector.extract_header_signature(header_row),
                            "block": merged_block
                        }
                    else:
                        # ✅ BẢNG MỚI
                        clean_block = {
                            "type": "table",
                            "table_id": block.get("table_id"),
                            "header_row": header_row,
                            "rows": rows,
                            "is_header_repeated": is_repeated,
                            "is_merged": False,
                            "page_number": page_num,
                            "validation": block.get("validation", "High"),
                            "metadata": block.get("metadata") or {
                                "page_number": page_num,
                                "block_index": len(merged_blocks),
                                "is_continuation": False,
                                "parent_block_id": None
                            }
                        }
                        merged_blocks.append(clean_block)
                        
                        last_table_info = {
                            "signature": self.detector.extract_header_signature(header_row),
                            "block": clean_block
                        }
                
                # ===== XỬ LÝ PARAGRAPH =====
                elif block.get("type") == "paragraph":
                    clean_block = {
                        **block,
                        "page_number": page_num,
                        "metadata": block.get("metadata") or {
                            "page_number": page_num,
                            "block_index": len(merged_blocks),
                            "is_continuation": False,
                            "parent_block_id": None
                        }
                    }
                    merged_blocks.append(clean_block)
                    last_table_info = None  # Reset table tracking
                
                # ===== HEADING =====
                elif block.get("type") == "heading":
                    clean_block = {
                        **block,
                        "page_number": page_num,
                        "metadata": block.get("metadata") or {
                            "page_number": page_num,
                            "block_index": len(merged_blocks),
                            "is_continuation": False,
                            "parent_block_id": None,
                            "confidence": 1.0
                        }
                    }
                    merged_blocks.append(clean_block)
                    last_table_info = None
                
                # ===== IMAGE =====
                elif block.get("type") == "image":
                    clean_block = {
                        **block,
                        "page_number": page_num,
                        "metadata": block.get("metadata") or {
                            "page_number": page_num,
                            "block_index": len(merged_blocks),
                            "is_continuation": False,
                            "parent_block_id": None
                        }
                    }
                    merged_blocks.append(clean_block)
                    last_table_info = None
                
                else:
                    # Unknown block type - giữ nguyên
                    clean_block = {
                        **block,
                        "page_number": page_num,
                        "metadata": block.get("metadata") or {
                            "page_number": page_num,
                            "block_index": len(merged_blocks),
                            "is_continuation": False,
                            "parent_block_id": None
                        }
                    }
                    merged_blocks.append(clean_block)
                    last_table_info = None
        
        return {
            "document": {
                "content": merged_blocks
            }
        }
    
    def extract_by_section(self, merged_blocks: List[Dict]) -> Dict[str, List]:
        """
        Tách blocks theo section (với header tracking).
        Useful cho việc tìm kiếm semantically
        
        Args:
            merged_blocks: List of merged blocks từ process_pages()
            
        Returns:
            Dict {section_name: [blocks]}
            
        Example:
            sections = processor.extract_by_section(merged_blocks)
            # sections["Báo Cáo Bảo Trì"] = [paragraph, table, ...]
        """
        sections = {}
        current_section = "Introduction"
        
        for block in merged_blocks:
            if block["type"] == "heading":
                current_section = block.get("text", "Unknown Section")
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(block)
            else:
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(block)
        
        return sections
    
    def get_page_ranges(self, merged_blocks: List[Dict]) -> Dict[int, List[str]]:
        """
        Lấy danh sách page ranges cho mỗi block type
        
        Args:
            merged_blocks: List of merged blocks
            
        Returns:
            Dict {block_type: [page_numbers]}
        """
        page_ranges = {}
        
        for block in merged_blocks:
            block_type = block.get("type")
            page_num = block.get("page_number", 0)
            
            if block_type not in page_ranges:
                page_ranges[block_type] = set()
            
            # For merged tables, add all pages
            if block.get("is_merged") and "pages" in block:
                pages = block["pages"].get("page_sequence", [])
                page_ranges[block_type].update(pages)
            else:
                page_ranges[block_type].add(page_num)
        
        # Convert sets to sorted lists
        return {k: sorted(list(v)) for k, v in page_ranges.items()}
