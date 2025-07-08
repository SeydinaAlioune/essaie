import requests

import json

CONFIG_FILE = "config.json"

def load_glpi_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Erreur: Fichier de configuration 'config.json' non trouvé.")
        return {}

config = load_glpi_config()
GLPI_API_URL = config.get("GLPI_API_URL")
GLPI_APP_TOKEN = config.get("GLPI_APP_TOKEN")

def remind_ticket(session_token, ticket_id, message=None):
    """
    Ajoute un suivi (reminder) public à un ticket GLPI.
    Par défaut, le message est une relance standard.
    """
    if not GLPI_API_URL or not GLPI_APP_TOKEN:
        print("Erreur: Configuration GLPI manquante dans 'config.json'.")
        return None

    url = f"{GLPI_API_URL}/ITILFollowup"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token,
        "Content-Type": "application/json"
    }
    if not message:
        message = "Relance automatique : ce ticket est en attente de traitement."
    payload = {
        "input": {
            "items_id": ticket_id,
            "itemtype": "Ticket",
            "content": message,
            "is_private": 0
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
