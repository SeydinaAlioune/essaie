"""
Script d'insertion d'exemples de documents internes CMS dans MongoDB.
A lancer une seule fois pour peupler la base avec des données réalistes.
"""

from pymongo import MongoClient
from datetime import datetime

# Connexion à MongoDB (adapter l'URL si besoin)
client = MongoClient("mongodb://localhost:27017/")
db = client["mcp_backend"]  # nom de la base
collection = db["documents"]  # nom de la collection

documents = [
    {
        "title": "Procédure de réinitialisation du mot de passe Outlook",
        "content": "Pour réinitialiser votre mot de passe Outlook, rendez-vous sur le portail interne, cliquez sur 'Mot de passe oublié', suivez les instructions et validez via le mail reçu.",
        "category": "IT",
        "tags": ["outlook", "mot de passe", "support"],
        "version": "1.0",
        "date": datetime(2024, 1, 15)
    },
    {
        "title": "Procédure de demande de télétravail",
        "content": "Pour effectuer une demande de télétravail, connectez-vous à l’intranet RH, remplissez le formulaire dédié et soumettez-le à votre manager pour validation.",
        "category": "RH",
        "tags": ["télétravail", "RH", "demande"],
        "version": "2.1",
        "date": datetime(2024, 3, 10)
    },
    {
        "title": "FAQ : Accès au portail Crédit Mutuel",
        "content": "Si vous ne parvenez pas à accéder au portail, vérifiez votre connexion internet et vos identifiants. En cas d’échec, contactez le support technique.",
        "category": "FAQ",
        "tags": ["portail", "accès", "support"],
        "version": "1.2",
        "date": datetime(2024, 2, 5)
    },
    {
        "title": "Guide d’onboarding pour nouveaux collaborateurs",
        "content": "Bienvenue ! Pour commencer, configurez votre poste avec les accès fournis, installez les outils listés dans la check-list et suivez la formation d’accueil.",
        "category": "Onboarding",
        "tags": ["onboarding", "nouveau", "formation"],
        "version": "1.0",
        "date": datetime(2024, 1, 20)
    }
]

result = collection.insert_many(documents)
print(f"{len(result.inserted_ids)} documents insérés dans la collection 'documents' de la base 'mcp_backend'.")
