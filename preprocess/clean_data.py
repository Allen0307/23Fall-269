from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from datasets import load_dataset
from torch.utils.data import Dataset, DataLoader
import torch
import requests
import sys
import io
from tqdm import tqdm
import torch
import torch.nn as nn
import torch.optim as optim
import os
import random
import pickle
class CLIPDataset(Dataset):
  def __init__(self, data_path, root, clean_data):

    self.dataset = data_path
    self.root = root
    self.clean_data = clean_data

  def __len__(self):

    return len(self.dataset)

  def __getitem__(self, idx):
    
    text = self.dataset[idx].rstrip('.jpg')

    try:
        image = Image.open(os.path.join(self.root, self.dataset[idx]))
        self.clean_data.append(self.dataset[idx])
    except: 
        return self.dataset[idx]

    return None

from tqdm import tqdm
# TRAIN_ROOT = "/home/share_folder/allen/269/train"
# image_path = os.listdir(TRAIN_ROOT)
# train_images = image_path[:1000000]

# print(f"Finished Loading Data...")
# train_dataset = CLIPDataset(train_images, TRAIN_ROOT, [])

# broken = 0
# for i in tqdm(range(len(train_dataset))):
#     if train_dataset.__getitem__(i) is not None:
#         broken += 1

# print(len(train_dataset.clean_data))
# print(broken)

# import pickle
# llama2_embed_file = '/home/share_folder/allen/269/clean_data_path.pkl'
# with open(llama2_embed_file, 'wb') as fp:
#     pickle.dump(train_dataset.clean_data, fp)
#     print('dictionary saved successfully to file')


import pickle
from PIL import Image
import os
from tqdm import tqdm
import threading

TRAIN_DATA = '/home/share_folder/allen/269/clean_data_path.pkl'
with open(TRAIN_DATA, 'rb') as fp:
    image_path = pickle.load(fp)
new_path = image_path[900000:]
TRAIN_ROOT = "/home/share_folder/allen/269/train"
print("loading finished...")
# Number of threads to use
num_threads = 20
import numpy as np
# Function to load images in parallel
def load_images(start_index, end_index, result):
    local_image_data = []
    for i in range(start_index, end_index):
        image = Image.open(os.path.join(TRAIN_ROOT, new_path[i])).convert("RGB")
        image = image.resize((224, 224))
        image = np.array(image)
        local_image_data.append(image)
    result.extend(local_image_data)

# Split the data indices for each thread
data_size = len(new_path)
indices_per_thread = data_size // num_threads
thread_list = []

# Create threads
for i in range(num_threads):
    start_index = i * indices_per_thread
    end_index = (i + 1) * indices_per_thread if i < num_threads - 1 else data_size
    result_list = []
    thread = threading.Thread(target=load_images, args=(start_index, end_index, result_list))
    thread.start()
    thread_list.append((thread, result_list))

# Wait for all threads to finish
for thread, result_list in thread_list:
    thread.join()

# Combine results from all threads
image_data = []
for _, result in thread_list:
    image_data.extend(result)
    print(f"len: {len(image_data)}", end='\r')
image_data = np.array(image_data)
image_data_file = '/home/share_folder/allen/269/image_data_9.npy'
print(image_data.shape)
print(f"saving...")
np.save(image_data_file, np.array(image_data)) 
# with open(image_data_file, 'wb') as fp:
#     pickle.dump(np.array(image_data), fp)
#     print('List of images saved successfully to file')