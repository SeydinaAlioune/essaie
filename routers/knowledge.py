from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List
import os
import shutil
from dependencies import get_current_admin_user

router = APIRouter(
    prefix="/api/admin/knowledge",
    tags=["knowledge_base"],
    dependencies=[Depends(get_current_admin_user)]
)

# Définir le chemin du répertoire où les documents sont stockés
KNOWLEDGE_BASE_DIR = "./knowledge_base_documents"

# S'assurer que le répertoire existe au démarrage
@router.on_event("startup")
def on_startup():
    os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)


@router.get("/documents", response_model=List[str])
def list_documents():
    """Liste tous les documents dans la base de connaissances."""
    try:
        # Retourne la liste des noms de fichiers dans le répertoire
        return sorted([f for f in os.listdir(KNOWLEDGE_BASE_DIR) if os.path.isfile(os.path.join(KNOWLEDGE_BASE_DIR, f))])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur du serveur lors de la lecture des documents: {e}")


@router.post("/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """Téléverse un ou plusieurs documents."""
    uploaded_files = []
    for file in files:
        file_path = os.path.join(KNOWLEDGE_BASE_DIR, file.filename)
        
        # Vérifier si le fichier existe déjà pour éviter les doublons
        if os.path.exists(file_path):
            # Optionnel: on peut choisir d'écraser ou de retourner une erreur
            # Ici, on ignore le téléversement si le fichier existe déjà.
            continue

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            uploaded_files.append(file.filename)
        except Exception as e:
            # En cas d'erreur, supprimer les fichiers déjà créés dans ce lot pour être atomique
            for uploaded_file in uploaded_files:
                os.remove(os.path.join(KNOWLEDGE_BASE_DIR, uploaded_file))
            raise HTTPException(status_code=500, detail=f"Impossible de sauvegarder le fichier {file.filename}: {e}")
        finally:
            file.file.close()
            
    if not uploaded_files:
        return {"message": "Aucun nouveau fichier à téléverser ou les fichiers existent déjà."}

    return {"message": f"{len(uploaded_files)} fichier(s) téléversé(s) avec succès", "uploaded_files": uploaded_files}


@router.delete("/documents/{filename}")
def delete_document(filename: str):
    """Supprime un document spécifique."""
    try:
        file_path = os.path.join(KNOWLEDGE_BASE_DIR, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Le fichier n'a pas été trouvé.")
        
        os.remove(file_path)
        return {"message": f"Le document '{filename}' a été supprimé avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur du serveur lors de la suppression du fichier: {e}")
