import requests
import time
from datetime import datetime, timedelta
import json

CONFIG_FILE = "config.json"

def load_glpi_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Erreur: Fichier de configuration 'config.json' non trouvé.")
        exit()

config = load_glpi_config()
GLPI_API_URL = config.get("GLPI_API_URL")
GLPI_APP_TOKEN = config.get("GLPI_APP_TOKEN")
GLPI_USER_TOKEN = config.get("GLPI_USER_TOKEN")

def get_session_token():
    url = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
    }
    response = requests.post(url, headers=headers)
    data = response.json()
    print("Réponse initSession GLPI:", data)  # Ajoute cette ligne pour debug
    if isinstance(data, dict):
        return data.get("session_token")
    else:
        return None

def get_open_tickets(session_token):
    url = f"{GLPI_API_URL}/Ticket"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    response = requests.get(url, headers=headers)
    return response.json()

def get_last_update(ticket):
    # GLPI retourne souvent 'date_mod' ou 'date' (création), on prend la dernière modif
    return ticket.get('date_mod') or ticket.get('date')

def add_reminder(session_token, ticket_id):
    url = f"{GLPI_API_URL}/ITILFollowup"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token,
        "Content-Type": "application/json"
    }
    payload = {
        "input": {
            "items_id": ticket_id,
            "itemtype": "Ticket",
            "content": "Relance automatique : ce ticket est en attente de traitement depuis plus de 2h.",
            "is_private": 0
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

def main():
    session_token = get_session_token()
    if not session_token:
        print("Erreur d'authentification GLPI.")
        return
    tickets = get_open_tickets(session_token)
    now = datetime.now()
    threshold = now - timedelta(hours=2)
    for ticket in tickets:
        # Filtrer les tickets ouverts/nouveaux/en attente
        status = ticket.get('status')
        if status not in [1, 2, 3]:  # 1: Nouveau, 2: En cours, 3: En attente
            continue
        last_update_str = get_last_update(ticket)
        if not last_update_str:
            continue
        try:
            last_update = datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%s")
        except Exception:
            try:
                last_update = datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        if last_update < threshold:
            print(f"Relance automatique du ticket {ticket['id']} (dernier update: {last_update})")
            add_reminder(session_token, ticket['id'])

if __name__ == "__main__":
    main()
