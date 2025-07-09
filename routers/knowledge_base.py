from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import subprocess
import sys

import models
import schemas
from dependencies import get_current_admin_user
from utils.kb_management import parse_and_insert_document
from database import get_db

router = APIRouter()

# Définir le chemin du répertoire pour les documents de la base de connaissances
KB_DIR = "knowledge_base_documents"

@router.on_event("startup")
def on_startup():
    os.makedirs(KB_DIR, exist_ok=True)

@router.post("/upload", response_model=schemas.Document, dependencies=[Depends(get_current_admin_user)])
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Téléverse, analyse et insère un document dans la base de connaissances via SQLAlchemy."""
    if not (file.filename.endswith(".pdf") or file.filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Type de fichier non supporté. Uniquement PDF et JSON.")

    file_path = os.path.join(KB_DIR, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde du fichier: {e}")
    finally:
        file.file.close()

    try:
        # Analyser le fichier et l'insérer via SQLAlchemy
        new_document = parse_and_insert_document(db, file_path, file.filename)
        return new_document
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents", response_model=List[schemas.Document], dependencies=[Depends(get_current_admin_user)])
async def list_documents(db: Session = Depends(get_db)):
    """Liste les documents présents dans la base de connaissances depuis la base SQL."""
    return db.query(models.Document).all()

@router.delete("/documents/{doc_id}", status_code=204, dependencies=[Depends(get_current_admin_user)])
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Supprime un document de la base de données et du système de fichiers."""
    doc_to_delete = db.query(models.Document).filter(models.Document.id == doc_id).first()

    if not doc_to_delete:
        raise HTTPException(status_code=404, detail="Document non trouvé.")

    file_path = os.path.join(KB_DIR, doc_to_delete.title)

    # Supprimer l'enregistrement de la base de données
    db.delete(doc_to_delete)
    db.commit()

    # Supprimer le fichier physique
    if os.path.exists(file_path):
        os.remove(file_path)

    return

@router.post("/reindex", dependencies=[Depends(get_current_admin_user)])
async def reindex_documents():
    """Déclenche le ré-indexage des documents en exécutant le script d'indexation."""
    try:
        python_executable = sys.executable
        script_path = os.path.join(os.path.dirname(__file__), "..", "index_docs_chroma.py")

        result = subprocess.run(
            [python_executable, script_path],
            capture_output=True, text=True, check=True
        )
        
        print(result.stdout)
        return {"message": "Ré-indexage terminé avec succès.", "output": result.stdout}

    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du ré-indexage: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du script de ré-indexage: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Une erreur inattendue est survenue: {e}")
