# from tqdm import tqdm
# from concurrent.futures import ThreadPoolExecutor
# from app.utils.postprocess_md import process_single_image
# from app.core.config import NUM_WORKERS

# def preprocess_batch(images, prompt):
#     """
#     Pre-process batch of images
    
#     Args:
#         images: List of PIL.Image
#         prompt: OCR prompt
    
#     Returns:
#         List of cache_items for vLLM
#     """
#     with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
#         batch_inputs = list(tqdm(
#             executor.map(lambda image: process_single_image(image, prompt), images),
#             total=len(images),
#             desc="Pre-processing images"
#         ))
    
#     return batch_inputs

# def generate_ocr(llm, batch_inputs, sampling_params):
#     """
#     Generate OCR results
    
#     Args:
#         llm: vLLM engine
#         batch_inputs: Pre-processed inputs
#         sampling_params: Sampling parameters
    
#     Returns:
#         List of outputs
#     """
#     outputs_list = llm.generate(batch_inputs, sampling_params=sampling_params)
#     return outputs_list


# import pytesseract
# from PIL import Image

# # Định nghĩa cấu trúc trả về giả lập để các bước sau (Post-process) không bị lỗi
# class MockModelOutput:
#     def __init__(self, text):
#         # Giả lập: outputs[0].text
#         self.outputs = [type('obj', (object,), {'text': text})]

# def run_tesseract_fallback(images):
#     """
#     Hàm này chạy khi DeepSeek (vLLM) bị lỗi.
#     Sử dụng CPU để cứu Job.
#     """
#     print("🔄 Đang kích hoạt Tesseract Fallback cho Job này...")
#     final_outputs = []
    
#     for img in images:
#         try:
#             # lang='vie+eng' vì bạn đã cài tesseract-ocr-vie ở bước 1
#             text = pytesseract.image_to_string(img, lang='vie+eng')
#             final_outputs.append(MockModelOutput(text))
#         except Exception as e:
#             print(f"⚠️ Lỗi xử lý 1 trang bằng Tesseract: {e}")
#             final_outputs.append(MockModelOutput("[Lỗi nhận diện trang này]"))
            
#     return final_outputs


import pytesseract
from PIL import Image
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
# Chú ý đường dẫn import từ utils
from app.utils.postprocess_md import process_single_image
from app.core.config import NUM_WORKERS

def preprocess_batch(images, prompt):
    """
    Tiền xử lý hàng loạt ảnh bằng đa luồng (CPU intensive)
    """
    # Sử dụng ThreadPoolExecutor giúp tận dụng đa nhân CPU khi resize/padding ảnh
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        batch_inputs = list(tqdm(
            executor.map(lambda image: process_single_image(image, prompt), images),
            total=len(images),
            desc="🚀 Pre-processing images",
            leave=False # Đảm bảo thanh tqdm biến mất sau khi xong để log sạch hơn
        ))
    
    return batch_inputs

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