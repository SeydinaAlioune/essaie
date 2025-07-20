from fastapi import APIRouter, Depends, HTTPException, Body, Response
from pymongo.database import Database
from typing import List
from bson import ObjectId

from dependencies import get_current_admin_user, hash_password
from database import get_mongo_db
import schemas

router = APIRouter()

# Helper pour convertir un document MongoDB en schéma User
def user_helper(user_data) -> schemas.User:
    # Nettoyer les données du rôle avant la validation pour gérer les incohérences
    if user_data.get("role") == "agent support":
        user_data["role"] = "agent_support"

    return schemas.User(
        id=str(user_data["_id"]),
        name=user_data["name"],
        email=user_data["email"],
        role=user_data["role"],
        status=user_data["status"]
    )

@router.get("/secret", summary="Endpoint secret pour admin")
def admin_secret(current_user: schemas.User = Depends(get_current_admin_user)):
    return {"message": f"Bienvenue, admin {current_user.name}! Ceci est une information confidentielle."}

@router.post("/users", summary="Créer un nouvel utilisateur", response_model=schemas.User, status_code=201)
def create_user(
    user: schemas.UserCreate,
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    if db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    
    user_data = user.dict()
    user_data["password"] = hash_password(user.password)
    
    result = db.users.insert_one(user_data)
    new_user = db.users.find_one({"_id": result.inserted_id})
    return user_helper(new_user)

@router.get("/users", summary="Lister tous les utilisateurs", response_model=List[schemas.User])
def list_users(
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    users = []
    for user in db.users.find():
        users.append(user_helper(user))
    return users

@router.get("/users/{user_id}", summary="Obtenir un utilisateur par son ID", response_model=schemas.User)
def get_user(
    user_id: str,
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail=f"Invalid ObjectId: {user_id}")
    db_user = db.users.find_one({"_id": ObjectId(user_id)})
    if not db_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user_helper(db_user)

@router.put("/users/{user_id}", summary="Mettre à jour un utilisateur", response_model=schemas.User)
def update_user(
    user_id: str,
    user_update: schemas.UserUpdate, # Utilise le nouveau schéma
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail=f"Invalid ObjectId: {user_id}")

    # Crée un dictionnaire avec les champs à mettre à jour
    update_data = user_update.dict(exclude_unset=True)

    # Si un nouveau mot de passe est fourni, le hasher et l'ajouter aux données de mise à jour
    if user_update.password:
        update_data["password"] = hash_password(user_update.password)
    else:
        # S'assurer de ne pas effacer le mot de passe existant si non fourni
        update_data.pop("password", None)

    if not update_data:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")

    result = db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    updated_user = db.users.find_one({"_id": ObjectId(user_id)})
    return user_helper(updated_user)

@router.delete("/users/{user_id}", summary="Supprimer un utilisateur", status_code=204)
def delete_user(
    user_id: str,
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail=f"Invalid ObjectId: {user_id}")

    result = db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    return Response(status_code=204)

@router.patch("/users/{user_id}/role", summary="Modifier le rôle d'un utilisateur", response_model=schemas.User)
def update_user_role(
    user_id: str,
    role_update: schemas.UserRoleUpdate,
    db: Database = Depends(get_mongo_db),
    current_admin: schemas.User = Depends(get_current_admin_user)
):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail=f"Invalid ObjectId: {user_id}")

    result = db.users.update_one(
        {"_id": ObjectId(user_id)}, 
        {"$set": {"role": role_update.role}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    updated_user = db.users.find_one({"_id": ObjectId(user_id)})
    return user_helper(updated_user)
