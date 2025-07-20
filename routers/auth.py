from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

import schemas
from dependencies import (
    get_current_user,
    verify_password,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import get_mongo_db

router = APIRouter()

@router.post("/login", response_model=schemas.TokenWithUser)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Connecte l'utilisateur via MongoDB et retourne un token JWT.
    """
    db = get_mongo_db()
    users_collection = db["users"]
    
    user_data = users_collection.find_one({"email": form_data.username})

    # Vérification robuste pour éviter les crashs si le document utilisateur est malformé
    if not user_data or not user_data.get("password") or not verify_password(form_data.password, user_data["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_data.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Votre compte est inactif (statut: {user_data.get('status')}). Veuillez contacter un administrateur."
        )

    # L'objet utilisateur doit correspondre au schéma `schemas.User`
    user_for_response = schemas.User(
        id=str(user_data.get('_id')),
        name=user_data.get('name'),
        email=user_data.get('email'),
        role=user_data.get('role'),
        status=user_data.get('status')
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_data["email"], "name": user_data.get("name"), "role": user_data.get("role")},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer", "user": user_for_response}


@router.get("/me", response_model=schemas.User)
def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    """
    Retourne les informations de l'utilisateur actuellement connecté.
    """
    return current_user
