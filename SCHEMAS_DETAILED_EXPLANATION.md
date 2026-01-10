# 📋 Giải Thích Chi Tiết File schemas.py

## 📌 Tổng Quan
File `app/schemas/schemas.py` định nghĩa **Pydantic Models** - cấu trúc dữ liệu cho FastAPI. Chúng dùng để:
1. **Validate** input/output API
2. **Generate** Swagger documentation tự động
3. **Serialize** dữ liệu Python → JSON

---

## 🔍 Chi Tiết Từng Class

### 1️⃣ OCRResponse
```python
class OCRResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None

    class Config:
        from_attributes = True
```

**Tác dụng:**
- Response khi user upload file PDF
- Trả về `job_id` để track tiến độ xử lý

**Tham chiếu:**
- **File:** `app/api/routes/ocr.py` (line 28)
- **Endpoint:** `POST /api/v1/ocr/upload`
- **Tác dụng cụ thể:**
  ```python
  @ocr_router.post("/upload", response_model=OCRResponse)
  async def upload_document(file: UploadFile = File(...), ...):
      # Nếu return data không match OCRResponse → Validation Error
      return {
          "job_id": job_id,
          "status": JobStatus.QUEUED,
          "message": "Tài liệu đã được tiếp nhận thành công."
      }
  ```
- **Workflow:**
  1. Client upload file
  2. Server generate `job_id`
  3. Return `OCRResponse` (validate bởi Pydantic)
  4. Client nhận job_id để query kết quả sau

---

### 2️⃣ BlockBase + HeadingBlock + ParagraphBlock + TableBlock
```python
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
```

**Tác dụng:**
- Định nghĩa các kiểu content blocks trong kết quả OCR
- Dùng Inheritance (`BlockBase`) để chung `type` field

**Tham chiếu:**
- **File:** `app/api/routes/ocr.py` (line 98)
- **Endpoint:** `GET /api/v1/ocr/result/{job_id}`
- **Tác dụng cụ thể:**
  ```python
  @ocr_router.get("/result/{job_id}", response_model=DocumentResponseSchema)
  def get_full_result(job_id: str, db: Session = Depends(get_db)):
      # DocumentResponseSchema chứa ContentPage → blocks
      # blocks chứa Union[HeadingBlock, ParagraphBlock, TableBlock]
      # Swagger sẽ show 3 loại block này
      return job
  ```
- **Workflow (trong ocr_service.py):**
  ```python
  # app/services/ocr_service.py - Khi generate JSON output
  blocks.append({
      "type": "heading",
      "level": 1,
      "text": "Tiêu đề",
      ...
  })  # → Match HeadingBlock schema
  
  blocks.append({
      "type": "table",
      "table_id": "tbl_01",
      "rows": [...],
      ...
  })  # → Match TableBlock schema
  ```

---

### 3️⃣ ContentPage
```python
class ContentPage(BaseModel):
    page_number: int
    blocks: List[Union[HeadingBlock, ParagraphBlock, TableBlock, Any]]
```

**Tác dụng:**
- Nhóm tất cả blocks của 1 page
- `page_number`: số trang (1-indexed)
- `blocks`: danh sách blocks trong trang

**Tham chiếu:**
- **File:** `app/api/routes/ocr.py` (line 98)
- **Workflow:**
  ```python
  # Trong DocumentBody.content:
  [
    ContentPage(
      page_number=1,
      blocks=[HeadingBlock(...), ParagraphBlock(...), TableBlock(...)]
    ),
    ContentPage(
      page_number=2,
      blocks=[ParagraphBlock(...)]
    )
  ]
  ```

---

### 4️⃣ DocumentMetadata
```python
class DocumentMetadata(BaseModel):
    source_filename: str
    total_pages: int
    processed_at: datetime
```

**Tác dụng:**
- Metadata về tài liệu gốc
- `source_filename`: tên file upload
- `total_pages`: số trang PDF
- `processed_at`: thời điểm xử lý

**Tham chiếu:**
- **File:** `app/services/ocr_service.py`
- **Tác dụng cụ thể:**
  ```python
  # Khi tạo response JSON
  response_data = {
      "document": {
          "metadata": {
              "job_id": job_id,
              "source_filename": job.filename,
              "total_pages": total_pages,
              "processed_at": datetime.now(timezone.utc).isoformat()
          },
          "content": merged_document["document"]["content"]
      }
  }
  ```

---

### 5️⃣ DocumentBody
```python
class DocumentBody(BaseModel):
    metadata: DocumentMetadata
    content: List[ContentPage]
```

**Tác dụng:**
- Chứa toàn bộ nội dung tài liệu
- `metadata`: thông tin tài liệu
- `content`: danh sách pages

