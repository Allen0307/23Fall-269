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

class CLIPDataset(Dataset):
  def __init__(self, data_path, processor, root):

    self.dataset = data_path
    self.processor = processor
    self.root = root

  def __len__(self):

    return len(self.dataset)

  def __getitem__(self, idx):

    text = self.dataset[idx].split(".jpg")[-2]

    try:
      image = Image.open(os.path.join(self.root, self.dataset[idx]))
      image = image.resize((224,224))
    except: 
      return None

    inputs = processor(text=text, images=image, return_tensors="pt", padding='max_length', max_length = 64, truncation = True)
    inputs["input_ids"] = inputs["input_ids"].view(-1)
    inputs["attention_mask"] = inputs["attention_mask"].view(-1)
    inputs["pixel_values"] = inputs["pixel_values"].view(3, 224, 224)

    return inputs

def collate_fn(batch):
    batch = list(filter(lambda x: x is not None, batch))
    return torch.utils.data.dataloader.default_collate(batch)

def contrastive_loss(logits: torch.Tensor) -> torch.Tensor:
    return nn.functional.cross_entropy(logits, torch.arange(len(logits), device=logits.device))

def clip_loss(similarity: torch.Tensor) -> torch.Tensor:
    caption_loss = contrastive_loss(similarity)
    image_loss = contrastive_loss(similarity.t())
    return (caption_loss + image_loss) / 2.0

def Trainer(train_args, model, train_dataset, val_dataset):

  train_dataloader = DataLoader(train_dataset, batch_size = train_args["batch_size"], shuffle = True, collate_fn=collate_fn)
  val_dataloader = DataLoader(val_dataset, batch_size = train_args["batch_size"], shuffle = True, collate_fn=collate_fn)
  model = model.to(device)
  optimizer = optim.AdamW(model.parameters(), lr = train_args["lr"])
  best_loss = float('inf')

  train_args["num_train_data"] = len(train_dataset)
  print(f"Training args: {train_args}")

  for epoch in range(train_args["epoch"]):

    model.train()
    for batch_idx, batch in tqdm(enumerate(train_dataloader)):
        
        mini_batch_size = train_args["mini_batch_size"]
        if batch.shape[0] % mini_batch_size != 0:
          mini_steps = batch.shape[0] // mini_batch_size + 1
        else:
          mini_steps = batch.shape[0] // mini_batch_size 

        text_embeds = None
        image_embeds = None

        for mini_batch_idx in range(mini_steps):

          if mini_batch_idx + 1 != mini_steps:
            inputs = batch[mini_batch_idx * mini_batch_size: mini_batch_idx * (mini_batch_size + 1)]
          else:
            inputs = batch[mini_batch_idx * mini_batch_size:]

          inputs = inputs.to(device)
          outputs = model(**inputs)

          tmp_text_embeds = outputs.text_embeds
          tmp_image_embeds = outputs.image_embeds

          if not text_embeds:
            text_embeds = tmp_text_embeds
            image_embeds = tmp_image_embeds
          else:
            text_embeds = torch.cat((text_embeds, tmp_text_embeds), 0)
            image_embeds = torch.cat((image_embeds, tmp_image_embeds), 0)
        
        # cosine similarity as logits
        logit_scale = model.logit_scale
        logits_per_text = torch.matmul(text_embeds, image_embeds.t()) * logit_scale
        # logits_per_image = logits_per_text.t()

        loss = None
        loss = clip_loss(logits_per_text)

        # backward pass
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()

    model.eval()
    eval_loss = 0
    with torch.no_grad():
      for batch_idx, batch in tqdm(enumerate(val_dataloader)):
        inputs = batch
        inputs = inputs.to(device)

        outputs = model(**inputs)
        loss = clip_loss(outputs.logits_per_text)
        eval_loss += loss
    if eval_loss < best_loss:
      best_loss = eval_loss
      torch.save(model, "clip.pt")
      print(f"Epoch: {epoch}, eval_loss: {eval_loss}, updating model...")
    else:
      print(f"Epoch: {epoch}, eval_loss: {eval_loss}")




if __name__ == "__main__":
  torch.manual_seed(0)
  device = torch.device('cuda')
  model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
  processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

  TRAIN_ROOT = "/home/share_folder/allen/269/train"
  image_path = os.listdir(TRAIN_ROOT)
  train_images = image_path[2000:]

  eval_images = image_path[:2000]

  train_dataset = CLIPDataset(train_images, processor, TRAIN_ROOT)
  val_dataset = CLIPDataset(eval_images, processor, TRAIN_ROOT)


  train_args = {
    "epoch": 50,
    "lr": 0.0002,
    "mini_batch_size": 256,
    "batch_size": 32768,
  }

  Trainer(
    train_args = train_args,
    model = model,
    train_dataset = train_dataset,
    val_dataset = val_dataset
  )
