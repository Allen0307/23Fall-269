import pickle

llama2_embed_file = '/home/share_folder/allen/269/llama2_embedding.pkl'
with open(llama2_embed_file, 'rb') as fp:
    llama2_embedding = pickle.load(fp)

print("Llama embds loading done...")

llama2_tensor = [v for k, v in llama2_embedding.items()]
print(f"num: {len(llama2_tensor)}")
from sklearn.cluster import MiniBatchKMeans

kmeans_llama = MiniBatchKMeans(n_clusters=100, batch_size=3072)
#kmeans_clip = MiniBatchKMeans(n_clusters=1000, batch_size=3072)
result_llama = kmeans_llama.fit(llama2_tensor)
#result_clip = kmeans_clip.fit(clip_embedding)

result = list(result_llama.labels_)

kmeans_result = {}
i = 0
for k, v in llama2_embedding.items():
    kmeans_result[k] = result[i]
    i += 1

import pickle
llama2_soft_file = '/home/share_folder/allen/269/llama2_soft_labels_100.pkl'
with open(llama2_soft_file, 'wb') as fp:
    pickle.dump(kmeans_result, fp)
    print('dictionary saved successfully to file')