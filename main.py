# main.py: Point d'entrée pour le serveur uvicorn.
# Ce fichier importe l'application créée par l'app factory
# et s'assure que les tables de la base de données sont créées.

from dotenv import load_dotenv

# Charger les variables d'environnement au tout début
load_dotenv()

from database import engine, Base
import models  # Importer les modèles pour qu'ils soient enregistrés par Base
from app_factory import create_app #qui se trouve dans app_factory.py

# Crée toutes les tables dans la base de données (ex: 'users')
# C'est une opération idempotente : elle ne recréera pas les tables si elles existent déjà.
Base.metadata.create_all(bind=engine)

app = create_app()
