"""
Recherche vectorielle + génération de réponse naturelle via LLM local (Ollama).
- Nécessite Ollama installé et lancé (https://ollama.com/)
- Le modèle doit être téléchargé (ex : llama3, mistral, phi3...)
"""

import os
import requests
from sentence_transformers import SentenceTransformer
import chromadb
from pymongo import MongoClient
from bson import ObjectId

# --- PARAMÈTRES ---
OLLAMA_URL = "http://localhost:11434/api/generate"  # API locale Ollama
# Par défaut, utilise le modèle local 'llama3:8b' (modifiez la variable d'environnement OLLAMA_MODEL pour changer)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")
TOP_K = 3

# Chemin absolu pour la base ChromaDB
CHROMA_PATH = os.path.abspath("chroma_data")
print("Chemin absolu de chroma_data (recherche+LLM):", CHROMA_PATH)

model = SentenceTransformer('all-MiniLM-L6-v2')
persist_dir = CHROMA_PATH
chroma_client = chromadb.PersistentClient(path=persist_dir)
collection_chroma = chroma_client.get_or_create_collection(name="cms_docs")  # Collection ChromaDB utilisée pour la recherche vectorielle

# Signature CMS pour le prompt
CMS = """
Vous êtes un assistant virtuel pour le support technique d'une plateforme interne.
"""

from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]
doc_collection = db["documents"]  # Collection MongoDB contenant les documents à indexer/rechercher

def search_vector(question, top_k=TOP_K):
    query_embedding = model.encode(question).tolist()
    results = collection_chroma.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    ids = results["ids"][0]
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


def build_prompt(question, context=None):
    # Nouveau prompt enrichi pour extraction d'intention et de champs structurés
    # Ajoute un bloc 'Contexte FAQ pertinent' avant la question utilisateur
    context_txt = ""
    if context:
        # Correction : chaque f-string doit être sur une seule ligne, pas de retour à la ligne non terminé
        context_txt = "\n\n".join([
            (f"Titre : {doc.get('title','')}\n"
             f"Catégorie : {doc.get('category','')}\n"
             f"Contenu : {doc.get('content','')[:600]}...") for doc in context
        ])
    prompt = f"""
Tu es un assistant GLPI expert en helpdesk. Ton objectif est de :
- Détecter l'intention de l'utilisateur parmi : FAQ, création de ticket, suivi de ticket, modification de ticket, relance, autre.
- Si intention création de ticket, extraire les champs structurés suivants si présents :
  - titre (sujet du problème)
  - description (détail du problème)
  - priorité (basse, normale, haute, urgente)
  - catégorie (matériel, logiciel, réseau, autre)
  - urgence (oui/non)
- Si c'est une FAQ, donne une réponse concise et claire.
- Si c'est une demande de suivi, modification ou relance, identifie le numéro du ticket si possible.
- Si l'utilisateur ne donne pas assez d'informations pour créer un ticket, indique explicitement les champs manquants.

Format de réponse attendu :
INTENTION: <FAQ|CREATION_TICKET|SUIVI_TICKET|MODIFICATION_TICKET|RELANCE|AUTRE>
TITRE: <...>
DESCRIPTION: <...>
PRIORITE: <basse|normale|haute|urgente|inconnue>
CATEGORIE: <matériel|logiciel|réseau|autre|inconnue>
URGENCE: <oui|non|inconnue>
TICKET_ID: <numéro si pertinent>
REPONSE: <réponse concise et claire à afficher à l'utilisateur>

Contexte FAQ pertinent (utilise-le pour répondre si possible) :
{context_txt}

Question utilisateur :
{question}

En t'appuyant uniquement sur ces documents, rédige une réponse claire, concise et professionnelle en français, adaptée à un utilisateur non technique.
Cordialement, {CMS}
"""
    return prompt

def call_ollama(prompt):
    print(f"Appel à Ollama avec le modèle : {OLLAMA_MODEL}")
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        return f"[Erreur lors de l'appel à Ollama : {e}]"

if __name__ == "__main__":
    question = input("Pose ta question : ")
    docs = search_vector(question)
    if not docs:
        print("Aucun document pertinent trouvé.")
    else:
        print("\n--- Documents utilisés comme contexte ---")
        for i, doc in enumerate(docs, 1):
            print(f"[{i}] {doc['title']} (Catégorie : {doc.get('category', '')})")
        prompt = build_prompt(question, docs)
        print("\n--- Génération de la réponse via LLM local... ---")
        reponse = call_ollama(prompt)
        print("\n--- Réponse générée ---\n")
        print(reponse)
