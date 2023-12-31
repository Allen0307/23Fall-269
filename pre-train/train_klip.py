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
from model import KLIPModel
import numpy as np
# from torch.utils.tensorboard import SummaryWriter


class CLIPDataset(Dataset):
  def __init__(self, data_path, image_data, processor, root):

    self.dataset = data_path
    self.image_data = image_data
    self.processor = processor
    self.root = root

  def __len__(self):

    return len(self.dataset)

  def __getitem__(self, idx):
    
    text = self.dataset[idx].rstrip('.jpg')

    # image = Image.open(os.path.join(self.root, self.dataset[idx])).convert("RGB")
    # image = image.resize((224, 224))
    image = self.image_data[idx]
    
    inputs = processor(text=text, images=image, return_tensors="pt", padding='max_length', max_length = 64, truncation = True)
    inputs["input_ids"] = inputs["input_ids"].view(-1)
    inputs["attention_mask"] = inputs["attention_mask"].view(-1)
    inputs["pixel_values"] = inputs["pixel_values"].view(3, 224, 224)

    return inputs

def collate_fn(batch):
  batch = list(filter(lambda x: x is not None, batch))
  return torch.utils.data.dataloader.default_collate(batch)
    
def Trainer(train_args, model, train_dataset, val_dataset):
  device = torch.device('cuda')
  train_dataloader = DataLoader(train_dataset, batch_size = train_args["batch_size"], shuffle = True, num_workers=20, pin_memory=True)
  val_dataloader = DataLoader(val_dataset, batch_size = train_args["batch_size"], shuffle = True, num_workers=20, pin_memory=True)
  model = model.to(device)
  concept_loss = nn.CrossEntropyLoss()
  l2_loss = nn.MSELoss()
  optimizer = optim.AdamW(model.parameters(), lr = train_args["lr"])
  best_loss = float('inf')

  train_args["num_train_data"] = len(train_dataset)
  print(f"Training args: {train_args}")

  for epoch in range(train_args["epoch"]):

    model.train()
    for batch_idx, batch in enumerate(tqdm(train_dataloader)):
        
      inputs = batch
      # labels (N)
      inputs = inputs.to(device)

      outputs = model(**inputs, return_loss = True)

      loss = outputs.loss
      
      # backward pass
      loss.backward()
      optimizer.step()
      optimizer.zero_grad()

    model.eval()

    with torch.no_grad():
      val_correct = 0
      val_loss = 0
      for batch_idx, batch in enumerate(tqdm(val_dataloader)):
        inputs = batch
        # labels (N)
        inputs = inputs.to(device)
        outputs = model(**inputs, return_loss = True)

        # val_loss += concept_loss(class_logits, labels)
        val_loss += outputs.loss


    if val_loss < best_loss:
      best_loss = val_loss
      torch.save(model.state_dict(), "clip.pt")
      print(f"Epoch: {epoch}, val_loss: {val_loss}, updating model...")
    else:
      print(f"Epoch: {epoch}, val_loss: {val_loss}")




if __name__ == "__main__":
  torch.manual_seed(0)
  model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
  processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

  TRAIN_ROOT = "/home/share_folder/allen/269/train"
  TRAIN_DATA = '/home/share_folder/allen/269/clean_data_path.pkl'
  IMAGE_DATA = '/home/share_folder/allen/269/image_data.npy'

  with open(TRAIN_DATA, 'rb') as fp:
    image_path = pickle.load(fp)
  image_data = np.load(IMAGE_DATA)

  print(f"Train data: {len(image_path)}")
  train_images = image_path[100000:500000]
  eval_images = image_path[:100000]

  train_image_data = image_data[100000:500000]
  eval_image_data = image_data[:100000]

  print(f"Finished Loading Data...")
  train_dataset = CLIPDataset(train_images, train_image_data, processor, TRAIN_ROOT)
  val_dataset = CLIPDataset(eval_images, eval_image_data, processor, TRAIN_ROOT)


  train_args = {
    "epoch": 200,
    "lr": 0.00002,
    "batch_size": 128,
  }

  Trainer(
    train_args = train_args,
    model = model,
    train_dataset = train_dataset,
    val_dataset = val_dataset,
  )