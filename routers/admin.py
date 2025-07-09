from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List

from dependencies import get_current_admin_user, hash_password
from database import get_db
import models
import schemas

router = APIRouter()

@router.get("/secret", summary="Endpoint secret pour admin")
def admin_secret(current_user: models.User = Depends(get_current_admin_user)):
    return {"message": f"Bienvenue, admin {current_user.name}! Ceci est une information confidentielle."}

@router.post("/users", summary="Créer un nouvel utilisateur", response_model=schemas.User, status_code=201)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    
    hashed_pwd = hash_password(user.password)
    new_user = models.User(**user.dict(exclude={'password'}), hashed_password=hashed_pwd)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.patch("/users/{user_id}/status", summary="Modifier le statut d'un utilisateur", response_model=schemas.User)
def update_user_status(
    user_id: int,
    status: schemas.UserStatus = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    db_user.status = status
    db.commit()
    db.refresh(db_user)
    return db_user

@router.put("/users/{user_id}", summary="Mettre à jour un utilisateur", response_model=schemas.User)
def update_user(
    user_id: int,
    user: schemas.UserBase,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    update_data = user.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}", summary="Supprimer un utilisateur", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    db.delete(db_user)
    db.commit()
    return

@router.patch("/users/{user_id}/role", summary="Modifier le rôle d'un utilisateur", response_model=schemas.User)
def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # TODO: Ajouter une validation pour s'assurer que le rôle est valide
    db_user.role = role_update.role
    db.commit()
    db.refresh(db_user)
    return db_user

@router.get("/users", summary="Lister tous les utilisateurs", response_model=List[schemas.User])
def list_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    return db.query(models.User).all()

@router.get("/users/{user_id}", summary="Obtenir un utilisateur par son ID", response_model=schemas.User)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin_user)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return db_user
