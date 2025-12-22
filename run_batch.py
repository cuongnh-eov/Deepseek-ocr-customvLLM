import os
import re
from tqdm import tqdm
import torch
if torch.version.cuda == '11.8':
    os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-11.8/bin/ptxas"
os.environ['VLLM_USE_V1'] = '0'
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

from configs.config import MODEL_PATH, INPUT_PATH, OUTPUT_PATH, PROMPT, MAX_CONCURRENCY, CROP_MODE, NUM_WORKERS
from concurrent.futures import ThreadPoolExecutor
import glob
from PIL import Image
from deepseek_ocr import DeepseekOCRForCausalLM

from vllm.model_executor.models.registry import ModelRegistry

from vllm import LLM, SamplingParams
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor
ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)


llm = LLM(
    model=MODEL_PATH,
    hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
    block_size=256,
    enforce_eager=False,
    trust_remote_code=True, 
    max_model_len=8192,
    swap_space=0,
    max_num_seqs = MAX_CONCURRENCY,
    tensor_parallel_size=1,
    gpu_memory_utilization=0.9,
)

logits_processors = [NoRepeatNGramLogitsProcessor(ngram_size=40, window_size=90, whitelist_token_ids= {128821, 128822})] #window for fast；whitelist_token_ids: <td>,</td>

sampling_params = SamplingParams(
    temperature=0.0,
    max_tokens=8192,
    logits_processors=logits_processors,
    skip_special_tokens=False,
)

class Colors:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    RESET = '\033[0m' 

def clean_formula(text):

    formula_pattern = r'\\\[(.*?)\\\]'
    
    def process_formula(match):
        formula = match.group(1)

        formula = re.sub(r'\\quad\s*\([^)]*\)', '', formula)
        
        formula = formula.strip()
        
        return r'\[' + formula + r'\]'

    cleaned_text = re.sub(formula_pattern, process_formula, text)
    
    return cleaned_text

def re_match(text):
    pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'
    matches = re.findall(pattern, text, re.DOTALL)


    # mathes_image = []
    mathes_other = []
    for a_match in matches:
        mathes_other.append(a_match[0])
    return matches, mathes_other

def process_single_image(image):
    """single image"""
    prompt_in = prompt
    cache_item = {
        "prompt": prompt_in,
        "multi_modal_data": {"image": DeepseekOCRProcessor().tokenize_with_images(images = [image], bos=True, eos=True, cropping=CROP_MODE)},
    }
    return cache_item


if __name__ == "__main__":

    from pathlib import Path

    # Tạo output folder
    out_dir = Path(OUTPUT_PATH)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'{Colors.RED}glob images.....{Colors.RESET}')

    # Lọc chỉ các file ảnh hợp lệ (tránh lẫn folder / file khác)
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
    images_path = sorted([
        p for p in glob.glob(f"{INPUT_PATH}/*")
        if Path(p).is_file() and Path(p).suffix.lower() in exts
    ])

    if not images_path:
        print(f"{Colors.YELLOW}No images found in {INPUT_PATH}{Colors.RESET}")
        raise SystemExit(0)

    # prompt global cho process_single_image
    prompt = PROMPT

    # Load ảnh (giữ nguyên logic của bạn)
    images = []
    for image_path in images_path:
        image = Image.open(image_path).convert("RGB")
        images.append(image)

    # Pre-process batch inputs
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        batch_inputs = list(tqdm(
            executor.map(process_single_image, images),
            total=len(images),
            desc="Pre-processed images"
        ))

    # OCR
    outputs_list = llm.generate(batch_inputs, sampling_params=sampling_params)

    # Ghi ra .md (KHÔNG ghi _det.md)
    for output, img_path in zip(outputs_list, images_path):
        content = output.outputs[0].text

        content = clean_formula(content)
        _, mathes_other = re_match(content)
        for a_match_other in mathes_other:
            content = (content.replace(a_match_other, '')
                              .replace('\n\n\n\n', '\n\n')
                              .replace('\n\n\n', '\n\n')
                              .replace('<center>', '')
                              .replace('</center>', ''))

        md_path = out_dir / f"{Path(img_path).stem}.md"
        md_path.write_text(content, encoding="utf-8")
