from fastapi import APIRouter, HTTPException, Depends, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional
from pymongo.errors import PyMongoError
from db import get_database
from auth import verify_password, hash_password, create_access_token, decode_access_token
from models.user import User
from jose import JWTError
from datetime import timedelta

router = APIRouter()
db = get_database()
users_collection = db["users"]

import random
import string
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# Configuration email (à adapter)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "diaoseydina62@gmail.com" 
SMTP_PASSWORD = "slji neaj eyre mqsk"  # Mot de passe d'application Gmail
RESET_CODE_EXP_MINUTES = 15


def send_reset_email(to_email, code):
    subject = "Code de réinitialisation de mot de passe"
    body = f"Bonjour,\n\nVotre code de réinitialisation est : {code}\nIl est valable 15 minutes.\n\nSi vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
    except Exception as e:
        print(f"Erreur envoi mail: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'envoi de l'email de réinitialisation")

@router.post("/request-password-reset")
def request_password_reset(email: str = Body(...)):
    """
    Génère un code de réinitialisation pour l'utilisateur et l'envoie par email.
    """
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    code = ''.join(random.choices(string.digits, k=6))
    exp = datetime.utcnow() + timedelta(minutes=RESET_CODE_EXP_MINUTES)
    users_collection.update_one({"email": email}, {"$set": {"reset_code": code, "reset_code_exp": exp}})
    send_reset_email(email, code)
    return {"message": "Un code de réinitialisation a été envoyé par email."}

@router.post("/reset-password")
def reset_password(
    email: str = Body(...),
    reset_code: str = Body(...),
    new_password: str = Body(...)
):
    """
    Permet de réinitialiser le mot de passe avec le code reçu (valide 15 min).
    """
    user = users_collection.find_one({"email": email})
    if not user or user.get("reset_code") != reset_code:
        raise HTTPException(status_code=400, detail="Code de réinitialisation invalide")
    exp = user.get("reset_code_exp")
    if not exp or datetime.utcnow() > exp:
        raise HTTPException(status_code=400, detail="Code expiré, veuillez refaire une demande")
    users_collection.update_one({"email": email}, {"$set": {"password": hash_password(new_password)}, "$unset": {"reset_code": "", "reset_code_exp": ""}})
    return {"message": "Mot de passe réinitialisé avec succès."}

@router.post("/register")
def register(
    name: str = Body(...),
    email: str = Body(...),
    password: str = Body(...),
    role: str = Body(...)
):
    """
    Permet à un utilisateur de s'inscrire lui-même (auto-inscription).
    Rôles acceptés : client, agent, support.
    Le compte est créé en status 'pending'.
    """
    allowed_roles = ["client", "agent support"]
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Rôle non autorisé pour l'inscription")
    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    hashed_pw = hash_password(password)
    user_doc = {
        "name": name,
        "email": email,
        "password": hashed_pw,
        "role": role,
        "status": "pending"
    }
    try:
        users_collection.insert_one(user_doc)
        return {"message": "Compte créé avec succès. En attente de validation par un administrateur."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création du compte: {e}")


# Pour extraire le token envoyé par le client
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Dépendance pour obtenir l'utilisateur courant à partir du token
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les identifiants",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
    user_data = users_collection.find_one({"email": email})
    if not user_data:
        raise credentials_exception
    return User(**user_data)

# Modifier son propre profil
@router.patch("/update-me")
def update_me(
    name: str = Body(None),
    password: str = Body(None),
    current_user: User = Depends(get_current_user)
):
    update_fields = {}
    if name:
        update_fields["name"] = name
    if password:
        update_fields["password"] = hash_password(password)
    if not update_fields:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
    db = get_database()
    users_collection = db["users"]
    result = users_collection.update_one({"email": current_user.email}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user = users_collection.find_one({"email": current_user.email}, {"password": 0})
    if user and "_id" in user:
        user["_id"] = str(user["_id"])
    return {"message": "Profil mis à jour !", "user": user}

# Endpoint de login
@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_data = users_collection.find_one({"email": form_data.username})
    if not user_data:
        raise HTTPException(status_code=400, detail="Utilisateur non trouvé")
    if not verify_password(form_data.password, user_data["password"]):
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")
    if user_data.get("status") != "active":
        raise HTTPException(status_code=403, detail="Compte inactif ou bloqué")
    access_token = create_access_token(
        data={"sub": user_data["email"], "role": user_data["role"]},
        expires_delta=timedelta(minutes=60)
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Dépendance pour obtenir l'utilisateur courant à partir du token
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les identifiants",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
    user_data = users_collection.find_one({"email": email})
    if not user_data:
        raise credentials_exception
    return User(**user_data)

# Endpoint pour obtenir les infos du user connecté
@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# Dépendance pour exiger un rôle spécifique

def require_role(role: str):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != role:
            raise HTTPException(status_code=403, detail="Permission refusée")
        return current_user
    return role_checker
