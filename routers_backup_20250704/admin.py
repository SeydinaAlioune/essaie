from fastapi import APIRouter, Depends, HTTPException, Body
from routers.auth import require_role
from db import get_database
from auth import hash_password

router = APIRouter()
db = get_database()
users_collection = db["users"]

@router.get("/admin/secret")
def admin_secret(current_user=Depends(require_role("admin"))):
    return {"message": f"Bienvenue, admin {current_user.name}! Ceci est une information confidentielle."}

@router.post("/admin/create-user")
def create_user(
    name: str = Body(...),
    email: str = Body(...),
    password: str = Body(...),
    role: str = Body(..., description="admin, support, agent, client"),
    status: str = Body("active", description="active, pending, blocked, rejected"),
    current_user=Depends(require_role("admin"))
):
    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    if role not in ["admin", "agent support", "client"]:
        raise HTTPException(status_code=400, detail="Rôle invalide")
    if status not in ["active", "pending", "blocked", "rejected"]:
        raise HTTPException(status_code=400, detail="Statut invalide")
    user_doc = {
        "name": name,
        "email": email,
        "password": hash_password(password),
        "role": role,
        "status": status
    }
    users_collection.insert_one(user_doc)
    return {"message": "Utilisateur créé !", "user": {"name": name, "email": email, "role": role, "status": status}}

@router.patch("/admin/validate-user/{email}")
def validate_user(email: str, current_user=Depends(require_role("admin"))):
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    if user.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Le compte n'est pas en attente de validation")
    users_collection.update_one({"email": email}, {"$set": {"status": "active"}})
    return {"message": f"Le compte {email} a été validé et activé."}

@router.patch("/admin/update-user/{email}")
def update_user(
    email: str,
    name: str = Body(None),
    role: str = Body(None),
    status: str = Body(None),
    current_user=Depends(require_role("admin"))
):
    update_fields = {}
    if name:
        update_fields["name"] = name
    if role:
        if role not in ["admin", "agent support", "client"]:
            raise HTTPException(status_code=400, detail="Rôle invalide")
        update_fields["role"] = role
    if status:
        if status not in ["active", "pending", "blocked", "rejected"]:
            raise HTTPException(status_code=400, detail="Statut invalide")
        update_fields["status"] = status
    if not update_fields:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
    result = users_collection.update_one({"email": email}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user = users_collection.find_one({"email": email}, {"password": 0})
    return {"message": "Utilisateur modifié !", "user": user}

@router.delete("/admin/delete-user/{email}")
def delete_user(email: str, current_user=Depends(require_role("admin"))):
    result = users_collection.delete_one({"email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"message": f"Utilisateur {email} supprimé !"}

@router.get("/admin/users")
def list_users(current_user=Depends(require_role("admin"))):
    users = list(users_collection.find({}, {"password": 0}))
    return {"users": users}

@router.get("/admin/user/{email}")
def get_user(email: str, current_user=Depends(require_role("admin"))):
    user = users_collection.find_one({"email": email}, {"password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"user": user}
