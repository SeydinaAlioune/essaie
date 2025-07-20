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
from routers.glpi import get_session_token, get_or_create_glpi_user

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

    # Récupérer et stocker l'ID utilisateur GLPI s'il n'existe pas
    glpi_user_id = user_data.get("glpi_user_id")
    if not glpi_user_id:
        session_token = get_session_token()
        if session_token:
            glpi_user_id = get_or_create_glpi_user(
                session_token=session_token,
                email=user_data["email"],
                name=user_data.get("name"),
                role=user_data.get("role")
            )
            if glpi_user_id:
                users_collection.update_one(
                    {"_id": user_data["_id"]},
                    {"$set": {"glpi_user_id": glpi_user_id}}
                )
                user_data["glpi_user_id"] = glpi_user_id  # Mettre à jour la variable locale

    # L'objet utilisateur doit correspondre au schéma `schemas.User`
    user_for_response = schemas.User(
        id=str(user_data.get('_id')),
        name=user_data.get('name'),
        email=user_data.get('email'),
        role=user_data.get('role'),
        status=user_data.get('status'),
        glpi_user_id=glpi_user_id
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_data["email"], "name": user_data.get("name"), "role": user_data.get("role"), "glpi_user_id": glpi_user_id},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer", "user": user_for_response}


@router.get("/me", response_model=schemas.User)
def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    """
    Retourne les informations de l'utilisateur actuellement connecté.
    """
    return current_user
