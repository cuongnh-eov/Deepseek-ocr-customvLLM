"""
Utility để format output blocks thành JSON chuẩn (giống Deepseek format)
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def format_output_with_metadata(
    blocks: List[Dict[str, Any]],
    source_filename: str,
    total_pages: int = 0
) -> Dict[str, Any]:
    """
    Format blocks thành JSON schema với metadata (giống Deepseek)
    
    Args:
        blocks: List of standardized blocks
        source_filename: Tên file gốc
        total_pages: Tổng số trang
        
    Returns:
        Dict với metadata + content
    """
    return {
        "metadata": {
            "source_filename": source_filename,
            "total_pages": total_pages,
            "processed_at": datetime.utcnow().isoformat() + "Z"
        },
        "content": blocks
    }


def save_output_json(
    output_data: Dict[str, Any],
    output_file: Path
) -> None:
    """
    Save output JSON to file
    
    Args:
        output_data: Dict với metadata + content
        output_file: Path to output JSON file
    """
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
