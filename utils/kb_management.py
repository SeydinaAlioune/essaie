import os
import json
import fitz  # PyMuPDF
from pymongo import MongoClient
from datetime import datetime

# Connexion à MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]
doc_collection = db["documents"]

def parse_and_insert_document(file_path: str, filename: str):
    """
    Analyse un fichier (PDF ou JSON), extrait son contenu et l'insère dans MongoDB.
    """
    try:
        if filename.endswith(".pdf"):
            content = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    content += page.get_text()
            
            document_data = {
                "filename": filename,
                "title": os.path.splitext(filename)[0].replace('_', ' ').capitalize(),
                "content": content,
                "category": "Documentation",
                "tags": ["pdf", "upload"],
                "source_file": filename,
                "date": datetime.utcnow()
            }

        elif filename.endswith(".json"):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            document_data = {
                "filename": filename,
                "title": data.get("title", filename),
                "content": data.get("content", "Contenu non fourni"),
                "category": data.get("category", "Catégorie non fournie"),
                "tags": data.get("tags", []),
                "source_file": filename,
                "date": datetime.utcnow()
            }
        else:
            raise ValueError("Type de fichier non supporté")

        doc_collection.insert_one(document_data)
        return True, f"Document '{filename}' inséré avec succès dans MongoDB."

    except Exception as e:
        return False, f"Erreur lors du traitement du fichier '{filename}': {e}"
