import os
from app.core.config import INPUT_PATH, OUTPUT_PATH, PROMPT
from.worker.model_init import llm, sampling_params
from app.services.processor import preprocess_batch, generate_ocr
from app.utils.postprocess_md import process_ocr_output
from app.services.file_handler import prepare_output_dirs, get_output_paths, save_outputs
from app.utils.utils import pdf_to_images_high_quality

def run_ocr_pipeline(input_pdf, output_dir, prompt):
    """
    Main OCR pipeline
    
    Args:
        input_pdf: Path to input PDF
        output_dir: Output directory
        prompt: OCR prompt
    """
    print('[PIPELINE] Starting OCR processing...')
    
    # Step 1: Prepare
    print('[STEP 1] Preparing output directories...')
    prepare_output_dirs(output_dir)
    output_paths = get_output_paths(input_pdf, output_dir)  
    
    # Step 2: Convert PDF to images
    print('[STEP 2] Converting PDF to images...')
    images = pdf_to_images_high_quality(input_pdf)
    print(f'  ✓ Loaded {len(images)} pages')
    
    # Step 3: Pre-process batch
    print('[STEP 3] Pre-processing images...')
    batch_inputs = preprocess_batch(images, prompt)
    print(f'  ✓ Pre-processed {len(batch_inputs)} images')
    
    # Step 4: Generate OCR
    print('[STEP 4] Running OCR inference...')
    outputs = generate_ocr(llm, batch_inputs, sampling_params)
    print(f'  ✓ Generated outputs for {len(outputs)} pages')
    
    # Step 5: Post-process
    print('[STEP 5] Post-processing results...')
    contents, contents_det, draw_images = process_ocr_output(outputs, images, out_path=output_dir)
    print('  ✓ Post-processed outputs')
    
    # Step 6: Save
    print('[STEP 6] Saving outputs...')
    save_outputs(contents, contents_det, draw_images, output_paths)
    print('  ✓ Saved all outputs')
    
    print('[PIPELINE] ✅ OCR processing completed!')
    
    return output_paths
 
if __name__ == "__main__":
    run_ocr_pipeline(INPUT_PATH, OUTPUT_PATH, PROMPT)