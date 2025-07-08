from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from routers.auth import require_role
import os
import shutil
import subprocess
import sys
from utils.kb_management import parse_and_insert_document
from pymongo import MongoClient

router = APIRouter()

# Connexion à MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]
doc_collection = db["documents"]

# Définir le chemin du répertoire pour les documents de la base de connaissances
KB_DIR = "knowledge_base_documents"

@router.on_event("startup")
def on_startup():
    os.makedirs(KB_DIR, exist_ok=True)

@router.post("/upload", dependencies=[Depends(require_role("admin"))])
async def upload_document(file: UploadFile = File(...)):
    """Téléverse, analyse et insère un document dans la base de connaissances."""
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

    # Analyser le fichier et l'insérer dans MongoDB
    success, message = parse_and_insert_document(file_path, file.filename)
    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {"filename": file.filename, "message": message}

@router.get("/documents", dependencies=[Depends(require_role("admin"))])
async def list_documents():
    """Liste les documents présents dans la base de connaissances depuis MongoDB."""
    try:
        documents = doc_collection.find({}, {"_id": 0, "title": 1, "category": 1, "source_file": 1, "date": 1})
        return {"documents": list(documents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impossible de lister les documents depuis MongoDB: {e}")

@router.post("/reindex", dependencies=[Depends(require_role("admin"))])
async def reindex_documents():
    """Déclenche le ré-indexage des documents en exécutant le script d'indexation."""
    try:
        # Chemin vers l'interpréteur Python actuel et le script d'indexation
        python_executable = sys.executable
        script_path = os.path.join(os.path.dirname(__file__), "..", "index_docs_chroma.py")

        # Exécuter le script d'indexation dans un sous-processus
        result = subprocess.run(
            [python_executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Loguer la sortie standard du script (utile pour le débogage)
        print(result.stdout)

        return {"message": "Ré-indexage terminé avec succès.", "output": result.stdout}

    except subprocess.CalledProcessError as e:
        # Si le script retourne un code d'erreur
        print(f"Erreur lors du ré-indexage: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du script de ré-indexage: {e.stderr}")
    except Exception as e:
        # Pour toute autre erreur
        raise HTTPException(status_code=500, detail=f"Une erreur inattendue est survenue: {e}")
