from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

import schemas
from config import SECRET_KEY, ALGORITHM
from database import get_mongo_db

# --- CONFIGURATION SÉCURITÉ ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- FONCTIONS UTILITAIRES ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire_time = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire_time})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- DÉPENDANCES FASTAPI --- 

def get_current_user(token: str = Depends(oauth2_scheme)) -> schemas.User:
    """Décode le token JWT et récupère l'utilisateur depuis MongoDB."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les informations d'identification",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    db = get_mongo_db()
    user_data = db.users.find_one({"email": email})
    
    if user_data is None:
        raise credentials_exception

    # Convertir le document MongoDB en modèle Pydantic
    return schemas.User(
        id=str(user_data.get('_id')),
        name=user_data.get('name'),
        email=user_data.get('email'),
        role=user_data.get('role'),
        status=user_data.get('status'),
        glpi_user_id=user_data.get('glpi_user_id')  # Inclure l'ID GLPI
    )

def get_current_admin_user(current_user: schemas.User = Depends(get_current_user)) -> schemas.User:
    """Vérifie que l'utilisateur actuel est un administrateur."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="L'opération nécessite des privilèges d'administrateur"
        )
    return current_user

def get_current_agent_or_admin_user(current_user: schemas.User = Depends(get_current_user)) -> schemas.User:
    """Vérifie que l'utilisateur actuel est un agent ou un administrateur."""
    allowed_roles = ["admin", "agent_support", "agent_interne"]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="L'opération nécessite des privilèges d'agent ou d'administrateur"
        )
    return current_user

