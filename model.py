import torch
import torch.nn as nn

def contrastive_loss(logits: torch.Tensor) -> torch.Tensor:
    return nn.functional.cross_entropy(logits, torch.arange(len(logits), device=logits.device))


def clip_loss(similarity: torch.Tensor) -> torch.Tensor:
    caption_loss = contrastive_loss(similarity)
    image_loss = contrastive_loss(similarity.t())
    return (caption_loss + image_loss) / 2.0

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
    
class KLIPModel(torch.nn.Module):

    def __init__(self, clip_model, class_num = 1000, classifier = None):
        super(KLIPModel, self).__init__()

        self.clip = clip_model

        self.clip_to_llama = nn.Sequential(
          torch.nn.Linear(512, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, 4096),
        )

        if classifier is not None:
          self.classifier = classifier
          for param in self.classifier.parameters():
            param.requires_grad = False
        else:
          self.classifier = nn.Sequential(
            torch.nn.Linear(512, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, class_num),
          )

    def forward(self, x):
        clip_output = self.clip(**x, return_loss = True)

        class_logits = self.classifier(clip_output.image_embeds)
        clip_to_llama_embeds = self.clip_to_llama(clip_output.text_embeds)

        # similarity_loss = None
        # labels = torch.ones((x["input_ids"].shape[0],), dtype=torch.float32, device=x["input_ids"].device)
        # criterion = nn.CosineEmbeddingLoss(margin=0.2)
        # similarity_loss = criterion(clip_output.text_embeds, clip_output.image_embeds, labels)

        return clip_output, clip_to_llama_embeds, class_logits, clip_output.loss