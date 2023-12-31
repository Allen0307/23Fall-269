# %%
import pandas as pd
import string
import torch
from torch.utils.data import Dataset, DataLoader
from torch import nn, optim
from tqdm import tqdm
from model import KLIPEval

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
class Seq2SeqDataset(Dataset):
    def __init__(self, dataframe, encoder_tokenizer, decoder_tokenizer, max_length=64):
        self.data = dataframe
        self.encoder_tokenizer = encoder_tokenizer
        self.decoder_tokenizer = decoder_tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        source_sentence = self.data.iloc[idx]
        
        # Tokenize and encode the source sentence
        encoder_tokens = self.encoder_tokenizer.encode_plus(
            source_sentence,
            add_special_tokens=True,
            max_length=self.max_length,
            return_tensors='pt',
            padding='max_length',
            truncation=True
        )

        encoder_inputs =  {
            'input_ids': encoder_tokens['input_ids'].squeeze(),
            'attention_mask': encoder_tokens['attention_mask'].squeeze(),
            'target_ids': encoder_tokens['input_ids'].squeeze(),
            'target_mask': encoder_tokens['attention_mask'].squeeze(),
            'target': source_sentence
        }

        decoder_tokens = self.decoder_tokenizer(
            text=source_sentence, 
            images=torch.zeros((3, 224, 224)), 
            return_tensors="pt", 
            padding='max_length', 
            max_length=self.max_length, 
            truncation=True
        )

        decoder_inputs = {
            'input_ids': decoder_tokens['input_ids'].squeeze(),
            'attention_mask': decoder_tokens['attention_mask'].squeeze(),
            'pixel_values': decoder_tokens["pixel_values"].view(3, 224, 224),
            'target_ids': decoder_tokens['input_ids'].squeeze()
            'target_mask': decoder_tokens['attention_mask'].squeeze(),
            'target': source_sentence
        }

        return encoder_inputs, decoder_inputs

# %%
device = 'cuda'
# Load the T5 tokenizer
encoder_tokenizer = T5Tokenizer.from_pretrained("t5-base")
decoder_tokenizer = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

# Create the dataset and DataLoader
train_dataset = Seq2SeqDataset(train_df, encoder_tokenizer, decoder_tokenizer)
val_dataset = Seq2SeqDataset(val_df, encoder_tokenizer, decoder_tokenizer)
train_dataloader = DataLoader(train_dataset, batch_size=128, shuffle=True, num_workers=4)
val_dataloader = DataLoader(val_dataset, batch_size=128, shuffle=False, num_workers=4)

# Initialize the autoencoder model
encoder_model_path = '/home/allenfu/269/klip_freeze.pt'
classifier_model_path = '/home/allenfu/269/classifier.pt'
decoder_model_path = '/home/allenfu/cyc/23Fall-269/t5_model.pth'
encoder_dim = 512
decoder_dim = 768
model = KLIPEval(classifier_model_path, encoder_model_path, decoder_model_path, encoder_dim, decoder_dim, device).to(device)

# Define the optimizer and learning rate scheduler
optimizer = optim.AdamW(model.bottleneck.parameters(), lr=1e-3)
scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.9)

# Training loop
num_epochs = 3
best_em_score = 0.0
for epoch in range(num_epochs):
    total_loss = 0
    model.train()

    for encoder_inputs, decoder_inputs in tqdm(train_dataloader, desc=f'Epoch {epoch + 1}/{num_epochs}'):
        loss = model(encoder_inputs, decoder_inputs, train=True)
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

    average_loss = total_loss / len(train_dataloader)
    print(f'Epoch {epoch + 1}/{num_epochs}, Average Loss: {average_loss}')

    # Optionally update the learning rate
    scheduler.step()

    # Evaluate with Exact Match (EM) on a validation set
    model.eval()
    with torch.no_grad():
        em_count = 0
        total_samples = 0

        for encoder_inputs, decoder_inputs in tqdm(val_dataloader, desc=f'Validation - Epoch {epoch + 1}'):
            # Generate sequences
            generated_ids = model(encoder_inputs, decoder_inputs, train=False).detach().cpu().numpy()

            # Decode token IDs to strings
            generated_sentences = [tokenizer.decode(ids, skip_special_tokens=True) for ids in generated_ids]
            target_sentences = decoder_inputs['target']

            # Check for exact match
            em_count += sum(1 for gen, target in zip(generated_sentences, target_sentences) if gen == target)
            total_samples += len(generated_sentences)

        em_score = em_count / total_samples
        print(f'Validation EM Score: {em_score}')

        # Save the model if the EM score improves
        if em_score > best_em_score:
            best_em_score = em_score
            torch.save(model.state_dict(), 'model.pth')
            print("Model saved!")
