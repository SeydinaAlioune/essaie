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
