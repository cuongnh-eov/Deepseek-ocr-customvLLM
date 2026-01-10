from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

# --- 1. Schema cho luồng Upload (Giai đoạn đầu) ---
class OCRResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None

    class Config:
        from_attributes = True

# --- 2. Định nghĩa các Block nội dung (Dùng cho kết quả chi tiết) ---
class BlockBase(BaseModel):
    type: str

class HeadingBlock(BlockBase):
    type: str = "heading"
    level: int
    text: str

class ParagraphBlock(BlockBase):
    type: str = "paragraph"
    text: str

class TableBlock(BlockBase):
    type: str = "table"
    table_id: str
    rows: List[List[str]]
#
# --- 3. Định nghĩa Trang, Metadata và Body ---
class ContentPage(BaseModel):
    page_number: int
    # Sử dụng Union để Swagger hiểu được các loại block khác nhau
    blocks: List[Union[HeadingBlock, ParagraphBlock, TableBlock, Any]]

class DocumentMetadata(BaseModel):
    source_filename: str
    total_pages: int
    processed_at: datetime # Chuyển sang datetime để chuẩn hóa

class DocumentBody(BaseModel):
    metadata: DocumentMetadata
    content: List[ContentPage]

# --- 4. Schema Response Cuối cùng (Dùng cho endpoint lấy kết quả) ---
class DocumentResponseSchema(BaseModel):
    status: str = "success"
    document: Optional[DocumentBody] = None
    num_pages: int
    processing_time: float
    # Thêm trường này để mapping với DB nếu cần
    job_id: str 

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "status": "success",
                "job_id": "uuid-123-456",
                "num_pages": 1,
                "processing_time": 5.45,
                "document": {
                    "metadata": {
                        "source_filename": "sample.pdf",
                        "total_pages": 1,
                        "processed_at": "2026-01-10T16:07:36.781286"
                    },
                    "content": []
                }
            }
        }