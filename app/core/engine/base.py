from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseOCRParser(ABC):
    """
    Base class cho tất cả OCR engines (Deepseek, Docling, MinerU, v.v).
    Mỗi engine phải chuẩn hóa output thành định dạng block chung.
    """

    @abstractmethod
    def check_installation(self) -> bool:
        """Kiểm tra xem tool (model/CLI) đã được cài đặt chưa"""
        pass

    @abstractmethod
    def parse(self, input_path: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        Parse PDF/Document thành danh sách blocks chuẩn.
        
        Mỗi block có định dạng:
        {
            "type": "text" | "table" | "image",
            "page_idx": int,
            ... (thêm các field khác tùy type)
        }
        """
        pass