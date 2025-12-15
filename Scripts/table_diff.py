import os  
import json  
import jsonlines  
from metric import TEDS  
from tqdm import tqdm  
  
def evaluate_html_folder(html_folder, ground_truth_jsonl, n_jobs=4):  
    """  
    Đánh giá song song tất cả file HTML trong folder  
      
    Args:  
        html_folder: Đường dẫn đến folder chứa file HTML  
        ground_truth_jsonl: File JSONL ground truth của PubTabNet  
        n_jobs: Số process chạy song song  
    """  
      
    # 1. Load ground truth từ JSONL  
    true_json = {}  
    with jsonlines.open(ground_truth_jsonl, 'r') as reader:  
        for annotation in reader:  
            # Reconstruct HTML từ tokens  
            html_code = annotation['html']['structure']['tokens'].copy()  
            to_insert = [i for i, tag in enumerate(html_code) if tag in ('<td>', '>')]  
            for i, cell in zip(to_insert[::-1], annotation['html']['cells'][::-1]):  
                if cell['tokens']:  
                    from html import escape  
                    cell = [escape(token) if len(token) == 1 else token for token in cell['tokens']]  
                    cell = ''.join(cell)  
                    html_code.insert(i + 1, cell)  
            html_code = ''.join(html_code)  
              
            # Wrap theo cấu trúc PubTabNet  
            full_html = f"""<html>  
                             <head><meta charset="UTF-8"></head>  
                             <body>  
                             <table frame="hsides" rules="groups" width="100%">  
                               {html_code}  
                             </table>  
                             </body>  
                             </html>"""  
              
            true_json[annotation['filename']] = {'html': full_html}  
      
    # 2. Load predictions từ folder HTML  
    pred_json = {}  
    html_files = [f for f in os.listdir(html_folder) if f.endswith('.html')]  
      
    print(f"Tìm thấy {len(html_files)} file HTML trong folder")  
      
    for filename in html_files:  
        with open(os.path.join(html_folder, filename), 'r', encoding='utf-8') as f:  
            pred_json[filename] = f.read()  
      
    # 3. Chạy batch evaluation với parallel processing  
    teds = TEDS(n_jobs=n_jobs)  
    scores = teds.batch_evaluate(pred_json, true_json)  
      
    return scores  
  
# Sử dụng  
if __name__ == "__main__":  
    scores = evaluate_html_folder(  
        html_folder="path/to/your/html/files",  
        ground_truth_jsonl="PubTabNet_2.0.0.jsonl",  
        n_jobs=8  # Dùng 8 cores  
    )  
      
    # Hiển thị kết quả  
    for filename, score in scores.items():  
        print(f"{filename}: {score:.4f}")  
      
    # Tính score trung bình  
    avg_score = sum(scores.values()) / len(scores)  
    print(f"\nAverage TEDS score: {avg_score:.4f}")