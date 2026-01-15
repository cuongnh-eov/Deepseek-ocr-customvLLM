"""
OCR Engine Factory - Rẽ nhánh cho Deepseek, MinerU, hoặc Docling V2
Deepseek + MinerU chính (2 nhánh) → Docling fallback khi lỗi
"""
import logging
from typing import Literal, Optional, Union
from app.core.engine.base import BaseOCRParser

_log = logging.getLogger(__name__)


def get_ocr_engine(engine_type: Literal["deepseek", "mineru", "docling"]) -> Optional[BaseOCRParser]:
    """
    Factory function để lấy OCR engine.
    
    Args:
        engine_type: "deepseek" (None), "mineru", hoặc "docling"
        
    Returns:
        BaseOCRParser instance hoặc None nếu là deepseek
    """
    engine_type = engine_type.lower().strip()
    
    if engine_type == "deepseek":
        _log.info("[Factory] Deepseek engine selected (None - main pipeline)")
        return None
    
    elif engine_type == "mineru":
        from app.core.engine.mineru_engine import MineruEngine
        _log.info("[Factory] MinerU engine selected")
        return MineruEngine()
    
    elif engine_type == "docling":
        from app.core.engine.docling_engine_v2 import DoclingEngineV2
        _log.info("[Factory] Docling V2 engine selected (fallback)")
        return DoclingEngineV2()
    
    else:
        raise ValueError(f"Unknown engine: {engine_type}. Use 'deepseek', 'mineru', or 'docling'")


class OCREngineFactory:
    """
    Factory class để quản lý OCR engines.
    Hỗ trợ multiple engines với instance caching.
    
    Flow: Deepseek/MinerU chính → Docling fallback khi lỗi
    """
    
    _engines = {}
    
    @classmethod
    def get_engine(cls, engine_type: Literal["deepseek", "mineru", "docling"]) -> Optional[BaseOCRParser]:
        """
        Lấy engine instance (cached).
        
        Args:
            engine_type: Loại engine - "deepseek" (None), "mineru", hoặc "docling"
            
        Returns:
            BaseOCRParser instance (hoặc None nếu là deepseek)
        """
        if engine_type not in cls._engines:
            cls._engines[engine_type] = get_ocr_engine(engine_type)
        return cls._engines[engine_type]
    
    @classmethod
    def is_deepseek(cls, engine_type: str) -> bool:
        """Kiểm tra xem engine type có phải Deepseek không"""
        return engine_type.lower().strip() == "deepseek"
    
    @classmethod
    def is_mineru(cls, engine_type: str) -> bool:
        """Kiểm tra xem engine type có phải MinerU không"""
        return engine_type.lower().strip() == "mineru"
    
    @classmethod
    def is_docling(cls, engine_type: str) -> bool:
        """Kiểm tra xem engine type có phải Docling không"""
        return engine_type.lower().strip() == "docling"
    
    @classmethod
    def clear_cache(cls):
        """Xóa cache engines"""
        cls._engines.clear()
    
    @classmethod
    def list_available_engines(cls) -> list:
        """Liệt kê tất cả engines có sẵn"""
        return ["deepseek", "mineru", "docling"]
    
    @classmethod
    def get_fallback_engine(cls) -> Optional[BaseOCRParser]:
        """Lấy fallback engine (Docling)"""
        return cls.get_engine("docling")


