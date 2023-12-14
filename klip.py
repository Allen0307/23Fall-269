# %%
import pandas as pd
import string

# Specify the path to your TSV file
train_tsv_file_path = '/home/allenfu/cyc/23Fall-269/Train_GCC-training.tsv'
val_tsv_file_path = '/home/allenfu/cyc/23Fall-269/Validation_GCC-1.1.0-Validation.tsv'

# Read the TSV file into a DataFrame
train_df = pd.read_csv(train_tsv_file_path, delimiter='\t', header=None)[0]
val_df = pd.read_csv(val_tsv_file_path, delimiter='\t', header=None)[0]

def remove_spaces(sentence):
    for punctuation in string.punctuation:
        sentence = sentence.replace(f' {punctuation}', punctuation)
    return ' '.join(sentence.split())

train_df = train_df.apply(remove_spaces)
val_df = val_df.apply(remove_spaces)

# %%
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import T5Tokenizer

class Seq2SeqDataset(Dataset):
    def __init__(self, dataframe, tokenizer, processor, max_length=64):
        self.data = dataframe
        self.tokenizer = tokenizer
        self.processor = processor
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        source_sentence = self.data.iloc[idx]
        
        # Tokenize and encode the source sentence
        t5_tokens = self.tokenizer.encode_plus(
            source_sentence,
            add_special_tokens=True,
            max_length=self.max_length,
            return_tensors='pt',
            padding='max_length',
            truncation=True
        )

        t5_inputs =  {
            'input_ids': t5_tokens['input_ids'].squeeze(),
            'attention_mask': t5_tokens['attention_mask'].squeeze(),
            'target_ids': t5_tokens['input_ids'].squeeze(),  # Target is the same as the input
            'target_mask': t5_tokens['attention_mask'].squeeze(),
            'target': source_sentence
        }

        clip_tokens = self.processor(
            text=source_sentence, 
            images=torch.zeros((3, 224, 224)), 
            return_tensors="pt", 
            padding='max_length', 
            max_length=self.max_length, 
            truncation=True
        )

        clip_inputs = {
            'input_ids': clip_tokens['input_ids'].squeeze(),
            'attention_mask': clip_tokens['attention_mask'].squeeze(),
            'pixel_values': clip_tokens["pixel_values"].view(3, 224, 224),
            'target_ids': clip_tokens['input_ids'].squeeze(),  # Target is the same as the input
            'target_mask': clip_tokens['attention_mask'].squeeze(),
            'target': source_sentence
        }

        return clip_inputs, t5_inputs

# %%
import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from transformers import T5ForConditionalGeneration, T5Tokenizer, CLIPModel, CLIPProcessor
from tqdm import tqdm

class KLIPModel(torch.nn.Module):

    def __init__(self, class_num = 1000):
        super(KLIPModel, self).__init__()

        self.clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

        self.clip_to_llama = nn.Sequential(
          torch.nn.Linear(512, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, 4096),
        )

        self.classifier = nn.Sequential(
          torch.nn.Linear(512, 64),
          torch.nn.ReLU(),
          torch.nn.Linear(64, class_num),
          torch.nn.Softmax(),
        )

    def forward(self, input_ids, attention_mask, pixel_values):
        clip_output = self.clip(input_ids=input_ids, attention_mask=attention_mask, pixel_values=pixel_values)

        class_logits = self.classifier(clip_output.image_embeds)
        clip_to_llama_embeds = self.clip_to_llama(clip_output.text_embeds)

        similarity_loss = None
        labels = torch.ones((input_ids.shape[0],), dtype=torch.float32, device=input_ids.device)
        criterion = nn.CosineEmbeddingLoss(margin=0.2)
        similarity_loss = criterion(clip_output.text_embeds, clip_output.image_embeds, labels)

        return clip_output, clip_to_llama_embeds, class_logits, similarity_loss

# %%
class Bottleneck(nn.Module):
    def __init__(self, input_dim, output_dim, bottleneck_dim=4096):
        super(Bottleneck, self).__init__()
        self.blocks = nn.Sequential(
            # nn.Linear(input_dim, bottleneck_dim),
            # nn.LayerNorm(bottleneck_dim),
            # nn.ReLU(),
            # nn.Linear(bottleneck_dim, output_dim),
            nn.Linear(input_dim, output_dim),
            nn.LayerNorm(output_dim),
            nn.ReLU()
        )

        # self.layer = nn.Linear(input_dim, output_dim)
        # self.norm = nn.LayerNorm(output_dim)

    def forward(self, x):
        return self.blocks(x)

