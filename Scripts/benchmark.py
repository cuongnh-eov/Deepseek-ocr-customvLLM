import os
import time
import psutil
import torch
import json
from pathlib import Path
from datetime import datetime
from app.core.config import INPUT_PATH, OUTPUT_PATH, PROMPT
from worker.model_init import llm, sampling_params
from app.services.processor import preprocess_batch, generate_ocr
from app.utils.postprocess_md import process_ocr_output
from app.services.file_handler import prepare_output_dirs, get_output_paths, save_outputs
from app.utils.utils import pdf_to_images_high_quality

class GPUMonitor:
    """Monitor GPU usage"""
    
    def __init__(self):
        self.initial_vram = torch.cuda.memory_allocated() / 1024**3  # GB
        self.peak_vram = self.initial_vram
        self.start_time = time.time()
    
    def update(self):
        """Update peak VRAM usage"""
        current_vram = torch.cuda.memory_allocated() / 1024**3
        if current_vram > self.peak_vram:
            self.peak_vram = current_vram
    
    def get_stats(self):
        """Get GPU statistics"""
        torch.cuda.synchronize()
        final_vram = torch.cuda.memory_allocated() / 1024**3
        
        return {
            'initial_vram_gb': round(self.initial_vram, 2),
            'peak_vram_gb': round(self.peak_vram, 2),
            'final_vram_gb': round(final_vram, 2),
            'vram_used_gb': round(self.peak_vram - self.initial_vram, 2),
            'gpu_name': torch.cuda.get_device_name(0),
            'cuda_version': torch.version.cuda
        }


