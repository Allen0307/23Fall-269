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
from itertools import chain
# from torch.utils.tensorboard import SummaryWriter

class Intermidiate(torch.nn.Module):

    def __init__(self):
        super(Intermidiate, self).__init__()

        self.int = nn.Sequential(
          torch.nn.Linear(4096, 512),
        )

    def forward(self, x):

        class_logits = self.int(x)

        return class_logits
    
class Classifier(torch.nn.Module):

    def __init__(self, class_num = 1000):
        super(Classifier, self).__init__()

        self.classifier = nn.Sequential(
          torch.nn.Linear(512, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, class_num),
        )

    def forward(self, x):

        class_logits = self.classifier(x)

        return class_logits

class CLIPDataset(Dataset):
  def __init__(self, data_path, llama_embs, llama_labels, root):

    self.dataset = data_path
    self.llama_embs = llama_embs
    self.llama_labels = llama_labels
    self.root = root

  def __len__(self):

    return len(self.dataset)

  def __getitem__(self, idx):
    
    text = self.dataset[idx].rstrip('.jpg')
    llama_emb = self.llama_embs[text]
    llama_soft = self.llama_labels[text]


    return torch.tensor(llama_emb), torch.tensor(llama_soft, dtype=torch.long)

def collate_fn(batch):
  batch = list(filter(lambda x: x is not None, batch))
  return torch.utils.data.dataloader.default_collate(batch)
    
def Trainer(train_args, model_1, model_2, train_dataset, val_dataset):
  device = torch.device('cuda')
  train_dataloader = DataLoader(train_dataset, batch_size = train_args["batch_size"], shuffle = True, num_workers=20, pin_memory=True)
  val_dataloader = DataLoader(val_dataset, batch_size = train_args["batch_size"], shuffle = True, num_workers=20, pin_memory=True)
  model_1 = model_1.to(device)
  model_2 = model_2.to(device)
  cros_loss = nn.CrossEntropyLoss()

  parameters_to_optimize = chain(model_1.parameters(), model_2.parameters())
  optimizer = optim.AdamW(parameters_to_optimize, lr = train_args["lr"])
  best_acc = float('-inf')

  train_args["num_train_data"] = len(train_dataset)
  print(f"Training args: {train_args}")

  for epoch in range(train_args["epoch"]):

    model_1.train()
    model_2.train()
    for batch_idx, batch in enumerate(tqdm(train_dataloader)):
        
      llama_embs, labels = batch
      # labels (N)
      llama_embs, labels = llama_embs.to(device), labels.to(device)

      outputs = model_1(llama_embs)
      outputs = model_2(outputs)


      #class_logits (B* C) e.g., 64 * 1000
      #labels (B) e.g., 64
      loss = cros_loss(outputs, labels)

      
      # backward pass
      loss.backward()
      optimizer.step()
      optimizer.zero_grad()

    model_1.eval()
    model_2.eval()
    with torch.no_grad():
        val_correct = 0
        val_total = 0  # Initialize a variable to keep track of the total number of samples
        val_loss = 0

        for batch_idx, batch in enumerate(tqdm(val_dataloader)):
            llama_embs, labels = batch
            llama_embs, labels = llama_embs.to(device), labels.to(device)

            outputs = model_1(llama_embs)
            outputs = model_2(outputs)

            val_loss += cros_loss(outputs, labels)

            pred = torch.argmax(outputs, dim=-1)
            val_correct += torch.sum(pred == labels)
            val_total += labels.size(0)  # Increment the total number of samples

    # Compute accuracy
    val_acc = val_correct / val_total

    if val_acc > best_acc:
      best_acc = val_acc
      torch.save(model_2.state_dict(), "classifier.pt")
      print(f"Epoch: {epoch}, val_loss: {val_loss.item()}, val_acc: {val_acc}, updating model...")
    # else:
    #   #print(f"Epoch: {epoch}, val_loss: {val_loss.item()}, val_acc: {val_acc}")




if __name__ == "__main__":
  torch.manual_seed(0)

  model_1 = Intermidiate()
  model_2 = Classifier()

  TRAIN_ROOT = "/home/share_folder/allen/269/train"
  TRAIN_DATA = '/home/share_folder/allen/269/clean_data_path.pkl'
  IMAGE_DATA = '/home/share_folder/allen/269/image_data.npy'

  with open(TRAIN_DATA, 'rb') as fp:
    image_path = pickle.load(fp)


  print(f"Train data: {len(image_path)}")
  train_images = image_path[100000:500000]
  eval_images = image_path[:100000]

  llama2_embed_file = '/home/share_folder/allen/269/llama2_embedding.pkl'
  llama2_soft_labels_file = '/home/share_folder/allen/269/llama2_soft_labels_1000.pkl'
  
  with open(llama2_embed_file, 'rb') as fp:
    llama2_embedding = pickle.load(fp)
  
  with open(llama2_soft_labels_file, 'rb') as fp:
    llama2_soft_labels = pickle.load(fp)

  print(f"Finished Loading Data...")
  train_dataset = CLIPDataset(train_images, llama2_embedding, llama2_soft_labels, TRAIN_ROOT)
  val_dataset = CLIPDataset(eval_images, llama2_embedding, llama2_soft_labels, TRAIN_ROOT)


  train_args = {
    "epoch": 200,
    "lr": 0.00002,
    "batch_size": 128,
  }

  Trainer(
    train_args = train_args,
    model_1 = model_1,
    model_2 = model_2,
    train_dataset = train_dataset,
    val_dataset = val_dataset,
  )