class KLIPEval(nn.Module):
    def __init__(self, klip_model_path, t5_model_path, device='cuda'):
        super(KLIPEval, self).__init__()
        self.encoder = KLIPModel()
        self.encoder.load_state_dict(torch.load(klip_model_path))
        self.bottleneck = Bottleneck(512, 768)
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

    def forward(self, clip_inputs, t5_inputs, train=True):
        if train:
            encoder_outputs = self.encoder.clip.text_model(
                input_ids=clip_inputs["input_ids"].to(self.device), 
                attention_mask=clip_inputs["attention_mask"].to(self.device),
            )

            encoder_outputs['last_hidden_state'] = self.bottleneck(encoder_outputs['last_hidden_state'])
            output = self.decoder(
                encoder_outputs=encoder_outputs,
                attention_mask=t5_inputs['attention_mask'].to(self.device),
                labels=t5_inputs['target_ids'].to(self.device)
            )
            return output.loss
        else:
            encoder_outputs = self.encoder.clip.text_model(
                input_ids=clip_inputs["input_ids"].to(self.device), 
                attention_mask=clip_inputs["attention_mask"].to(self.device),
            )

            encoder_outputs['last_hidden_state'] = self.bottleneck(encoder_outputs['last_hidden_state'])
            output = self.decoder.generate(
                # inputs_embeds=t5_inputs_embeds,
                encoder_outputs=encoder_outputs,
                attention_mask=t5_inputs['attention_mask'].to(self.device),
                decoder_input_ids=torch.tensor([[self.tokenizer.pad_token_id]] * t5_inputs['input_ids'].shape[0]).to(self.device),
                # max_length=64,  # Set a reasonable maximum length for generated sequences
                # num_beams=1,  # Set to 1 for greedy decoding
                # no_repeat_ngram_size=2,  # Avoid repeating bigrams in the output
                # early_stopping=True
            )
            return output

# %%
device = 'cuda'
# Load the T5 tokenizer
tokenizer = T5Tokenizer.from_pretrained("t5-base")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

# Create the dataset and DataLoader
train_dataset = Seq2SeqDataset(train_df, tokenizer, processor)
val_dataset = Seq2SeqDataset(val_df, tokenizer, processor)
train_dataloader = DataLoader(train_dataset, batch_size=128, shuffle=True, num_workers=4)
val_dataloader = DataLoader(val_dataset, batch_size=128, shuffle=False, num_workers=4)

# Initialize the autoencoder model
klip_model_path = '/home/allenfu/269/klip.pt'
# klip_model_path = '/home/allenfu/cyc/23Fall-269/klip.pt'
t5_model_path = '/home/allenfu/cyc/23Fall-269/t5_model.pth'
klip_model = KLIPEval(klip_model_path, t5_model_path, device).to(device)

# Define the optimizer and learning rate scheduler
optimizer = optim.AdamW(klip_model.bottleneck.parameters(), lr=1e-3)
scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.9)

# Training loop
num_epochs = 3
best_em_score = 0.0
for epoch in range(num_epochs):
    total_loss = 0
    klip_model.train()

    for clip_inputs, t5_inputs in tqdm(train_dataloader, desc=f'Epoch {epoch + 1}/{num_epochs}'):
        loss = klip_model(clip_inputs, t5_inputs, train=True)
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    average_loss = total_loss / len(train_dataloader)
    print(f'Epoch {epoch + 1}/{num_epochs}, Average Loss: {average_loss}')

    # Optionally update the learning rate
    scheduler.step()

    # Evaluate with Exact Match (EM) on a validation set
    klip_model.eval()
    with torch.no_grad():
        em_count = 0
        total_samples = 0

        for clip_inputs, t5_inputs in tqdm(val_dataloader, desc=f'Validation - Epoch {epoch + 1}'):
            # Generate sequences
            generated_ids = klip_model(clip_inputs, t5_inputs, train=False).detach().cpu().numpy()

            # Decode token IDs to strings
            generated_sentences = [tokenizer.decode(ids, skip_special_tokens=True) for ids in generated_ids]
            target_sentences = t5_inputs['target']

            # Check for exact match
            em_count += sum(1 for gen, target in zip(generated_sentences, target_sentences) if gen == target)
            total_samples += len(generated_sentences)

        em_score = em_count / total_samples
        print(f'Validation EM Score: {em_score}')

        # Save the model if the EM score improves
        if em_score > best_em_score:
            best_em_score = em_score
            torch.save(klip_model.state_dict(), 'klip_model.pth')
            print("Model saved!")


