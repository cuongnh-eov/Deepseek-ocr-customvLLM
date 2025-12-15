import os
import io
import time
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import torch

from configs.config import INPUT_PATH, OUTPUT_PATH, PROMPT
from app.model_init import llm, sampling_params
from app.processor import preprocess_batch, generate_ocr
from app.postprocess_md import process_ocr_output
from app.file_handler import prepare_output_dirs, get_output_paths, save_outputs
from app.utils import pdf_to_images_high_quality
import re

from app.postprocess_json import process_ocr_to_blocks
from app.schemas import DocumentResponseSchema
# ============ FASTAPI APP ============
app = FastAPI(
    title="DeepSeek OCR API",
    description="OCR API sử dụng DeepSeek-OCR",
    version="1.0.0"
)

# ============ SERVER METRICS ============
server_metrics = {
    "start_time": datetime.now().isoformat(),
    "total_requests": 0,
    "total_pages_processed": 0,
    "total_processing_time": 0.0,
    "request_history": []
}


class RequestMetrics:
    """Track metrics cho mỗi request"""
    
    def __init__(self):
        self.metrics = {}
        self.start_time = time.time()
    
    def mark_step(self, step_name):
        """Mark start of a step"""
        self.metrics[step_name] = {
            'start': time.time(),
            'vram_start': torch.cuda.memory_allocated() / 1024**3
        }
    
    def end_step(self, step_name):
        """End a step"""
        if step_name in self.metrics:
            elapsed = time.time() - self.metrics[step_name]['start']
            vram_end = torch.cuda.memory_allocated() / 1024**3
            vram_used = vram_end - self.metrics[step_name]['vram_start']
            
            self.metrics[step_name]['elapsed'] = elapsed
            self.metrics[step_name]['vram_end'] = vram_end
            self.metrics[step_name]['vram_used'] = vram_used
    
    def get_total_time(self):
        """Get total processing time"""
        return time.time() - self.start_time
    
    def get_peak_vram(self):
        """Get peak VRAM usage"""
        peak = 0
        for step_data in self.metrics.values():
            if 'vram_end' in step_data:
                if step_data['vram_end'] > peak:
                    peak = step_data['vram_end']
        return peak


def extract_content(text):
    # """Extract content from OCR output"""
    # if '<｜end▁of▁sentence｜>' in text:
    #     text = text.replace('<｜end▁of▁sentence｜>', '')
    
    # text = text.replace('\\coloneqq', ':=')
    # text = text.replace('\\eqqcolon', '=:')
    # text = text.replace('\n\n\n\n', '\n\n')
    # text = text.replace('\n\n\n', '\n\n')
    
    # return text
    # Step 1: Xóa EOS token
    if '<｜end▁of▁sentence｜>' in text:
        text = text.replace('<｜end▁of▁sentence｜>', '')
    
    # Step 2: Detect references
    pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
    matches = re.findall(pattern, text, re.DOTALL)
    
    matches_image = []
    matches_other = []
    for a_match in matches:
        if '<|ref|>image<|/ref|>' in a_match[0]:
            matches_image.append(a_match[0])
        else:
            matches_other.append(a_match[0])
    
    # Step 3: Replace image references
    for img_idx, match in enumerate(matches_image):
        text = text.replace(match, f'![](images/{img_idx}.jpg)\n')
    
    # Step 4: Clean up other references
    for match in matches_other:
        text = text.replace(match, '')
    
    # Step 5: Replace special characters
    text = text.replace('\\coloneqq', ':=')
    text = text.replace('\\eqqcolon', '=:')
    
    # Step 6: Clean newlines
    text = text.replace('\n\n\n\n', '\n\n')
    text = text.replace('\n\n\n', '\n\n')
    
    return text


# ============ ENDPOINTS ============

