import os
import json
import fitz  # PyMuPDF
from sqlalchemy.orm import Session
from models import Document


def parse_and_insert_document(db: Session, file_path: str, filename: str):
    """
    Analyse un fichier (PDF ou JSON), crée un objet Document SQLAlchemy et l'insère en base.
    Lève une ValueError en cas d'erreur.
    """
    try:
        if filename.endswith(".pdf"):
            content = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    content += page.get_text()
            
            document_data = {
                "title": os.path.splitext(filename)[0].replace('_', ' ').capitalize(),
                "content": content,
                "category": "Documentation PDF",
                "roles_allowed": ["admin", "support", "agent"]  # Rôles par défaut pour KB
            }

        elif filename.endswith(".json"):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            document_data = {
                "title": data.get("title", filename),
                "content": data.get("content", "Contenu non fourni"),
                "category": data.get("category", "Documentation JSON"),
                "roles_allowed": data.get("roles_allowed", ["admin", "support", "agent"])
            }
        else:
            raise ValueError("Type de fichier non supporté")

        # Créer et insérer le document via SQLAlchemy
        new_document = Document(**document_data)
        db.add(new_document)
        db.commit()
        db.refresh(new_document)
        return new_document

    except Exception as e:
        # Propage l'exception pour que le routeur puisse la gérer
        raise ValueError(f"Erreur lors du traitement du fichier '{filename}': {e}") from e
