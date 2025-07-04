from typing import Optional
from pydantic import BaseModel, EmailStr

class User(BaseModel):
    id: Optional[str] = None  # MongoDB ObjectId as str
    name: str
    email: EmailStr
    password: str  # hashed
    role: str  # admin, support, agent, client
    status: str  # active, pending, blocked, rejected
