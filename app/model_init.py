import os
import torch
from vllm import LLM, SamplingParams
from vllm.model_executor.models.registry import ModelRegistry
from deepseek_ocr import DeepseekOCRForCausalLM
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from configs.config import MODEL_PATH, MAX_CONCURRENCY

if torch.version.cuda == '11.8':
    os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-11.8/bin/ptxas"

os.environ['VLLM_USE_V1'] = '0'
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)

def init_llm():
    """Initialize vLLM engine"""
    llm = LLM(
        model=MODEL_PATH,
        hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
        block_size=256,
        enforce_eager=False,
        trust_remote_code=True, 
        max_model_len=8192,
        swap_space=0,
        max_num_seqs=MAX_CONCURRENCY,
        tensor_parallel_size=1,
        gpu_memory_utilization=0.9,
        disable_mm_preprocessor_cache=True
    )
    return llm

def get_sampling_params():
    """Get sampling parameters"""
    logits_processors = [NoRepeatNGramLogitsProcessor(
        ngram_size=20, 
        window_size=50, 
        whitelist_token_ids={128821, 128822}
    )]
    
    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=8192,
        logits_processors=logits_processors,
        skip_special_tokens=False,
        include_stop_str_in_output=True,
    )
    return sampling_params

# Global instances
llm = init_llm()
sampling_params = get_sampling_params()