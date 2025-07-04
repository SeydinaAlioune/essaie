import requests

# Utilise les tokens GLPI du fichier config.py
import config

def remind_ticket(session_token, ticket_id, message=None):
    """
    Ajoute un suivi (reminder) public à un ticket GLPI.
    Par défaut, le message est une relance standard.
    """
    url = "http://localhost:8080/apirest.php/ITILFollowup"
    headers = {
        "App-Token": config.GLPI_APP_TOKEN,
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
