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

class Bottleneck(nn.Module):
    def __init__(self, input_dim, output_dim, bottleneck_dim=4096):
        super(Bottleneck, self).__init__()
        self.blocks = nn.Sequential(
            nn.Linear(input_dim, output_dim),
            nn.LayerNorm(output_dim),
            nn.ReLU()
        )
    def forward(self, x):
        return self.blocks(x)

class KLIPEval(nn.Module):
    def __init__(self, classifier_model_path, encoder_model_path, t5_model_path, encoder_dim=512, decoder_dim=768, device='cuda'):
        super(KLIPEval, self).__init__()
        classifier = Classifier()
        classifier.load_state_dict(torch.load(classifier_model_path))
        self.encoder = KLIPModel(classifier=classifier)
        self.encoder.load_state_dict(torch.load(encoder_model_path))
        self.bottleneck = Bottleneck(encoder_dim, decoder_dim)
        self.decoder = T5ForConditionalGeneration.from_pretrained('t5-base')
        self.decoder.load_state_dict(torch.load(t5_model_path))
        self.tokenizer = T5Tokenizer.from_pretrained('t5-base')
        self.device = device

        # Set requires_grad to False for encoder and decoder parameters
        for param in self.encoder.parameters():
            param.requires_grad = False

        for param in self.decoder.parameters():
            param.requires_grad = False

        # Set requires_grad to True for dimension transform layer parameters
        for param in self.bottleneck.parameters():
            param.requires_grad = True

    def forward(self, encoder_inputs, decoder_inputs, train=True):
        encoder_outputs = self.encoder.clip.text_model(
            input_ids=encoder_inputs["input_ids"].to(self.device), 
            attention_mask=encoder_inputs["attention_mask"].to(self.device),
        )
        encoder_outputs['last_hidden_state'] = self.bottleneck(encoder_outputs['last_hidden_state'])
        if train:
            output = self.decoder(
                encoder_outputs=encoder_outputs,
                attention_mask=decoder_inputs['attention_mask'].to(self.device),
                labels=decoder_inputs['target_ids'].to(self.device)
            )
            return output.loss
        else:
            output = self.decoder.generate(
                encoder_outputs=encoder_outputs,
                attention_mask=decoder_inputs['attention_mask'].to(self.device),
                decoder_input_ids=torch.tensor([[self.tokenizer.pad_token_id]] * decoder_inputs['input_ids'].shape[0]).to(self.device),
            )
            return output