**Workflow:**
```
DocumentBody
├── metadata (DocumentMetadata)
│   ├── source_filename
│   ├── total_pages
│   └── processed_at
└── content (List[ContentPage])
    ├── ContentPage(page_number=1)
    │   └── blocks
    │       ├── HeadingBlock
    │       ├── ParagraphBlock
    │       └── TableBlock
    └── ContentPage(page_number=2)
        └── blocks
```

---

### 6️⃣ DocumentResponseSchema (Schema Response Chính)
```python
class DocumentResponseSchema(BaseModel):
    status: str = "success"
    document: Optional[DocumentBody] = None
    num_pages: int
    processing_time: float
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
                        "processed_at": "2025-11-26T10:00:00Z"
                    },
                    "content": []
                }
            }
        }
```

**Tác dụng:**
- Response cuối cùng của endpoint `/result/{job_id}`
- `from_attributes = True`: Map các attributes từ DB object → schema
- `json_schema_extra`: Example cho Swagger docs

**Tham chiếu:**
- **File:** `app/api/routes/ocr.py` (line 98)
- **Endpoint:** `GET /api/v1/ocr/result/{job_id}`
- **Tác dụng cụ thể:**
  ```python
  @ocr_router.get("/result/{job_id}", response_model=DocumentResponseSchema)
  def get_full_result(job_id: str, db: Session = Depends(get_db)):
      job = db.query(OCRJob).filter(OCRJob.job_id == job_id).first()
      
      if not job:
          raise HTTPException(status_code=404, detail="Không tìm thấy mã Job.")
      
      # FastAPI tự động validate & convert job object → DocumentResponseSchema
      # Nếu thiếu field hoặc kiểu sai → Lỗi 500
      return job
  ```

---

## 🔗 Luồng Dữ Liệu Hoàn Chỉnh

```
1. USER UPLOAD FILE
   ↓
2. ocr.py - upload_document()
   ├─ Validate: file extension, file size
   ├─ Create job in DB
   ├─ Return OCRResponse ← SCHEMA 1
   │  {
   │    "job_id": "abc123",
   │    "status": "QUEUED",
   │    "message": "..."
   │  }
   └─ Push to Celery Queue
   
3. ocr_service.py - process_ocr_document()
   ├─ Gọi vLLM để OCR mỗi page
   ├─ Tạo blocks: HeadingBlock, ParagraphBlock, TableBlock ← SCHEMA 2-4
   ├─ Group into ContentPage ← SCHEMA 5
   ├─ Tạo DocumentBody ← SCHEMA 6
   └─ Save JSON to MinIO
   
4. USER QUERY RESULT
   ↓
5. ocr.py - get_full_result()
   ├─ Fetch job from DB
   ├─ Return DocumentResponseSchema ← SCHEMA 7 (chứa tất cả)
   │  {
   │    "status": "success",
   │    "job_id": "abc123",
   │    "num_pages": 11,
   │    "processing_time": 84.78,
   │    "document": {
   │      "metadata": {...},
   │      "content": [ContentPage, ContentPage, ...]
   │    }
   │  }
   └─ Client nhận JSON
```

---

## 📊 Bảng Tóm Tắt

| Schema | Dùng Ở | Tác Dụng | Validation |
|--------|--------|---------|-----------|
| **OCRResponse** | POST /upload | Response upload | ✓ Validate job_id, status |
| **HeadingBlock** | JSON output | Heading content | ✓ level, text required |
| **ParagraphBlock** | JSON output | Paragraph content | ✓ text required |
| **TableBlock** | JSON output | Table content | ✓ rows format |
| **ContentPage** | JSON structure | Group blocks per page | ✓ page_number required |
| **DocumentMetadata** | JSON output | File metadata | ✓ datetime format |
| **DocumentBody** | JSON structure | Full document | ✓ Nested validation |
| **DocumentResponseSchema** | GET /result | Final API response | ✓ from_attributes=True |

---

## ⚠️ Validation Errors

Nếu code return data không match schema:

```python
# ❌ Error: "field is required"
return {
    "job_id": "abc123",
    "status": "QUEUED"
    # Thiếu "message" (nhưng optional, nên OK)
}

# ❌ Error: "value is not a valid string"
return {
    "job_id": 123,  # ← Phải là str, không phải int!
    "status": "QUEUED",
    "message": None
}

# ❌ Error: "value is not a valid datetime"
return {
    "processed_at": "2025-11-26T10:00:00Z",  # ← Phải là datetime object
}

# ✅ OK
return {
    "job_id": "abc123",
    "status": "QUEUED",
    "message": "Done"
}
```

---

## 🎯 Kết Luận

Schemas **không chỉ** hiển thị trên API - nó **kiểm soát** luồng logic:
1. **Validate** data trước response
2. **Convert** kiểu (str → datetime)
3. **Ensure** data integrity
4. **Generate** API docs tự động

Nếu không có schemas, server có thể return data sai kiểu → Client fail.
