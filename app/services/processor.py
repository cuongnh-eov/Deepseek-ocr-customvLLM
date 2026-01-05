import pytesseract
from PIL import Image
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
# Chú ý đường dẫn import từ utils
from app.utils.postprocess_md import process_single_image
from app.config import NUM_WORKERS

def preprocess_batch(images, prompt):
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # results sẽ là danh sách các bộ (cache_item, image)
        results = list(tqdm(
            executor.map(lambda image: process_single_image(image, prompt), images),
            total=len(images),
            desc="🚀 Pre-processing images",
            leave=False 
        ))
    
    # TÁCH RIÊNG 2 DANH SÁCH TỪ results
    batch_inputs = [r[0] for r in results]   # Đây là cái cũ bạn cần giữ nguyên
    processed_images = [r[1] for r in results] # Đây là cái mới để dùng cho vẽ BBox
    
    return batch_inputs, processed_images # Trả về cả cũ và mới

def generate_ocr(llm, batch_inputs, sampling_params):
    """
    Chạy Inference trên GPU thông qua vLLM
    """
    if not llm:
        raise ValueError("vLLM Engine chưa được khởi tạo!")
    
    # vLLM xử lý Batch cực nhanh trên GPU
    outputs_list = llm.generate(batch_inputs, sampling_params=sampling_params)
    return outputs_list

# --- FALLBACK MECHANISM ---

class MockModelOutput:
    """Giả lập cấu trúc trả về của vLLM để đồng nhất dữ liệu đầu ra"""
    def __init__(self, text):
        # Tạo object giả lập để truy cập được dạng output.outputs[0].text
        self.outputs = [type('obj', (object,), {'text': text})]

def run_tesseract_fallback(images):
    """
    Cơ chế cứu hộ: Chạy Tesseract OCR (CPU) nếu vLLM/GPU gặp sự cố
    """
    print("🔄 [FALLBACK] Đang xử lý bằng Tesseract (CPU)...")
    final_outputs = []
    
    for idx, img in enumerate(images):
        try:
            # lang='vie+eng' để hỗ trợ song ngữ Việt - Anh
            # config='--psm 3' (Fully automatic page segmentation) thường cho kết quả tốt nhất
            text = pytesseract.image_to_string(img, lang='vie+eng', config='--psm 3')
            final_outputs.append(MockModelOutput(text))
        except Exception as e:
            print(f"⚠️ Lỗi Tesseract tại trang {idx + 1}: {e}")
            final_outputs.append(MockModelOutput(f"[Trang {idx+1} lỗi: {str(e)}]"))
            
    return final_outputs