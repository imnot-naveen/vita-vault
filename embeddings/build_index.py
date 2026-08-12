import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from tqdm import tqdm
import config

CHUNKS_PATH = "data/chunks/chunks.jsonl"
BATCH_SIZE = 128

def get_client():
    return QdrantClient(url=config.QDRANT_URL)

def ensure_collection(client):
    collections = [c.name for c in client.get_collections().collections]
    if config.COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config=VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{config.COLLECTION_NAME}'")
    else:
        print(f"Collection '{config.COLLECTION_NAME}' already exists")

def load_chunks():
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def build():
    model = SentenceTransformer(config.EMBED_MODEL)
    client = get_client()
    ensure_collection(client)

    chunks = load_chunks()
    points = []
    point_id = 0

    for row in tqdm(chunks, desc="Embedding + uploading"):
        vector = model.encode(row["chunk"], normalize_embeddings=True).tolist()
        payload = {k: v for k, v in row.items() if v is not None}
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        point_id += 1

        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=config.COLLECTION_NAME, points=points)
            points = []

    if points:
        client.upsert(collection_name=config.COLLECTION_NAME, points=points)

    count = client.count(collection_name=config.COLLECTION_NAME).count
    print(f"Index built. Total points in collection: {count}")

if __name__ == "__main__":
    build()