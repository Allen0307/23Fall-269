import pickle


# def concate(dic, i):
#     llama2_embed_file = f'/home/share_folder/allen/269/llama2_embedding_{i}.pkl'
#     with open(llama2_embed_file, 'rb') as fp:
#         llama2_embedding = pickle.load(fp)
#     dic.update(llama2_embedding)

#     return dic

# llama_embeds = {}

# for i in range(10):
#     concate(llama_embeds, i)
#     print(f"Done {i} part...")

# print(len(llama_embeds.keys()))

# import pickle
# llama2_embed_file = '/home/share_folder/allen/269/llama2_embedding.pkl'
# with open(llama2_embed_file, 'wb') as fp:
#     pickle.dump(llama_embeds, fp)
#     print('dictionary saved successfully to file')

import numpy as np

def concate(a, i):
    IMAGE_DATA = f'/home/share_folder/allen/269/image_data_{i}.npy'
    b = np.load(IMAGE_DATA)
    a = np.concatenate((a, b), axis=0)
    print(f"Successfully concate {i}")
    return a

IMAGE_DATA = f'/home/share_folder/allen/269/image_data_0.npy'
a = np.load(IMAGE_DATA)

for i in range(1, 5):
    a = concate(a, i)

image_data_file = '/home/share_folder/allen/269/image_data.npy'
print(a.shape)
print(f"saving...")
np.save(image_data_file, a) 