class CPUMonitor:
    """Monitor CPU usage"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / 1024**2  # MB
        self.peak_memory = self.initial_memory
        self.initial_cpu_percent = self.process.cpu_percent()
    
    def update(self):
        """Update peak memory usage"""
        current_memory = self.process.memory_info().rss / 1024**2
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
    
    def get_stats(self):
        """Get CPU statistics"""
        return {
            'initial_memory_mb': round(self.initial_memory, 2),
            'peak_memory_mb': round(self.peak_memory, 2),
            'memory_used_mb': round(self.peak_memory - self.initial_memory, 2),
            'cpu_percent': round(self.process.cpu_percent(), 2)
        }


class Benchmark:
    """Main benchmark class"""
    
    def __init__(self, input_pdf, output_dir=None):
        self.input_pdf = input_pdf
        self.output_dir = output_dir or f"{OUTPUT_PATH}/benchmark"
        self.gpu_monitor = GPUMonitor()
        self.cpu_monitor = CPUMonitor()
        self.metrics = {}
        self.timestamps = {}
    
    def log_step(self, step_name):
        """Log timestamp for a step"""
        self.timestamps[step_name] = time.time()
        print(f'[{step_name}] Started...')
    
    def end_step(self, step_name):
        """End step timing"""
        if step_name not in self.timestamps:
            return 0
        
        elapsed = time.time() - self.timestamps[step_name]
        print(f'  ✓ {step_name} completed in {elapsed:.2f}s')
        return elapsed
    
    def run_benchmark(self):
        """Run complete benchmark"""
        print('=' * 80)
        print('🔬 BENCHMARK: DeepSeek OCR Pipeline')
        print('=' * 80)
        print(f'Input PDF: {self.input_pdf}')
        print(f'Output Dir: {self.output_dir}')
        print()
        
        # Step 1: Prepare
        self.log_step('PREPARE')
        prepare_output_dirs(self.output_dir)
        output_paths = get_output_paths(self.input_pdf, self.output_dir)
        time_prepare = self.end_step('PREPARE')
        
        # Step 2: Convert PDF to images
        self.log_step('PDF_TO_IMAGES')
        images = pdf_to_images_high_quality(self.input_pdf)
        time_pdf_to_images = self.end_step('PDF_TO_IMAGES')
        print(f'  → Loaded {len(images)} pages')
        self.gpu_monitor.update()
        self.cpu_monitor.update()
        
        # Step 3: Pre-process
        self.log_step('PREPROCESS')
        batch_inputs = preprocess_batch(images, PROMPT)
        time_preprocess = self.end_step('PREPROCESS')
        self.gpu_monitor.update()
        self.cpu_monitor.update()
        
        # Step 4: OCR inference
        self.log_step('OCR_INFERENCE')
        outputs = generate_ocr(llm, batch_inputs, sampling_params)
        time_ocr = self.end_step('OCR_INFERENCE')
        self.gpu_monitor.update()
        self.cpu_monitor.update()
        
        # Step 5: Post-process
        self.log_step('POSTPROCESS')
        contents, contents_det, draw_images = process_ocr_output(outputs, images)
        time_postprocess = self.end_step('POSTPROCESS')
        self.gpu_monitor.update()
        self.cpu_monitor.update()
        
        # Step 6: Save
        self.log_step('SAVE')
        save_outputs(contents, contents_det, draw_images, output_paths)
        time_save = self.end_step('SAVE')
        
        # Collect metrics
        self.metrics = {
            'timestamp': datetime.now().isoformat(),
            'input_pdf': self.input_pdf,
            'num_pages': len(images),
            'output_dir': self.output_dir,
            'timing': {
                'prepare_s': round(time_prepare, 2),
                'pdf_to_images_s': round(time_pdf_to_images, 2),
                'preprocess_s': round(time_preprocess, 2),
                'ocr_inference_s': round(time_ocr, 2),
                'postprocess_s': round(time_postprocess, 2),
                'save_s': round(time_save, 2),
                'total_s': round(sum([time_prepare, time_pdf_to_images, time_preprocess, 
                                     time_ocr, time_postprocess, time_save]), 2)
            },
            'timing_per_page': {
                'pdf_to_images_per_page_s': round(time_pdf_to_images / len(images), 2),
                'preprocess_per_page_s': round(time_preprocess / len(images), 2),
                'ocr_per_page_s': round(time_ocr / len(images), 2),
                'postprocess_per_page_s': round(time_postprocess / len(images), 2)
            },
            'gpu': self.gpu_monitor.get_stats(),
            'cpu': self.cpu_monitor.get_stats(),
            'throughput': {
                'pages_per_second': round(len(images) / self.metrics['timing']['total_s'], 2)
            }
        }
        
        self.print_results()
        self.save_results()
        
        return self.metrics
    
    def print_results(self):
        """Print benchmark results"""
        print()
        print('=' * 80)
        print('📊 BENCHMARK RESULTS')
        print('=' * 80)
        
        # Timing
        print('\n⏱️  TIMING:')
        timing = self.metrics['timing']
        print(f'  Prepare:            {timing["prepare_s"]:7.2f}s')
        print(f'  PDF to Images:      {timing["pdf_to_images_s"]:7.2f}s')
        print(f'  Pre-process:        {timing["preprocess_s"]:7.2f}s')
        print(f'  OCR Inference:      {timing["ocr_inference_s"]:7.2f}s')
        print(f'  Post-process:       {timing["postprocess_s"]:7.2f}s')
        print(f'  Save:               {timing["save_s"]:7.2f}s')
        print(f'  {"─" * 40}')
        print(f'  TOTAL:              {timing["total_s"]:7.2f}s')
        
        # Per page
        print('\n📄 PER PAGE:')
        per_page = self.metrics['timing_per_page']
        print(f'  Pages:              {self.metrics["num_pages"]:>7} pages')
        print(f'  PDF to Images:      {per_page["pdf_to_images_per_page_s"]:7.2f}s/page')
        print(f'  Pre-process:        {per_page["preprocess_per_page_s"]:7.2f}s/page')
        print(f'  OCR Inference:      {per_page["ocr_per_page_s"]:7.2f}s/page')
        print(f'  Post-process:       {per_page["postprocess_per_page_s"]:7.2f}s/page')
        
        # Throughput
        print('\n🚀 THROUGHPUT:')
        throughput = self.metrics['throughput']
        print(f'  Pages/Second:       {throughput["pages_per_second"]:7.2f} pages/s')
        
        # GPU
        print('\n🔥 GPU MEMORY:')
        gpu = self.metrics['gpu']
        print(f'  GPU:                {gpu["gpu_name"]}')
        print(f'  CUDA Version:       {gpu["cuda_version"]}')
        print(f'  Initial VRAM:       {gpu["initial_vram_gb"]:7.2f} GB')
        print(f'  Peak VRAM:          {gpu["peak_vram_gb"]:7.2f} GB')
        print(f'  Final VRAM:         {gpu["final_vram_gb"]:7.2f} GB')
        print(f'  VRAM Used:          {gpu["vram_used_gb"]:7.2f} GB')
        
        # CPU
        print('\n💻 CPU MEMORY:')
        cpu = self.metrics['cpu']
        print(f'  Initial Memory:     {cpu["initial_memory_mb"]:7.2f} MB')
        print(f'  Peak Memory:        {cpu["peak_memory_mb"]:7.2f} MB')
        print(f'  Memory Used:        {cpu["memory_used_mb"]:7.2f} MB')
        print(f'  CPU Percent:        {cpu["cpu_percent"]:7.2f}%')
        
        print()
        print('=' * 80)
    
    def save_results(self):
        """Save results to JSON"""
        results_file = f"{self.output_dir}/benchmark_results.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, ensure_ascii=False)
        
        print(f'✅ Results saved: {results_file}')


def run_benchmark(input_pdf=None, output_dir=None):
    """Run benchmark"""
    if input_pdf is None:
        input_pdf = INPUT_PATH
    if output_dir is None:
        output_dir = f"{OUTPUT_PATH}/benchmark"
    
    benchmark = Benchmark(input_pdf, output_dir)
    metrics = benchmark.run_benchmark()
    
    return metrics


if __name__ == "__main__":
    import sys
    
    input_pdf = sys.argv[1] if len(sys.argv) > 1 else INPUT_PATH
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    run_benchmark(input_pdf, output_dir)