# import re
# import editdistance
# import csv

# # Hàm làm sạch văn bản
# def clean_text(text):
#     """
#     Loại bỏ khoảng trắng dư thừa và chuẩn hóa khoảng trắng giữa các từ.
#     Giúp văn bản trở nên chuẩn xác cho việc tính CER.
#     """
#     # Loại bỏ khoảng trắng dư thừa và chuẩn hóa khoảng trắng
#     text = re.sub(r'\s+', ' ', text)  # Đảm bảo chỉ có 1 khoảng trắng giữa các từ
#     text = text.strip()  # Loại bỏ khoảng trắng ở đầu và cuối văn bản
    
#     return text

# # Hàm tính Character Error Rate (CER)
# def calculate_cer(reference_text, hypothesis_text):
#     """
#     Tính toán Character Error Rate (CER) giữa văn bản tham chiếu và văn bản OCR.
#     """
#     edit_dist = editdistance.eval(reference_text, hypothesis_text)  # Tính edit distance
#     cer = edit_dist / len(reference_text)  # Tính CER
#     return cer

# # Đọc và làm sạch tệp văn bản tham chiếu (Ground truth)
# def read_and_clean_file(file_path):
#     """
#     Đọc và làm sạch văn bản từ tệp.
#     """
#     with open(file_path, 'r', encoding='utf-8') as file:
#         text = file.read()
#     return clean_text(text)

# # Đọc các tệp văn bản (OCR output và Ground truth)
# ocr_text_path = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/processed/ocr_clean.txt'  # Thay bằng đường dẫn tới tệp OCR output
# ground_truth_path = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/processed/raw_clean.txt'  # Thay bằng đường dẫn tới tệp tham chiếu

# # Làm sạch văn bản từ cả hai tệp
# ocr_text = read_and_clean_file(ocr_text_path)
# ground_truth_text = read_and_clean_file(ground_truth_path)

# # Tính CER
# cer_score = calculate_cer(ground_truth_text, ocr_text)
# print(f"CER: {cer_score:.4f}")

# # Lưu kết quả CER vào tệp CSV
# output_csv = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/corpus_manifest.csv'
# with open(output_csv, 'w', newline='', encoding='utf-8') as file:
#     writer = csv.writer(file)
#     writer.writerow(['File', 'CER_Score', 'Text_Length'])
#     writer.writerow([ocr_text_path, cer_score, len(ground_truth_text)])

# print(f'Results saved in {output_csv}')
import re
import editdistance
import csv
import os

# --- 1. HÀM CHUẨN BỊ DỮ LIỆU ---

# Hàm làm sạch văn bản (Giữ nguyên)
def clean_text(text):
    """
    Loại bỏ khoảng trắng dư thừa và chuẩn hóa khoảng trắng giữa các từ.
    """
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

# Hàm đọc và làm sạch tệp văn bản (Giữ nguyên)
def read_and_clean_file(file_path):
    """
    Đọc và làm sạch văn bản từ tệp.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        return clean_text(text)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp tại đường dẫn {file_path}")
        return ""

# Hàm tính Character Error Rate (CER) (Giữ nguyên)
def calculate_cer(reference_text, hypothesis_text):
    """
    Tính toán Character Error Rate (CER) giữa văn bản tham chiếu và văn bản OCR.
    Trả về CER và Edit Distance.
    """
    if len(reference_text) == 0:
        return 0.0, 0
        
    edit_dist = editdistance.eval(reference_text, hypothesis_text)
    cer = edit_dist / len(reference_text)
    return cer, edit_dist

# --- 2. THÔNG SỐ ĐẦU VÀO CỦA BẠN ---

# Đường dẫn đến TỆP Ground Truth duy nhất
ground_truth_file_path = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/test_additional/origin/hi.txt' 
# Đường dẫn đến THƯ MỤC chứa nhiều tệp OCR
ocr_folder_path = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/test_additional/lb'

output_csv = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/corpus_manifest_single_gt.csv'

# --- 3. QUÁ TRÌNH XỬ LÝ CHÍNH ---

# 1. Đọc và làm sạch TỆP Ground Truth duy nhất
ground_truth_text = read_and_clean_file(ground_truth_file_path)
reference_length = len(ground_truth_text)

if not ground_truth_text:
    print("Lỗi nghiêm trọng: Tệp Ground Truth duy nhất không tồn tại hoặc rỗng. Không thể tiến hành đánh giá.")
    exit()

all_cer_scores = [] # Lưu tất cả các CER score riêng lẻ
num_ocr_files = 0

# Lấy danh sách tệp .txt từ thư mục OCR và sắp xếp
ocr_files = sorted([f for f in os.listdir(ocr_folder_path) if f.endswith('.txt')])
num_ocr_files = len(ocr_files)

print(f"Tìm thấy {num_ocr_files} tệp OCR để so sánh với Ground Truth duy nhất.")
print(f"Độ dài Ground Truth: {reference_length} ký tự.")

# Mở tệp CSV và ghi header
with open(output_csv, 'w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['OCR_File_Name', 'CER_Score', 'Edit_Distance', 'Reference_Length'])

    for filename in ocr_files:
        ocr_file_path = os.path.join(ocr_folder_path, filename)
        
        # 1. Đọc và làm sạch tệp OCR
        ocr_text = read_and_clean_file(ocr_file_path)
        
        # 2. Tính CER cho cặp tệp (OCR File vs Single GT File)
        cer_score, edit_dist = calculate_cer(ground_truth_text, ocr_text)
        
        # 3. Lưu điểm CER riêng lẻ
        all_cer_scores.append(cer_score)
        
        # 4. Ghi kết quả của tệp hiện tại vào CSV
        writer.writerow([
            filename, 
            f"{cer_score:.4f}", 
            edit_dist, 
            reference_length
        ])
        
        print(f"Đã xử lý: {filename} -> CER: {cer_score:.4f}")

# --- 4. TÍNH TOÁN CER CUỐI CÙNG (TRUNG BÌNH CỘNG) ---

final_average_cer = 0.0
if num_ocr_files > 0:
    # Tính Trung bình cộng (Simple Average) của tất cả các CER score riêng lẻ
    final_average_cer = sum(all_cer_scores) / num_ocr_files

print("\n" + "=" * 60)
print(f"TỔNG KẾT ĐÁNH GIÁ (So sánh {num_ocr_files} OCR files với 1 GT File):")
print(f"Độ dài Ground Truth: {reference_length}")
print(f"CER TRUNG BÌNH CỘNG (Simple Average): {final_average_cer:.4f}")
print("=" * 60)
print(f'Kết quả chi tiết từng tệp được lưu trong {output_csv}')