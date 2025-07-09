# Base de données: Configuration et initialisation de la connexion à la base de données SQLite.

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL de la base de données SQLite locale
# Le fichier mcp_app.db sera créé dans le même répertoire que le projet.
SQLALCHEMY_DATABASE_URL = "sqlite:///./mcp_app.db"

# Création du moteur SQLAlchemy
# L'argument connect_args est spécifique à SQLite pour autoriser les opérations multithread.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Création d'une classe de session locale
# Chaque instance de SessionLocal sera une session de base de données.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Création d'une classe de base pour les modèles de données
# Les modèles (ex: User) hériteront de cette classe.
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
