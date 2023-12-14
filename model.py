import torch
import torch.nn as nn
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