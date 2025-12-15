import re
import os

def clean_text_refined(text):
    """
    Loại bỏ các thẻ Markdown, chỉ dẫn như Page Split, ký tự đặc biệt và khoảng trắng dư thừa.
    Đảm bảo các từ ở hai dòng khác nhau (do ngắt dòng mềm) vẫn có 1 khoảng trắng
    ngăn cách, và làm phẳng văn bản thành một đoạn thuần túy.
    """
    
    # 1. Loại bỏ các chỉ dẫn "Page Split" và các biến thể
    text = re.sub(r'<---? ?Page Split ?--->?', '', text)
    
    # 2. Loại bỏ các thẻ Markdown (**, *, #, !, |, <, >, -, =)
    text = re.sub(r'(\*\*|\*|#|!|\||<|>|\-|=)', '', text)
    
    # 3. Loại bỏ dấu nháy kép (")
    text = re.sub(r'"', '', text)
    
    # 4. **BƯỚC SỬA LỖI QUAN TRỌNG:** Thay thế TẤT CẢ ký tự xuống dòng (\n) bằng một khoảng trắng.
    # Điều này đảm bảo từ cuối dòng cũ và từ đầu dòng mới luôn được phân cách.
    text = text.replace('\n', ' ')

    # 5. Thay thế mọi chuỗi khoảng trắng dư thừa (\s+) bằng một khoảng trắng duy nhất.
    text = re.sub(r'\s+', ' ', text)
    
    # 6. Loại bỏ khoảng trắng ở đầu và cuối văn bản
    text = text.strip()
    
    return text

# Thiết lập đường dẫn tệp
# LƯU Ý: VÌ BẠN ĐANG SỬ DỤNG ĐƯỜNG DẪN TẠM THỜI (/mnt/data/...), HÃY ĐẢM BẢO
# BẠN THAY ĐỔI CHÚNG KHI CHẠY TRÊN HỆ THỐNG CỦA MÌNH.
input_file = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/test_additional/origin/res/4248297722967711064__skew_2p0/result.mmd' # Đường dẫn tệp của bạn
output_file = '/home/cuongnh/PycharmProjects/TTTS_01/TTS-01/data/test_additional/origin/res/4248297722967711064__skew_2p0/result.txt'  # Đường dẫn tệp lưu kết quả

# --- Thực thi quá trình làm sạch và lưu tệp ---
try:
    # 1. Đọc tệp văn bản
    with open(input_file, 'r', encoding='utf-8') as file:
        text = file.read()

    # 2. Làm sạch văn bản
    cleaned_text = clean_text_refined(text)

    # 3. Lưu văn bản đã làm sạch vào một tệp mới
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(cleaned_text)

    # 4. Thông báo kết quả
    # (Tôi vẫn giữ một câu thông báo đơn giản để bạn biết quá trình đã hoàn thành)
    print(f'Văn bản đã được làm sạch và lưu thành công tại: {output_file}')

except FileNotFoundError:
    print(f"Lỗi: Không tìm thấy tệp đầu vào tại đường dẫn: {input_file}. Vui lòng kiểm tra lại đường dẫn.")
except Exception as e:
    print(f"Đã xảy ra lỗi trong quá trình xử lý tệp: {e}")