@app.post("/ocr/markdown")
async def ocr_markdown(file: UploadFile = File(...)):
    """OCR PDF và trả về Markdown"""
    try:
        request_metrics = RequestMetrics()
        
        temp_dir = f"/tmp/ocr_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)
        temp_pdf = f"{temp_dir}/{file.filename}"
        
        print(f'[API] POST /ocr/markdown - {file.filename}')
        
        # Save uploaded file
        request_metrics.mark_step('SAVE_UPLOAD')
        with open(temp_pdf, "wb") as buffer:
            buffer.write(await file.read())
        request_metrics.end_step('SAVE_UPLOAD')
        
        # Convert PDF to images
        request_metrics.mark_step('PDF_TO_IMAGES')
        images = pdf_to_images_high_quality(temp_pdf)
        request_metrics.end_step('PDF_TO_IMAGES')
        
        # Pre-process
        request_metrics.mark_step('PREPROCESS')
        batch_inputs = preprocess_batch(images, PROMPT)
        request_metrics.end_step('PREPROCESS')
        
        # OCR inference
        request_metrics.mark_step('OCR_INFERENCE')
        outputs = generate_ocr(llm, batch_inputs, sampling_params)
        request_metrics.end_step('OCR_INFERENCE')
        
        # Create output directory
        output_dir = f"{OUTPUT_PATH}/ocr_{int(time.time())}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Post-process
        request_metrics.mark_step('POSTPROCESS')
        contents = ''
        
        for output in outputs:
            raw_text = output.outputs[0].text
            cleaned_text = extract_content(raw_text)
            contents += cleaned_text + '\n<--- Page Split --->\n'
        
        request_metrics.end_step('POSTPROCESS')
        
        # Save markdown
        request_metrics.mark_step('SAVE_OUTPUT')
        markdown_path = f"{output_dir}/{Path(file.filename).stem}.md"
        os.makedirs(output_dir, exist_ok=True)
        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write(contents)
        request_metrics.end_step('SAVE_OUTPUT')
        
        total_time = request_metrics.get_total_time()
        
        # Update metrics
        server_metrics["total_requests"] += 1
        server_metrics["total_pages_processed"] += len(images)
        server_metrics["total_processing_time"] += total_time
        server_metrics["request_history"].append({
            "timestamp": datetime.now().isoformat(),
            "endpoint": "/ocr/markdown",
            "filename": file.filename,
            "num_pages": len(images),
            "processing_time": round(total_time, 2)
        })
        
        os.remove(temp_pdf)
        
        print(f'[API] ✅ Completed in {total_time:.2f}s')
        
        return {
            "status": "success",
            "markdown": contents,
            "num_pages": len(images),
            "processing_time": round(total_time, 2),
            "output_file": markdown_path
        }
        
    except Exception as e:
        print(f'[API] ❌ Error: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/ocr/json")
# async def ocr_json(file: UploadFile = File(...)):
#     """OCR PDF và trả về JSON + lưu file"""
#     try:
#         request_metrics = RequestMetrics()
        
#         temp_dir = f"/tmp/ocr_{int(time.time())}"
#         os.makedirs(temp_dir, exist_ok=True)
#         temp_pdf = f"{temp_dir}/{file.filename}"
        
#         print(f'[API] POST /ocr/json - {file.filename}')
        
#         # Save uploaded file
#         request_metrics.mark_step('SAVE_UPLOAD')
#         with open(temp_pdf, "wb") as buffer:
#             buffer.write(await file.read())
#         request_metrics.end_step('SAVE_UPLOAD')
        
#         # Convert PDF to images
#         request_metrics.mark_step('PDF_TO_IMAGES')
#         images = pdf_to_images_high_quality(temp_pdf)
#         request_metrics.end_step('PDF_TO_IMAGES')
        
#         # Pre-process
#         request_metrics.mark_step('PREPROCESS')
#         batch_inputs = preprocess_batch(images, PROMPT)
#         request_metrics.end_step('PREPROCESS')
        
#         # OCR inference
#         request_metrics.mark_step('OCR_INFERENCE')
#         outputs = generate_ocr(llm, batch_inputs, sampling_params)
#         request_metrics.end_step('OCR_INFERENCE')
        
#         # Create output directory
#         output_dir = f"{OUTPUT_PATH}/ocr_{int(time.time())}"
#         os.makedirs(output_dir, exist_ok=True)
        
#         # Post-process
#         request_metrics.mark_step('POSTPROCESS')
#         pages = []
        
#         for page_num, output in enumerate(outputs):
#             raw_text = output.outputs[0].text
#             cleaned_text = extract_content(raw_text)
#             pages.append({
#                 "page_number": page_num + 1,
#                 "content": cleaned_text,
#                 "content_length": len(cleaned_text)
#             })
        
#         request_metrics.end_step('POSTPROCESS')
        
#         # Save JSON file ← THÊM PHẦN NÀY
#         request_metrics.mark_step('SAVE_OUTPUT')
#         json_path = f"{output_dir}/{Path(file.filename).stem}.json"
#         with open(json_path, 'w', encoding='utf-8') as f:
#             json.dump(pages, f, ensure_ascii=False, indent=2)
#         request_metrics.end_step('SAVE_OUTPUT')
        
#         total_time = request_metrics.get_total_time()
        
#         # Update metrics
#         server_metrics["total_requests"] += 1
#         server_metrics["total_pages_processed"] += len(images)
#         server_metrics["total_processing_time"] += total_time
#         server_metrics["request_history"].append({
#             "timestamp": datetime.now().isoformat(),
#             "endpoint": "/ocr/json",
#             "filename": file.filename,
#             "num_pages": len(images),
#             "processing_time": round(total_time, 2)
#         })
        
#         os.remove(temp_pdf)
        
#         print(f'[API] ✅ Completed in {total_time:.2f}s')
#         print(f'[API] ✅ JSON saved: {json_path}')
        
#         return {
#             "status": "success",
#             "pages": pages,
#             "num_pages": len(images),
#             "processing_time": round(total_time, 2),
#             "output_file": json_path  # ← Return path
#         }
        
#     except Exception as e:
#         print(f'[API] ❌ Error: {str(e)}')
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr/json", response_model=DocumentResponseSchema)
async def ocr_json(file: UploadFile = File(...)):
    """OCR PDF và trả về JSON cấu trúc theo schema DocumentResponse"""
    try:
        request_metrics = RequestMetrics()
        
        temp_dir = f"/tmp/ocr_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)
        temp_pdf = f"{temp_dir}/{file.filename}"
        
        print(f'[API] POST /ocr/json - {file.filename}')
        
        # Save uploaded file
        request_metrics.mark_step('SAVE_UPLOAD')
        with open(temp_pdf, "wb") as buffer:
            buffer.write(await file.read())
        request_metrics.end_step('SAVE_UPLOAD')
        
        # Convert PDF to images
        request_metrics.mark_step('PDF_TO_IMAGES')
        images = pdf_to_images_high_quality(temp_pdf)
        request_metrics.end_step('PDF_TO_IMAGES')
        
        # Pre-process
        request_metrics.mark_step('PREPROCESS')
        batch_inputs = preprocess_batch(images, PROMPT)
        request_metrics.end_step('PREPROCESS')
        
        # OCR inference
        request_metrics.mark_step('OCR_INFERENCE')
        outputs = generate_ocr(llm, batch_inputs, sampling_params)
        request_metrics.end_step('OCR_INFERENCE')
        
        
        # =======================================================
        # BƯỚC THAY ĐỔI CỐT LÕI: POST-PROCESS VÀ ĐỊNH DẠNG JSON
        # =======================================================
        
        request_metrics.mark_step('POSTPROCESS_STRUCTURED')
        
        content_pages = []
        total_pages = len(images)
        
        for page_num, output in enumerate(outputs):
            raw_text = output.outputs[0].text
            cleaned_text = extract_content(raw_text)
            
            # Sử dụng hàm phân tích cấu trúc Markdown thành Blocks
            # (Giả định process_ocr_to_blocks đã được import)
            blocks = process_ocr_to_blocks(cleaned_text) 

            content_pages.append({
                "page_number": page_num + 1,
                "blocks": blocks, # <-- Lấy kết quả từ hàm phân tích
            })
        
        # 2. Định dạng theo schema DocumentResponse
        response_data = {
            "document": {
                "metadata": {
                    "source_filename": file.filename,
                    "total_pages": total_pages,
                    "processed_at": datetime.now().isoformat()
                },
                "content": content_pages
            }
        }
        
        request_metrics.end_step('POSTPROCESS_STRUCTURED')
        
        # Save JSON file
        request_metrics.mark_step('SAVE_OUTPUT')
        output_dir = f"{OUTPUT_PATH}/ocr_{int(time.time())}"
        os.makedirs(output_dir, exist_ok=True)
        json_path = f"{output_dir}/{Path(file.filename).stem}.json"
        
        # Lưu toàn bộ response_data
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, ensure_ascii=False, indent=2)
        request_metrics.end_step('SAVE_OUTPUT')
        
        total_time = request_metrics.get_total_time()
        
        # Update metrics
        server_metrics["total_requests"] += 1
        server_metrics["total_pages_processed"] += total_pages
        server_metrics["total_processing_time"] += total_time
        server_metrics["request_history"].append({
            "timestamp": datetime.now().isoformat(),
            "endpoint": "/ocr/json",
            "filename": file.filename,
            "num_pages": total_pages,
            "processing_time": round(total_time, 2)
        })
        
        os.remove(temp_pdf)
        
        print(f'[API] ✅ Completed in {total_time:.2f}s')
        print(f'[API] ✅ JSON saved: {json_path}')
        
        # 3. Cập nhật giá trị trả về
        return {
            "status": "success",
            "document": response_data["document"], # <-- Trả về cấu trúc document
            "num_pages": total_pages,
            "processing_time": round(total_time, 2),
            "output_file": json_path 
        }
        
    except Exception as e:
        print(f'[API] ❌ Error: {str(e)}')
        # Đảm bảo dọn dẹp file tạm nếu có lỗi
        if 'temp_pdf' in locals() and os.path.exists(temp_pdf):
             os.remove(temp_pdf)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """
    Get server metrics
    
    Returns:
        {
            "status": "running",
            "start_time": "2025-12-09T...",
            "total_requests": 10,
            "total_pages_processed": 50,
            "average_time_per_page": 8.5,
            "average_time_per_request": 42.5,
            "request_history": [...]
        }
    """
    avg_time_per_request = 0
    avg_time_per_page = 0
    
    if server_metrics["total_requests"] > 0:
        avg_time_per_request = server_metrics["total_processing_time"] / server_metrics["total_requests"]
    
    if server_metrics["total_pages_processed"] > 0:
        avg_time_per_page = server_metrics["total_processing_time"] / server_metrics["total_pages_processed"]
    
    return {
        "status": "running",
        "start_time": server_metrics["start_time"],
        "total_requests": server_metrics["total_requests"],
        "total_pages_processed": server_metrics["total_pages_processed"],
        "total_processing_time": round(server_metrics["total_processing_time"], 2),
        "average_time_per_request": round(avg_time_per_request, 2),
        "average_time_per_page": round(avg_time_per_page, 2),
        "request_history": server_metrics["request_history"][-20:]  # Last 20 requests
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1
    )