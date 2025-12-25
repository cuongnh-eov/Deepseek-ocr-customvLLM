# app/schemas.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- 1. Định nghĩa Block (Khối nội dung) ---
# Sử dụng Union hoặc chỉ định các trường chung nhất
class BlockBase(BaseModel):
    """Base class cho mọi khối nội dung."""
    type: str = Field(..., description="Loại khối: heading, paragraph, table, image.")
    
# Cấu trúc cho Heading
class HeadingBlock(BlockBase):
    type: str = "heading"
    level: int = Field(..., description="Mức độ tiêu đề (1-6).")
    text: str = Field(..., description="Nội dung văn bản của tiêu đề.")

# Cấu trúc cho Paragraph
class ParagraphBlock(BlockBase):
    type: str = "paragraph"
    text: str = Field(..., description="Nội dung văn bản của đoạn văn.")

# Cấu trúc cho Table
class TableBlock(BaseModel):
    type: str = "table"
    table_id: str = Field(..., description="ID định danh bảng trong tài liệu.")
    # Định dạng rows: list của list strings (ví dụ: [["Header A", "Header B"], ["Value 1", "Value 2"]])
    rows: List[List[str]] = Field(..., description="Danh sách các hàng, mỗi hàng là danh sách các ô (cell text).")

# --- 2. Định nghĩa Trang (Content Page) ---
class ContentPage(BaseModel):
    page_number: int
    # Union cho phép blocks chứa bất kỳ loại Block nào đã định nghĩa
    blocks: List[Any] = Field(..., description="Danh sách các khối nội dung (heading, paragraph, table) trên trang.")

# --- 3. Định nghĩa Metadata ---
class DocumentMetadata(BaseModel):
    source_filename: str
    total_pages: int
    processed_at: str

# --- 4. Định nghĩa Tài liệu (Document) ---
class DocumentBody(BaseModel):
    metadata: DocumentMetadata
    content: List[ContentPage]

# --- 5. Định nghĩa Schema Response Cuối cùng ---
class DocumentResponseSchema(BaseModel):
    status: str = "success"
    document: DocumentBody
    num_pages: int
    processing_time: float
    output_file: str

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "document": {
                    "metadata": {
                        "source_filename": "sample_sop.pdf",
                        "total_pages": 1,
                        "processed_at": "2025-11-26T10:00:00Z"
                    },
                    "content": [
                        {
                            "page_number": 1,
                            "blocks": [
                                {"type": "heading", "level": 1, "text": "Chapter 1: Introduction"},
                                {"type": "paragraph", "text": "This is the content of the first paragraph..."},
                                {"type": "table", "table_id": "tbl_01", "rows": [["Header A", "Header B"], ["Value 1", "Value 2"]]}
                            ]
                        }
                    ]
                },
                "num_pages": 1,
                "processing_time": 5.45,
                "output_file": "/path/to/output.json"
            }
        }