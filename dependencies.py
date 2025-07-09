from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

from database import SessionLocal, get_db
from models import User
from config import SECRET_KEY, ALGORITHM

# --- CONFIGURATION DE LA SÉCURITÉ ---

# Contexte pour le hachage des mots de passe (bcrypt est la norme)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Durée de validité du token en minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Indique à FastAPI où trouver le token dans la requête (endpoint de login)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- FONCTIONS UTILITAIRES DE SÉCURITÉ ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si un mot de passe en clair correspond à un mot de passe haché."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    """Hache un mot de passe en utilisant bcrypt."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Crée un nouveau token JWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Par défaut, le token expire après ACCESS_TOKEN_EXPIRE_MINUTES
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- DÉPENDANCES FASTAPI ---

def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> User:
    """Décode le token JWT pour obtenir l'utilisateur actuel."""
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
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Vérifie que l'utilisateur actuel est un administrateur."""
    # Utilise .value pour comparer avec l'énumération du modèle
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="L'opération nécessite des privilèges d'administrateur"
        )
    return current_user
