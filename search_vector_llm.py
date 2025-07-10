"""
Recherche vectorielle + génération de réponse naturelle via LLM local (Ollama).
- Nécessite Ollama installé et lancé (https://ollama.com/)
- Le modèle doit être téléchargé (ex : llama3, mistral, phi3...)
"""

import os
import requests
from groq import Groq
import together
from sentence_transformers import SentenceTransformer
import chromadb
from pymongo import MongoClient
from bson import ObjectId

# --- PARAMÈTRES ---
OLLAMA_URL = "http://localhost:11434/api/generate"  # API locale Ollama
# Par défaut, utilise le modèle local 'llama3:8b' (modifiez la variable d'environnement OLLAMA_MODEL pour changer)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")
TOP_K = 3

# Chemin absolu et robuste pour la base ChromaDB
script_dir = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(script_dir, "chroma_data")
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


def build_prompt(question, context=None, history=None):
    """Construit le prompt pour le LLM, en incluant le contexte et l'historique de conversation."""
    context_txt = ""
    if context:
        context_txt = "\n\n".join([
            (f"Titre : {doc.get('title','')}\n"
             f"Catégorie : {doc.get('category','')}\n"
             f"Contenu : {doc.get('content','')[:600]}...") for doc in context
        ])

    history_txt = ""
    if history:
        # Formate l'historique pour le prompt. On attend une liste de dictionnaires avec 'question' et 'response'.
        history_txt = "\n".join([f"Ancien message de l'Utilisateur: {turn.get('question', '')}\nAncienne réponse de l'Assistant: {turn.get('response', '')}" for turn in history])
        history_txt += "\n\n" # Ajoute une séparation

    prompt = f"""
Tu es un assistant GLPI expert en helpdesk. Ton rôle est d'analyser la demande de l'utilisateur et de répondre de manière appropriée en suivant des règles strictes.

--- RÈGLES OBLIGATOIRES ---
1.  **Analyse d'Intention d'Abord** : Ta première tâche est de déterminer l'intention de l'utilisateur. Les intentions possibles sont :
    - `SALUTATION`: Si l'utilisateur dit juste bonjour, au revoir, merci.
    - `CREATION_TICKET`: Si l'utilisateur décrit explicitement un problème, une erreur, ou demande à créer un ticket.
    - `FAQ`: Pour toutes les autres questions générales ou demandes d'information.
2.  **Remplissage Conditionnel** : Ne remplis les champs `TITRE` et `DESCRIPTION` que si l'intention est `CREATION_TICKET` et que l'utilisateur a fourni ces détails. Pour toute autre intention, ces champs DOIVENT être `inconnue`.
3.  **Gestion de l'Historique** : Utilise l'historique pour comprendre le contexte et ne jamais redemander une information déjà fournie.
4.  **Réponse à l'Utilisateur** : La `REPONSE` doit toujours être polie, concise et directement liée à la question actuelle.

--- FORMAT DE RÉPONSE STRICT ---
INTENTION: <SALUTATION|CREATION_TICKET|FAQ|SUIVI_TICKET|AUTRE>
TITRE: <titre complet du problème ou 'inconnue'>
DESCRIPTION: <description détaillée du problème ou 'inconnue'>
PRIORITE: <basse|normale|haute|urgente|inconnue>
CATEGORIE: <matériel|logiciel|réseau|autre|inconnue>
URGENCE: <oui|non|inconnue>
TICKET_ID: <numéro si pertinent ou 'inconnue'>
REPONSE: <ta réponse à afficher à l'utilisateur pour CE tour de conversation>

--- EXEMPLES ---
- Utilisateur: "Bonjour"
  INTENTION: SALUTATION
  TITRE: inconnue
  DESCRIPTION: inconnue
  REPONSE: Bonjour ! Comment puis-je vous aider aujourd'hui ?

- Utilisateur: "J'ai une question sur mon mot de passe."
  INTENTION: FAQ
  TITRE: inconnue
  DESCRIPTION: inconnue
  REPONSE: Bien sûr, quelle est votre question concernant votre mot de passe ?

- Utilisateur: "Mon écran est tout noir."
  INTENTION: CREATION_TICKET
  TITRE: Écran noir
  DESCRIPTION: L'écran de l'ordinateur est tout noir.
  REPONSE: Je vois. Pour créer un ticket, pouvez-vous me donner plus de détails sur le moment où c'est arrivé ?

--- CONTEXTE ET CONVERSATION ---
Contexte FAQ pertinent (si disponible) : {context_txt}

Historique de la conversation actuelle :
{history_txt}
Question actuelle de l'utilisateur :
{question}

--- TA MISSION ---
Analyse la question actuelle en te basant sur les règles, les exemples et le contexte. Fournis une réponse structurée dans le format demandé.
Assistant: {CMS}
"""
    return prompt

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")

def call_llm(prompt):
    """Aiguilleur qui choisit le fournisseur LLM (Groq, Together ou Ollama) en fonction des variables d'environnement."""
    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        print("Utilisation du fournisseur LLM externe : Groq")
        try:
            client = Groq(api_key=GROQ_API_KEY)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"[Erreur lors de l'appel à Groq : {e}]"

    elif LLM_PROVIDER == "together" and TOGETHER_API_KEY:
        print("Utilisation du fournisseur LLM externe : Together AI")
        try:
            client = together.Together(api_key=TOGETHER_API_KEY)
            response = client.chat.completions.create(
                model="meta-llama/Llama-3-8b-chat-hf",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[Erreur lors de l'appel à Together AI : {e}]"

    else:
        print(f"Utilisation du fournisseur LLM local : Ollama ({OLLAMA_MODEL})")
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=180)
            response.raise_for_status()
            return response.json().get("response", "Réponse invalide d'Ollama")
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
        reponse = call_llm(prompt)
        print("\n--- Réponse générée ---\n")
        print(reponse)
