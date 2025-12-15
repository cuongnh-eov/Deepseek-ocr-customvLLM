import os
from pathlib import Path
from app.utils import pil_to_pdf_img2pdf

def prepare_output_dirs(output_path):
    """Create output directories"""
    os.makedirs(output_path, exist_ok=True)
    os.makedirs(f'{output_path}/images', exist_ok=True)

def get_output_paths(input_path, output_path):
    """
    Get output file paths
    
    Args:
        input_path: Input PDF path
        output_path: Output directory
    
    Returns:
        Dict with all output paths
    """
    base_name = Path(input_path).stem
    
    return {
        'mmd_det': f'{output_path}/{base_name}_det.mmd',
        'mmd': f'{output_path}/{base_name}.mmd',
        'pdf': f'{output_path}/{base_name}_layouts.pdf',
        'images': f'{output_path}/images'
    }

def save_outputs(contents, contents_det, draw_images, output_paths):
    """
    Save all outputs to files
    
    Args:
        contents: Processed markdown content
        contents_det: Detailed markdown with detections
        draw_images: List of PIL images with bounding boxes
        output_paths: Dict of output file paths
    """
    # Save markdown files
    with open(output_paths['mmd_det'], 'w', encoding='utf-8') as f:
        f.write(contents_det)
    
    with open(output_paths['mmd'], 'w', encoding='utf-8') as f:
        f.write(contents)
    
    # Save PDF with layouts
    pil_to_pdf_img2pdf(draw_images, output_paths['pdf'])
    
    print(f"✅ Saved: {output_paths['mmd_det']}")
    print(f"✅ Saved: {output_paths['mmd']}")
    print(f"✅ Saved: {output_paths['pdf']}")