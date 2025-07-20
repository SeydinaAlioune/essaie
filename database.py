# Base de données: Configuration et initialisation de la connexion à la base de données SQLite.

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./mcp_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def create_db_and_tables():
    # La magie opère ici : SQLAlchemy crée toutes les tables qui héritent de Base.
    Base.metadata.create_all(bind=engine)

# Dépendance FastAPI pour obtenir une session de base de données
# Cette fonction sera appelée pour chaque requête nécessitant un accès à la BDD.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- MongoDB Configuration ---
from pymongo import MongoClient
from pymongo.database import Database

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "mcp_backend"

# Créer le client une seule fois pour être réutilisé à travers l'application
mongo_client = MongoClient(MONGO_URI)

def get_mongo_db() -> Database:
    """
    Retourne une instance de la base de données MongoDB.
    """
    return mongo_client[DB_NAME]

