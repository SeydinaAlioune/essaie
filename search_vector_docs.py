"""
Script de recherche vectorielle sur les documents indexés dans ChromaDB.
- Saisissez une question en français.
- Le script affiche les documents internes les plus pertinents (titre, catégorie, extrait).
"""

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from pymongo import MongoClient
import os

# Initialisation du modèle d'embedding local
model = SentenceTransformer('all-MiniLM-L6-v2')

# Connexion à ChromaDB
persist_dir = os.path.abspath("chroma_data")
print("Chemin absolu de chroma_data (recherche):", persist_dir)
chroma_client = chromadb.PersistentClient(path=persist_dir)
collection_chroma = chroma_client.get_or_create_collection(name="cms_docs")
print("Nombre de docs dans ChromaDB (au lancement recherche):", collection_chroma.count())
print("Tous les IDs dans ChromaDB (au lancement recherche):", collection_chroma.get()['ids'])

# Connexion à MongoDB pour récupérer les infos complètes
client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]
doc_collection = db["documents"]

def search_vector(question, top_k=3):
    query_embedding = model.encode(question).tolist()
    results = collection_chroma.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    from bson import ObjectId
    ids = results["ids"][0]
    print("IDs retournés par ChromaDB :", ids)
    print("Tous les IDs dans ChromaDB :", collection_chroma.get()['ids'])
    docs = []
    for doc_id in ids:
        try:
            mongo_id = ObjectId(doc_id)
        except Exception:
            mongo_id = doc_id  # fallback for non-ObjectId ids
        doc = doc_collection.find_one({"_id": mongo_id})
        if doc:
            docs.append(doc)
    return docs

if __name__ == "__main__":
    question = input("Pose ta question : ")
    docs = search_vector(question)
    print("\n--- Résultats les plus pertinents ---")
    for i, doc in enumerate(docs, 1):
        print(f"\n[{i}] {doc['title']} (Catégorie : {doc.get('category', '')})")
        print(f"Extrait : {doc['content'][:200]}...")
