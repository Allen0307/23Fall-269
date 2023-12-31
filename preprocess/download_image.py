# %%
from datasets import load_dataset
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from datasets import load_dataset
from torch.utils.data import Dataset, DataLoader
import os
import torch
import requests
from tqdm import tqdm
import torch.nn as nn
import torch.optim as optim

torch.manual_seed(0)

dataset = load_dataset("yxchng/cc15m_yfcc15m") #100w 

data = dataset['train'][3000000:5000000]
data = list(zip(data['url'], data['caption']))

#

# %%
def get_image(data, tmp):
    for e, (url, caption) in enumerate(data):
        try:
            r = requests.get(url, stream=True, timeout=0.5).raw
            image = Image.open(r)
            image.save(f"/home/share_folder/allen/269/train/{caption}.jpg")
        except:
            None
    return tmp

# %%
from tqdm import tqdm
import threading
num_threads = 20
get_image_length = 2000000 // num_threads
tmp = [[] for _ in range(num_threads)]
# Create and start threads for each URL
threads = []
for d in range(num_threads):
    left, right = get_image_length * d, get_image_length * (d + 1)
    tmp_data = data[left:right]
    thread = threading.Thread(target=get_image, args=(tmp_data, tmp[d],))
    thread.start()
    threads.append(thread)
# Wait for all threads to finish
for thread in threads:
    thread.join()