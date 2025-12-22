"""
app/db.py
- Tạo kết nối Postgres và session cho SQLAlchemy.
- API và Worker cùng dùng chung để cập nhật trạng thái job.
"""


import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session,declarative_base


DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://ocr_cuong:ocr_cuong@localhost:5432/ocr_cuong_db')

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()

def get_db():
    """Tạo session DB cho mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()




