from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
from datetime import datetime

# Enum pour les rôles et statuts, miroir de models.py
class UserRole(str, Enum):
    admin = "admin"
    support = "support"
    agent = "agent"
    client = "client"

class UserStatus(str, Enum):
    active = "active"
    pending = "pending"
    blocked = "blocked"
    rejected = "rejected"

# Schéma de base pour l'utilisateur
class UserBase(BaseModel):
    name: str
    email: str
    role: UserRole
    status: UserStatus

# Schéma pour la création d'utilisateur (inclut le mot de passe)
class UserCreate(UserBase):
    password: str

# Schéma pour la lecture d'un utilisateur (réponse API)
class User(UserBase):
    id: int

    class Config:
        from_attributes = True

# --- Schémas pour les Documents ---

class DocumentBase(BaseModel):
    title: str
    content: str
    category: str
    roles_allowed: List[str]

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    date_creation: datetime

    class Config:
        from_attributes = True

# --- Schémas pour l'Authentification ---

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
