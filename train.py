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

    return inputs, labels, llama_embeds

def collate_fn(batch):
    batch = list(filter(lambda x: x is not None, batch))
    return torch.utils.data.dataloader.default_collate(batch)

def contrastive_loss(logits: torch.Tensor) -> torch.Tensor:
    return nn.functional.cross_entropy(logits, torch.arange(len(logits), device=logits.device))

def clip_loss(similarity: torch.Tensor) -> torch.Tensor:
    caption_loss = contrastive_loss(similarity)
    image_loss = contrastive_loss(similarity.t())
    return (caption_loss + image_loss) / 2.0

class KLIPModel(torch.nn.Module):

    def __init__(self, clip_model, class_num = 1000):
        super(KLIPModel, self).__init__()

        self.clip = clip_model

        self.clip_to_llama = nn.Sequential(
          torch.nn.Linear(512, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, 4096),
        )

        self.classifier = nn.Sequential(
          torch.nn.Linear(1024, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, class_num),
          torch.nn.Softmax(),
        )

    def forward(self, x):
        clip_output = self.clip(**x)

        concate_embeds = torch.cat((clip_output.text_embeds, clip_output.image_embeds), 1)
        class_logits = self.classifier(concate_embeds)
        clip_to_llama_embeds = self.clip_to_llama(clip_output.text_embeds)

        return clip_output, clip_to_llama_embeds, class_logits
    
def Trainer(train_args, model, train_dataset, val_dataset):

  train_dataloader = DataLoader(train_dataset, batch_size = train_args["batch_size"], shuffle = True, collate_fn=collate_fn)
  val_dataloader = DataLoader(val_dataset, batch_size = train_args["batch_size"], shuffle = True, collate_fn=collate_fn)
  model = model.to(device)
  kmeans_loss = nn.CrossEntropyLoss()
  l2_loss = nn.MSELoss()
  optimizer = optim.AdamW(model.parameters(), lr = train_args["lr"])
  best_loss = float('inf')

  train_args["num_train_data"] = len(train_dataset)
  print(f"Training args: {train_args}")

  for epoch in range(train_args["epoch"]):

    model.train()
    for batch_idx, batch in tqdm(enumerate(train_dataloader)):
        
      inputs = batch
      # labels (N)
      inputs = inputs.to(device)
      outputs = model(inputs)

      clip_outpus, clip_to_llama_embeds, class_logits = outputs

      #class_logits (B* C) e.g., 64 * 1000
      #labels (B) e.g., 64
      loss = kmeans_loss(class_logits, labels)
      loss += l2_loss(clip_to_llama_embeds, llama_embeds)

      # backward pass
      loss.backward()
      optimizer.step()
      optimizer.zero_grad()

    model.eval()

    with torch.no_grad():
      val_correct = 0
      for batch_idx, batch in tqdm(enumerate(val_dataloader)):
        inputs = batch
        # labels
        inputs = inputs.to(device)
        outputs = model(inputs)

        clip_outpus, clip_to_llama_embeds, class_logits = outputs

        pred = torch.argmax(class_logits, dim=-1)
        val_correct +=  torch.sum(pred == labels)
    val_acc = val_correct / len(val_dataloader)

    if val_acc > best_loss:
      best_loss = val_acc
      torch.save(model, "klip.pt")
      print(f"Epoch: {epoch}, val_acc: {val_acc}, updating model...")
    else:
      print(f"Epoch: {epoch}, val_acc: {val_acc}")




if __name__ == "__main__":
  torch.manual_seed(0)
  device = torch.device('cuda')
  clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
  model = KLIPModel(clip_model=clip, class_num=1000)
  processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

  TRAIN_ROOT = "/home/share_folder/allen/269/train"
  image_path = os.listdir(TRAIN_ROOT)
  train_images = image_path[:200000]

  eval_images = image_path[200000:210000]

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
