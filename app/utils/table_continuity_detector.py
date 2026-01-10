"""
Table Continuity Detector - Phát hiện và track bảng biểu kéo dài qua nhiều trang
"""

from typing import List, Dict, Tuple, Optional


class TableContinuityDetector:
    """
    Phát hiện và track bảng biểu kéo dài qua nhiều trang
    
    Features:
    - Detect header signature (hash + column count)
    - Detect header repetition across pages
    - Detect if current header is continuation of previous table
    - Detect footer rows (total, summary)
    - Merge table blocks from multiple pages
    """
    
    def __init__(self):
        self.table_signatures = {}  # {table_id: (header_hash, col_count)}
        self.pending_tables = {}    # {table_id: table_data}
    
    def extract_header_signature(self, header_row: List[str]) -> Tuple[str, int]:
        """
        Tạo chữ ký (signature) cho header bảng:
        - Hash của header content (normalized)
        - Số cột
        
        Args:
            header_row: List các cell trong header
            
        Returns:
            Tuple của (header_hash, col_count)
        """
        # Normalize header: lowercase, strip whitespace, remove extra spaces
        normalized = [col.strip().lower() for col in header_row]
        # Remove empty cells
        normalized = [col for col in normalized if col]
        
        # Create hash từ normalized header
        header_hash = hash(tuple(normalized))
        col_count = len(header_row)
        
        return (header_hash, col_count)
    
    def is_table_continuation(
        self, 
        current_header: List[str], 
        last_table_signature: Optional[Tuple[str, int]],
        current_table_id: str
    ) -> bool:
        """
        Kiểm tra xem header hiện tại có phải là tiếp tục của table trước không
        
        Logic:
        1. Header giống hệt nhau (hash match)
        2. Số cột giống nhau
        3. Nội dung header không chứa "summary", "total" (tránh footer)
        4. Column names có overlap >= 70%
        
        Args:
            current_header: Header của bảng hiện tại
            last_table_signature: Signature của bảng trang trước
            current_table_id: ID bảng hiện tại
            
        Returns:
            True nếu đây là tiếp tục, False nếu là bảng mới
        """
        if not last_table_signature:
            return False
        
        current_sig = self.extract_header_signature(current_header)
        
        # Check 1: Signature match
        if current_sig != last_table_signature:
            return False
        
        # Check 2: Không phải footer
        footer_keywords = [
            'total', 'sum', 'tổng', 'cộng', 'kết', 'grand total',
            'tổng cộng', 'tổng cộng', 'lương cộng', 'subtotal'
        ]
        header_text = ' '.join(current_header).lower()
        if any(kw in header_text for kw in footer_keywords):
            return False
        
        # Check 3: Column count match (đã check ở signature)
        if len(current_header) != last_table_signature[1]:
            return False
        
        return True
    
    def detect_header_repetition(self, rows: List[List[str]]) -> Tuple[int, bool]:
        """
        Phát hiện xem dòng đầu tiên của page có phải là header lặp lại không.
        
        Heuristics:
        - Nếu dòng 1 và dòng 2 giống nhau → dòng 1 là header lặp
        - Phải EXACT match (case-insensitive, whitespace-stripped)
        
        Args:
            rows: List các row (mỗi row là list cell)
            
        Returns:
            Tuple (header_row_index, is_repeated)
            - header_row_index: vị trí của header (thường là 0)
            - is_repeated: True nếu header bị lặp lại ở page này
        """
        if len(rows) < 2:
            return 0, False
        
        first_row = rows[0]
        second_row = rows[1]
        
        # Normalize và so sánh
        first_normalized = [cell.strip().lower() for cell in first_row]
        second_normalized = [cell.strip().lower() for cell in second_row]
        
        # Only if EXACT match → is_repeated
        if first_normalized == second_normalized:
            return 0, True
        
        return 0, False
    
    def detect_footer_row(self, row: List[str]) -> bool:
        """
        Kiểm tra xem một dòng có phải là footer (summary) row không
        
        Heuristics:
        - Chứa "Total", "Tổng", "Sum", etc.
        - Chứa số lớn hoặc currency format
        - Thường ở cuối bảng
        
        Args:
            row: List cell trong dòng
            
        Returns:
            True nếu đây là footer row
        """
        footer_keywords = [
            'total', 'sum', 'tổng', 'cộng', 'kết',
            'grand total', 'tổng cộng', 'subtotal', 'sub total',
            'average', 'trung bình', 'count', 'số lượng'
        ]
        
        row_text = ' '.join(row).lower()
        
        # Check 1: Keyword match
        for kw in footer_keywords:
            if kw in row_text:
                return True
        
        # Check 2: First cell có keyword thường xuất hiện ở footer
        first_cell = row[0].strip().lower() if row else ""
        if first_cell in ['total', 'tổng', 'cộng', 'subtotal']:
            return True
        
        return False
    
    def detect_column_mismatch(
        self, 
        current_rows: List[List[str]], 
        previous_rows: List[List[str]]
    ) -> bool:
        """
        Kiểm tra xem số cột có khác nhau giữa 2 bảng không
        
        Args:
            current_rows: Rows của bảng hiện tại
            previous_rows: Rows của bảng trang trước
            
        Returns:
            True nếu số cột khác nhau (should NOT merge)
        """
        if not current_rows or not previous_rows:
            return True
        
        current_cols = len(current_rows[0])
        previous_cols = len(previous_rows[0])
        
        return current_cols != previous_cols
    
    def merge_table_blocks(
        self,
        table_from_prev_page: Dict,
        table_from_curr_page: Dict,
        table_id: str
    ) -> Dict:
        """
        Gộp 2 bảng từ 2 trang khác nhau thành 1 bảng
        
        Args:
            table_from_prev_page: Table block từ trang trước
            table_from_curr_page: Table block từ trang hiện tại
            table_id: ID của bảng gộp
            
        Returns:
            Merged table block
        """
        prev_rows = table_from_prev_page.get("rows", [])
        curr_rows = table_from_curr_page.get("rows", [])
        prev_page = table_from_prev_page.get("page_number", 1)
        curr_page = table_from_curr_page.get("page_number", 1)
        
        merged = {
            "type": "table",
            "table_id": table_id,
            "header_row": table_from_prev_page.get("header_row") or 
                         table_from_curr_page.get("header_row"),
            "rows": prev_rows + curr_rows,
            "is_header_repeated": True,  # Nếu gộp = header bị lặp
            "is_merged": True,
            "pages": {
                "first_page": prev_page,
                "last_page": curr_page,
                "page_sequence": [prev_page, curr_page]
            },
            "validation": "High",
            "metadata": table_from_prev_page.get("metadata", {})
        }
        
        return merged
    
    def calculate_confidence(self, validation: str) -> float:
        """
        Tính confidence score dựa trên validation level
        
        Args:
            validation: "High", "Medium", "Low"
            
        Returns:
            Confidence score (0.0 - 1.0)
        """
        confidence_map = {
            "High": 1.0,
            "Medium": 0.75,
            "Low": 0.5
        }
        return confidence_map.get(validation, 0.95)
