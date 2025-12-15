from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from app.postprocess_md import process_single_image
from configs.config import NUM_WORKERS

def preprocess_batch(images, prompt):
    """
    Pre-process batch of images
    
    Args:
        images: List of PIL.Image
        prompt: OCR prompt
    
    Returns:
        List of cache_items for vLLM
    """
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        batch_inputs = list(tqdm(
            executor.map(lambda image: process_single_image(image, prompt), images),
            total=len(images),
            desc="Pre-processing images"
        ))
    
    return batch_inputs

def generate_ocr(llm, batch_inputs, sampling_params):
    """
    Generate OCR results
    
    Args:
        llm: vLLM engine
        batch_inputs: Pre-processed inputs
        sampling_params: Sampling parameters
    
    Returns:
        List of outputs
    """
    outputs_list = llm.generate(batch_inputs, sampling_params=sampling_params)
    return outputs_list