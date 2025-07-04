"""
Script d'indexation des documents MongoDB dans ChromaDB avec génération d'embeddings via OpenAI.
A lancer après avoir inséré les documents dans la collection 'documents' de la base 'mcp_backend'.
"""

import os
import chromadb
from chromadb.config import Settings
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
import os

# Initialisation du modèle local Sentence Transformers (MiniLM)
model = SentenceTransformer('all-MiniLM-L6-v2')

# Connexion à MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]
collection = db["documents"]

# Connexion à ChromaDB (stockage local par défaut)
persist_dir = os.path.abspath("chroma_data")
print("Chemin absolu de chroma_data (indexation):", persist_dir)
chroma_client = chromadb.PersistentClient(path=persist_dir)
collection_chroma = chroma_client.get_or_create_collection(name="cms_docs")

def get_embedding(text):
    """Génère un embedding local (Sentence Transformers) pour un texte donné."""
    return model.encode(text).tolist()

# Indexation des documents
for doc in collection.find():
    doc_id = str(doc["_id"])
    text = doc["title"] + "\n" + doc["content"]
    embedding = get_embedding(text)
    # Ajout dans ChromaDB
    collection_chroma.add(
    embeddings=[embedding],
    documents=[text],
    ids=[doc_id],
    metadatas=[{
        "category": doc.get("category", ""),
        "tags": ", ".join(doc.get("tags", []))
    }]
)
    print(f"Document {doc_id} indexé dans ChromaDB.")

print("Indexation terminée. Les documents sont prêts pour la recherche vectorielle !")
print("Nombre de docs dans ChromaDB (après indexation):", collection_chroma.count())
print("Tous les IDs dans ChromaDB (après indexation):", collection_chroma.get()['ids'])
