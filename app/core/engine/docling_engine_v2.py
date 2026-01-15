import json
import logging
import subprocess
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from PIL import Image
import io

from app.core.engine.base import BaseOCRParser
from app.utils.format_output import format_output_with_metadata, save_output_json

_log = logging.getLogger(__name__)


class DoclingEngineV2(BaseOCRParser):
    """
    Docling V2 - Using subprocess CLI (optimized, stable)
    Sử dụng subprocess để gọi docling CLI command
    """

    def check_installation(self) -> bool:
        """Check if docling CLI is installed"""
        try:
            subprocess.run(["docling", "--version"], capture_output=True, check=True)
            return True
        except:
            return False

    def _save_image_as_jpg(self, png_path: Path, jpg_path: Path) -> None:
        """Convert PNG to JPG (quality 95, match Deepseek format)"""
        try:
            img = Image.open(png_path)
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            img.save(jpg_path, 'JPEG', quality=95)
            png_path.unlink()  # Delete PNG
            _log.info(f"✓ Converted PNG to JPG: {jpg_path.name}")
        except Exception as e:
            _log.error(f"Failed to convert PNG to JPG: {e}")
            # Keep PNG if conversion fails
            jpg_path = png_path
    
    def _generate_markdown_from_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        """Generate markdown from blocks (compatible with Deepseek format)"""
        md_lines = []
        current_page = -1
        
        for block in blocks:
            page_idx = block.get("page_idx", 0)
            
            # Add page break if page changed
            if page_idx != current_page:
                if current_page != -1:
                    md_lines.append("\n---\n")  # Page separator
                current_page = page_idx
            
            block_type = block.get("type")
            
            if block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    md_lines.append(text)
            
            elif block_type == "equation":
                text = block.get("text", "").strip()
                if text:
                    md_lines.append(f"$$\n{text}\n$$\n")
            
            elif block_type == "image":
                img_path = block.get("img_path", "")
                img_caption = block.get("image_caption", "")
                if img_path:
                    caption_text = f' "{img_caption}"' if img_caption else ""
                    md_lines.append(f"![{caption_text}]({img_path})\n")
            
            elif block_type == "table":
                table_body = block.get("table_body", "").strip()
                table_caption = block.get("table_caption", "")
                if table_body:
                    if table_caption:
                        md_lines.append(f"**{table_caption}**\n")
                    md_lines.append(table_body)
                    md_lines.append("")
        
        return "\n".join(md_lines)

    def parse(self, input_path: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        Parse PDF using Docling CLI
        
        Args:
            input_path: Path to PDF
            output_dir: Output directory
            
        Returns:
            List of standardized blocks
        """
        input_path = Path(input_path)
        file_stem = input_path.stem
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Create output directory
        work_dir = Path(output_dir) / file_stem / "docling"
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract job_id from output_dir path (parent directory name)
        # output_dir is like /outputs/{job_id}, extract {job_id}
        try:
            job_id = Path(output_dir).name if Path(output_dir).name else "docling"
        except:
            job_id = "docling"
        
        _log.info(f"🔄 Parsing: {input_path}")
        
        try:
            # Run docling CLI for JSON output
            cmd = ["docling", "--output", str(work_dir), "--to", "json", str(input_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Read JSON file
            json_file = work_dir / f"{file_stem}.json"
            if not json_file.exists():
                _log.warning(f"JSON file not found: {json_file}")
                return []
            
            with open(json_file, "r", encoding="utf-8") as f:
                docling_data = json.load(f)
            
            # Parse blocks recursively
            blocks = self._read_from_block_recursive(
                docling_data.get("body", {}),
                "body",
                work_dir,
                0,
                "0",
                docling_data
            )
            
            blocks = [b for b in blocks if b is not None]
            
            # Convert PNG images to JPG (match Deepseek format) with correct path
            self._convert_images_to_jpg(work_dir, blocks, job_id, file_stem)
            
            # Generate markdown from blocks
            markdown_content = self._generate_markdown_from_blocks(blocks)
            markdown_file = work_dir / f"{file_stem}.md"
            with open(markdown_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            _log.info(f"💾 Markdown saved: {markdown_file}")
            
            # Format output with metadata (giống Deepseek)
            total_pages = docling_data.get("num_pages", 0)
            output_data = format_output_with_metadata(
                blocks,
                input_path.name,
                total_pages
            )
            
            # Save blocks as JSON (standardized format with metadata)
            blocks_file = work_dir / "blocks.json"
            save_output_json(output_data, blocks_file)
            
            _log.info(f"✅ Extracted {len(blocks)} blocks")
            _log.info(f"💾 Saved to {blocks_file}")
            return blocks
        
        except subprocess.CalledProcessError as e:
            _log.error(f"Docling CLI error: {e.stderr}")
            raise RuntimeError(f"Docling parsing failed: {e}")
        except Exception as e:
            _log.error(f"Error: {e}")
            raise
    
    def _convert_images_to_jpg(self, work_dir: Path, blocks: List[Dict[str, Any]], job_id: str, file_stem: str) -> None:
        """Convert all PNG images to JPG format and update paths to match Deepseek format: ocr-results/{job_id}/images/{page_idx}_{idx}.jpg"""
        image_dir = work_dir / "images"
        if not image_dir.exists():
            return
        
        for block in blocks:
            if block.get("type") == "image":
                img_path = block.get("img_path", "")
                if img_path.endswith(".png"):
                    # Convert PNG to JPG
                    png_file = image_dir / f"{block.get('img_path').split('/')[-1]}"
                    jpg_file = png_file.with_suffix(".jpg")
                    
                    if png_file.exists():
                        self._save_image_as_jpg(png_file, jpg_file)
                        # Update block path to match Deepseek format: ocr-results/{job_id}/images/{page_idx}_{idx}.jpg
                        page_idx = block.get("page_idx", 0)
                        filename = jpg_file.name
                        block["img_path"] = f"ocr-results/{job_id}/images/{filename}"
                        block["image_caption"] = []  # Ensure it's a list, not string

    def _read_from_block_recursive(
        self,
        block: Dict[str, Any],
        block_type: str,
        output_dir: Path,
        cnt: int,
        num: str,
        docling_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Recursive parser for Docling block structure (same as V1)
        
        Docling model_dump() structure with references (cref):
        {
            "body": {
                "children": [
                    {"cref": "#/texts/0"},
                    {"cref": "#/pictures/1"},
                    {"cref": "#/tables/2"}
                ]
            },
            "texts": [...],
            "pictures": [...],
            "tables": [...]
        }
        
        Note: Uses "cref" key instead of "$ref" in model_dump() output
        """
        content_list = []
        
        # If no children, process this block
        if not block.get("children"):
            cnt += 1
            result = self._read_from_block(block, block_type, output_dir, cnt, num)
            if result:
                content_list.append(result)
        else:
            # If has children and not body/groups, process this block first
            if block_type not in ["groups", "body"]:
                cnt += 1
                result = self._read_from_block(block, block_type, output_dir, cnt, num)
                if result:
                    content_list.append(result)
            
            # Process children
            children = block.get("children", [])
            for child in children:
                cnt += 1
                
                # Parse reference: "#/pictures/0" using both $ref and cref keys
                ref = child.get("$ref") or child.get("cref", "")
                if not ref or "/" not in ref:
                    continue
                
                # Remove leading #/ if present
                if ref.startswith("#/"):
                    ref = ref[2:]
                elif ref.startswith("#"):
                    ref = ref[1:]
                
                parts = ref.split("/")
                if len(parts) < 2:
                    continue
                
                member_type = parts[0]  # "texts", "pictures", "tables"
                try:
                    member_index = int(parts[1])
                except (ValueError, IndexError):
                    continue
                
                # Get member from docling_data
                if member_type not in docling_data:
                    continue
                
                member_list = docling_data[member_type]
                if member_index >= len(member_list):
                    continue
                
                member_block = member_list[member_index]
                
                # Recursively process
                content_list.extend(
                    self._read_from_block_recursive(
                        member_block,
                        member_type,
                        output_dir,
                        cnt,
                        str(member_index),
                        docling_data
                    )
                )
        
        return content_list

    def _read_from_block(
        self,
        block: Dict[str, Any],
        block_type: str,
        output_dir: Path,
        cnt: int,
        num: str
    ) -> Optional[Dict[str, Any]]:
        """
        Convert single Docling block to internal format
        (Same as V1 implementation)
        """
        page_idx = cnt // 10
        
        if block_type == "texts":
            # Handle text blocks
            label = block.get("label", "paragraph")
            text = block.get("orig", "")
            
            if label == "formula":
                return {
                    "type": "equation",
                    "text": text,
                    "page_idx": page_idx
                }
            else:
                return {
                    "type": "text",
                    "text": text,
                    "page_idx": page_idx
                }
        
        elif block_type == "pictures":
            # Handle image blocks
            try:
                image_data = block.get("image", {})
                if isinstance(image_data, dict):
                    uri = image_data.get("uri", "")
                    if uri.startswith("data:"):
                        # Base64 encoded image
                        base64_str = uri.split(",")[1]
                        
                        # Create images directory
                        image_dir = output_dir / "images"
                        image_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Use format: {page_idx}_{image_idx}.png (e.g., 0_0.png, 1_0.png)
                        image_filename = f"{page_idx}_{num}.png"
                        image_path = image_dir / image_filename
                        with open(image_path, "wb") as f:
                            f.write(base64.b64decode(base64_str))
                        
                        return {
                            "type": "image",
                            "img_path": f"images/{image_filename}",
                            "image_caption": [],  # Return as list, not string
                            "page_idx": page_idx
                        }
                
                # Fallback
                return {
                    "type": "image",
                    "img_path": block.get("path", ""),
                    "image_caption": [],  # Return as list, not string
                    "page_idx": page_idx
                }
            
            except Exception as e:
                _log.warning(f"Failed to process image {num}: {e}")
                return {
                    "type": "text",
                    "text": f"[Image: {block.get('caption', 'unknown')}]",
                    "page_idx": page_idx
                }
        
        elif block_type == "tables":
            # Handle table blocks
            try:
                table_data = block.get("data", [])
                if table_data:
                    table_rows = []
                    for row in table_data:
                        if isinstance(row, list):
                            table_rows.append([str(cell).strip() for cell in row])
                    
                    if table_rows:
                        table_body = '\n'.join(['|' + '|'.join(row) + '|' for row in table_rows])
                        return {
                            "type": "table",
                            "table_body": table_body,
                            "table_caption": block.get("caption", ""),
                            "page_idx": page_idx
                        }
                
                return {
                    "type": "table",
                    "table_body": "",
                    "table_caption": block.get("caption", ""),
                    "page_idx": page_idx
                }
            
            except Exception as e:
                _log.warning(f"Failed to process table {num}: {e}")
                return {
                    "type": "text",
                    "text": f"[Table: {block.get('caption', 'unknown')}]",
                    "page_idx": page_idx
                }
        
        return None

