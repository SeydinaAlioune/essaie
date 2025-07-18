# Base de données: Configuration et initialisation de la connexion à la base de données SQLite.

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL de la base de données. Utilise la variable d'environnement DATABASE_URL si elle existe (fournie par Render),
# sinon, utilise une base de données SQLite locale.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mcp_app.db")

# Création du moteur SQLAlchemy
# L'argument connect_args est spécifique à SQLite pour autoriser les opérations multithread.
# Pour PostgreSQL, nous n'avons pas besoin de l'argument connect_args, qui est spécifique à SQLite.
engine_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_args)

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
