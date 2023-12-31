# %%
from datasets import load_dataset
import random
import numpy as np
import torch

def set_seed(SEED):
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

set_seed(0)

# %%
from transformers import AutoModel, AutoTokenizer, pipeline, BitsAndBytesConfig

################################################################################
# bitsandbytes parameters
################################################################################

# Activate 4-bit precision base model loading
use_4bit = True

# Compute dtype for 4-bit base models
bnb_4bit_compute_dtype = "float16"

# Quantization type (fp4 or nf4)
bnb_4bit_quant_type = "nf4"

# Activate nested quantization for 4-bit base models (double quantization)
use_nested_quant = False

# Load tokenizer and model with QLoRA configuration
compute_dtype = getattr(torch, bnb_4bit_compute_dtype)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=use_4bit,
    bnb_4bit_quant_type=bnb_4bit_quant_type,
    bnb_4bit_compute_dtype=compute_dtype,
    bnb_4bit_use_double_quant=use_nested_quant,
)

# Check GPU compatibility with bfloat16
if compute_dtype == torch.float16 and use_4bit:
    major, _ = torch.cuda.get_device_capability()
    if major >= 8:
        print("=" * 80)
        print("Your GPU supports bfloat16: accelerate training with bf16=True")
        print("=" * 80)

# The model that you want to train from the Hugging Face hub
model_name = "meta-llama/Llama-2-7b-chat-hf"
model = AutoModel.from_pretrained(model_name, device_map='auto', quantization_config=bnb_config)

# Load LLaMA tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True, device_map='auto')
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right" # Fix weird overflow issue with fp16 training

# %%

import os
TRAIN_ROOT = "/home/share_folder/allen/269/train"
images = [image.rstrip('.jpg') for image in os.listdir(TRAIN_ROOT)]
print(len(images))

from tqdm import tqdm

#
def run_llama(sub):
    pipe = pipeline(task="feature-extraction", model=model, tokenizer=tokenizer, device_map='auto')
    llama2_embedding = {}
    for e, caption in enumerate(tqdm(images[100000*sub:100000*(sub + 1)])):
        result = pipe(caption, return_tensors=True)
        llama2_embedding[caption] = result[0][-1].detach().cpu().numpy()

    import pickle
    llama2_embed_file = f'/home/share_folder/allen/269/llama2_embedding_{sub}.pkl'
    with open(llama2_embed_file, 'wb') as fp:
        pickle.dump(llama2_embedding, fp)
        print('dictionary saved successfully to file')
for i in range(10):
    run_llama(i)

