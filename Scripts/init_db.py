# init_db.py
import os
from app.db import engine, Base
from app.models import OCRJob

def init():
    print("🛠 Đang khởi tạo database...")
    Base.metadata.create_all(bind=engine)
    print("✅ Đã tạo bảng ocr_jobs thành công!")

if __name__ == "__main__":
    init()