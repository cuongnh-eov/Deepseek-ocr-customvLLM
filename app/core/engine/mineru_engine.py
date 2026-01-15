import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from app.core.engine.base import BaseOCRParser
from app.utils.format_output import format_output_with_metadata, save_output_json

_log = logging.getLogger(__name__)


class MineruExecutionError(Exception):
    """Catch mineru error"""

    def __init__(self, return_code, error_msg):
        self.return_code = return_code
        self.error_msg = error_msg
        super().__init__(
            f"Mineru command failed with return code {return_code}: {error_msg}"
        )


class MineruEngine(BaseOCRParser):
    """
    MinerU 2.0 OCR Parser - Subprocess-based CLI
    Converts Mineru output format to standardized OCR format (compatible with Deepseek)
    
    Mineru generates: {filename}_content_list.json with blocks
    We convert to: {filename}.json with standardized format (metadata + content)
    """

    def check_installation(self) -> bool:
        """Check if mineru CLI is installed"""
        try:
            subprocess.run(["mineru", "--version"], capture_output=True, check=True)
            return True
        except:
            return False

    def _run_mineru_command(
        self,
        input_path: str,
        output_dir: str,
        method: str = "auto",
        lang: Optional[str] = None,
        backend: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        """
        Run mineru command line tool
        
        Args:
            input_path: Path to input PDF/image file
            output_dir: Output directory path
            method: Parsing method (auto, txt, ocr)
            lang: Document language for OCR optimization
            backend: Parsing backend
            device: Inference device (cpu, cuda, etc.)
        """
        cmd = [
            "mineru",
            "-p", str(input_path),
            "-o", str(output_dir),
            "-m", method,
        ]

        if backend:
            cmd.extend(["-b", backend])
        if lang:
            cmd.extend(["-l", lang])
        if device:
            cmd.extend(["-d", device])

        _log.info(f"🔄 Executing mineru command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't raise on non-zero exit
                timeout=600  # 10 minutes timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                _log.error(f"Mineru error: {error_msg}")
                raise MineruExecutionError(result.returncode, error_msg)

            _log.info("[MinerU] ✅ Command executed successfully")

        except subprocess.TimeoutExpired:
            raise RuntimeError("Mineru command timeout (10 minutes exceeded)")
        except FileNotFoundError:
            raise RuntimeError(
                "mineru command not found. Install with: pip install -U 'mineru[core]'"
            )
        except MineruExecutionError:
            raise
        except Exception as e:
            _log.error(f"Unexpected error running mineru: {e}")
            raise RuntimeError(f"Mineru execution failed: {e}") from e

    def _read_mineru_output(
        self,
        output_dir: Path,
        file_stem: str,
        method: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        Read Mineru output files and convert to standardized format
        
        Mineru generates:
        - {file_stem}_content_list.json
        - {file_stem}.md
        - images/ directory
        
        Returns standardized blocks list
        """
        # Check different possible paths where mineru outputs files
        json_file = None
        images_dir = None

        # Try direct output
        direct_json = output_dir / f"{file_stem}_content_list.json"
        if direct_json.exists():
            json_file = direct_json
            images_dir = output_dir / "images"

        # Try subdirectory: output_dir/{file_stem}/{method}/
        subdir_json = output_dir / file_stem / method / f"{file_stem}_content_list.json"
        if subdir_json.exists():
            json_file = subdir_json
            images_dir = subdir_json.parent / "images"

        # Try nested subdirectory: output_dir/{file_stem}/{method}/{file_stem}*/
        if not json_file:
            nested_search = list((output_dir / file_stem / method).glob(f"{file_stem}*"))
            for path in nested_search:
                if path.is_dir():
                    candidate = path / f"{file_stem}_content_list.json"
                    if candidate.exists():
                        json_file = candidate
                        images_dir = path / "images"
                        break

        # Try recursive search as fallback
        if not json_file:
            results = list(output_dir.rglob(f"{file_stem}_content_list.json"))
            if results:
                json_file = results[0]
                images_dir = json_file.parent / "images"

        if not json_file or not json_file.exists():
            _log.warning(f"Mineru JSON file not found in {output_dir}")
            return []

        # Read JSON content list from Mineru
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                mineru_blocks = json.load(f)
        except Exception as e:
            _log.error(f"Failed to read Mineru JSON: {e}")
            return []

        # Convert Mineru format to standardized format
        standardized_blocks = self._convert_mineru_blocks(mineru_blocks, images_dir)
        return standardized_blocks

    def _convert_mineru_blocks(
        self,
        mineru_blocks: List[Dict[str, Any]],
        images_dir: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert Mineru block format to standardized format
        
        Mineru blocks contain: type, bbox, content/img_path/table_body, etc.
        We convert to: type, text/img_path/table_body, page_idx, image_caption
        """
        standardized = []
        page_idx = 0

        for block in mineru_blocks:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type", "").lower()
            
            try:
                if block_type == "text":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "text",
                            "text": text,
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "header":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "text",
                            "text": text,
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "title":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "text",
                            "text": text,
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "image":
                    img_path = block.get("img_path", "")
                    if img_path:
                        standardized.append({
                            "type": "image",
                            "img_path": img_path,
                            "image_caption": block.get("image_caption", []),
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "table":
                    table_body = block.get("table_body", "")
                    if table_body:
                        standardized.append({
                            "type": "table",
                            "table_body": table_body,
                            "table_caption": block.get("table_caption", ""),
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "equation":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "equation",
                            "text": text,
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "code":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "text",
                            "text": f"```\n{text}\n```",
                            "page_idx": block.get("page_idx", 0)
                        })

                elif block_type == "list":
                    text = block.get("text", "").strip()
                    if text:
                        standardized.append({
                            "type": "text",
                            "text": text,
                            "page_idx": block.get("page_idx", 0)
                        })

            except Exception as e:
                _log.warning(f"Failed to convert block: {e}")
                continue

        return standardized

    def parse(self, input_path: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        Parse PDF/image using MinerU 2.0
        
        Args:
            input_path: Path to PDF or image file
            output_dir: Output directory (like /outputs/{job_id})
            
        Returns:
            List of standardized blocks compatible with Deepseek format
        """
        input_path = Path(input_path)
        file_stem = input_path.stem

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Create output directory
        work_dir = Path(output_dir) / file_stem / "mineru"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Extract job_id from output_dir path
        try:
            job_id = Path(output_dir).name if Path(output_dir).name else "mineru"
        except:
            job_id = "mineru"

        _log.info(f"🔄 Parsing with MinerU: {input_path}")

        try:
            # Determine file type and method
            file_ext = input_path.suffix.lower()
            if file_ext in [".pdf"]:
                method = "auto"  # Auto-detect between txt and ocr
            elif file_ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]:
                method = "ocr"
            else:
                method = "auto"

            # Run mineru command
            self._run_mineru_command(
                input_path=str(input_path),
                output_dir=str(work_dir),
                method=method,
            )

            # Read and convert mineru output
            blocks = self._read_mineru_output(work_dir, file_stem, method=method)
            blocks = [b for b in blocks if b is not None]

            # Format with metadata (standardized format)
            total_pages = len(set(b.get("page_idx", 0) for b in blocks)) if blocks else 0
            output_data = format_output_with_metadata(
                blocks,
                input_path.name,
                total_pages
            )

            # Save blocks as JSON (standardized format with metadata)
            blocks_file = work_dir / "blocks.json"
            save_output_json(output_data, blocks_file)

            _log.info(f"✅ MinerU extracted {len(blocks)} blocks")
            _log.info(f"💾 Saved to {blocks_file}")
            return blocks

        except MineruExecutionError as e:
            _log.error(f"MinerU execution error: {e}")
            raise RuntimeError(f"MinerU parsing failed: {e}")
        except Exception as e:
            _log.error(f"Error: {e}")
            raise
