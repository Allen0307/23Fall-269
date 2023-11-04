import matplotlib.pyplot as plt
import numpy as np
import torch
import os
from tqdm import tqdm
from torchvision.datasets import CIFAR100
from transformers import CLIPProcessor, CLIPModel


def accuracy(output, target, topk=(1,)):
    pred = output.topk(max(topk), 1, True, True)[1].t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))
    return [float(correct[:k].reshape(-1).float().sum(0, keepdim=True).cpu().numpy()) for k in topk]

def benchmark(model_name, batch_size):
    # Build the model, preprocessor, and dataset
    cifar100 = CIFAR100(root=os.path.expanduser("~/.cache"), download=True, train=False)
    processor = CLIPProcessor.from_pretrained(model_name)
    model = CLIPModel.from_pretrained(model_name)

    # Prepare a sample input
    top1_accuracy, top5_accuracy = 0, 0
    text = []
    for c in cifar100.classes:
        text.append(f'a photo of a {c}')
    
    for i in range(len(cifar100)):
        image = cifar100[i][0]
        #display(image)
        inputs = processor(text=text, images=image, return_tensors="pt", padding=True)
        outputs = model(**inputs)

        logits_per_image = outputs.logits_per_image # this is the image-text similarity score
        probs = logits_per_image.softmax(dim=1) # we can take the softmax to get the label probabilities
        acc1, acc5 = accuracy(probs, torch.tensor([cifar100[i][1]]), topk=(1, 5))
        top1_accuracy += acc1
        top5_accuracy += acc5
    
    print("Top1 Accuracy: {}".format(top1_accuracy/len(cifar100)))
    print("Top5 Accuracy: {}".format(top5_accuracy/len(cifar100)))

if __name__ == '__main__':
    # Recommended batch sizes for throughput
    # openai/clip-vit-base-patch32: 64
    # openai/clip-vit-large-patch14: 4
    model_name = 'openai/clip-vit-base-patch32'
    batch_size = 64
    benchmark(model_name, batch_size)
