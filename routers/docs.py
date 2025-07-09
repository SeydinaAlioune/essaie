from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

import models
import schemas
from database import get_db
from dependencies import get_current_user, get_current_admin_user

router = APIRouter()

@router.get("/search", summary="Rechercher des documents", response_model=List[schemas.Document])
def search_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    keyword: Optional[str] = Query(None, description="Mot-clé dans le titre ou le contenu"),
    category: Optional[str] = Query(None, description="Filtrer par catégorie"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    query = db.query(models.Document)

    # Filtrer par rôle : l'utilisateur ne voit que les documents autorisés pour son rôle
    query = query.filter(models.Document.roles_allowed.contains([current_user.role.value]))

    if keyword:
        query = query.filter(or_(models.Document.title.ilike(f"%{keyword}%"), models.Document.content.ilike(f"%{keyword}%")))
    
    if category:
        query = query.filter(models.Document.category.ilike(f"%{category}%"))

    documents = query.offset(skip).limit(limit).all()
    return documents

@router.post("/create", summary="Créer un nouveau document", status_code=status.HTTP_201_CREATED, response_model=schemas.Document)
def create_document(
    doc: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    new_doc = models.Document(**doc.dict())
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc

@router.put("/update/{doc_id}", summary="Mettre à jour un document", response_model=schemas.Document)
def update_document(
    doc_id: int,
    doc_update: schemas.DocumentBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    db_doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    update_data = doc_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_doc, key, value)

    db.commit()
    db.refresh(db_doc)
    return db_doc

@router.delete("/{doc_id}", summary="Supprimer un document", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    db_doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    
    db.delete(db_doc)
    db.commit()
    return