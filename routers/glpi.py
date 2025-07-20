from collections import Counter
from fastapi import APIRouter, Body, Depends, HTTPException
from models import User
from dependencies import get_current_user
from routers.configuration import load_config as load_glpi_config
import requests
import logging

router = APIRouter()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def url_joiner(base_url, path):
    """Joins a base URL and a path, handling trailing slashes."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

# --- Fonctions Utilitaires GLPI ---

def get_session_token():
    """Obtient un session_token GLPI."""
    try:
        config = load_glpi_config()
        url = url_joiner(config['GLPI_API_URL'], 'initSession')
        headers = {
            "App-Token": config['GLPI_APP_TOKEN'],
            "Authorization": f"user_token {config['GLPI_USER_TOKEN']}"
        }
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("session_token")
    except (requests.exceptions.RequestException, KeyError) as e:
        logging.error(f"Erreur get_session_token: {e}")
        return None

def get_or_create_glpi_user(session_token, email, name, password=None, role=None):
    """
    Cherche un utilisateur GLPI par email. Si non trouvé, le crée avec le mot de passe et le profil correspondant au rôle. Retourne l'id GLPI.
    """
    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    # 1. Chercher l'utilisateur par email
    url = url_joiner(config['GLPI_API_URL'], f'User?searchText={email}')
    try:
        response = requests.get(url, headers=headers)
        users = response.json()
        email_clean = (email or '').strip().lower()
        if isinstance(users, list) and users:
            for user in users:
                user_email = (user.get("email", "") or '').strip().lower()
                user_name = (user.get("name", "") or '').strip().lower()
                if user_email == email_clean or user_name == email_clean:
                    return user["id"]
    except Exception as e:
        logging.error(f"[DEBUG USER] Erreur recherche utilisateur : {e}")

    # 2. Si non trouvé, créer l'utilisateur
    role_to_profile = {
        "admin": 4,
        "agent_support": 3,
        "client": 2
    }
    profiles_id = role_to_profile.get(role, 2)

    payload = {
        "input": {
            "name": email,
            "realname": name,
            "password": password if password else "TempPass#2025",
            "email": email,
            "profiles_id": profiles_id,
            "entities_id": 0,
            "is_active": 1
        }
    }
    try:
        resp = requests.post(url_joiner(config['GLPI_API_URL'], 'User'), headers=headers, json=payload)
        user = resp.json()
        if isinstance(user, dict) and "id" in user:
            return user.get("id")
        else:
            logging.error(f"Erreur inattendue lors de la création de l'utilisateur GLPI: {user}")
            return None
    except Exception as e:
        logging.error(f"Exception lors de la création de l'utilisateur GLPI: {e}")
        return None

def _create_ticket_internal(title: str, content: str, user: User):
    """Logique interne pour créer un ticket GLPI. Ajoute l'email du demandeur au contenu."""
    session_token = get_session_token()
    if not session_token:
        return {"success": False, "error": "Connexion à GLPI impossible."}

    glpi_user_id = user.glpi_user_id
    if not glpi_user_id:
        return {"success": False, "error": "L'utilisateur n'a pas d'ID GLPI."}

    config = load_glpi_config()
    email_header = f"Email du demandeur: {user.email}\n\n"
    content_with_email = email_header + content

    url = url_joiner(config['GLPI_API_URL'], 'Ticket')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    ticket_data = {"input": {"name": title, "content": content_with_email, "_users_id_requester": glpi_user_id}}

    try:
        response = requests.post(url, headers=headers, json=ticket_data)
        response.raise_for_status()
        ticket_info = response.json()
        return {"success": True, "ticket": ticket_info}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Erreur création ticket GLPI: {e}"}

def _create_ticket_followup_internal(ticket_id: int, content: str, user: User):
    """Logique interne pour créer un suivi de ticket (ITILFollowup) avec préfixe de rôle."""
    session_token = get_session_token()
    if not session_token:
        return {"success": False, "error": "Connexion à GLPI impossible."}

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], 'ITILFollowup')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    is_agent = user.role.value in ["admin", "agent_support"]
    prefix = "AGENT_MSG::" if is_agent else "CLIENT_MSG::"
    content_with_prefix = f"{prefix} {content}"

    followup_data = {
        "input": {
            "itemtype": "Ticket",
            "items_id": ticket_id,
            "content": content_with_prefix,
            "is_private": 0
        }
    }

    try:
        response = requests.post(url, headers=headers, json=followup_data)
        response.raise_for_status()
        followup_info = response.json()
        return {"success": True, "followup": followup_info}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

@router.post("/tickets")
def glpi_create_ticket(title: str = Body(..., embed=True), content: str = Body(..., embed=True), current_user: User = Depends(get_current_user)):
    """Crée un nouveau ticket dans GLPI via la route API."""
    result = _create_ticket_internal(title=title, content=content, user=current_user)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result["ticket"]

@router.get("/tickets")
def glpi_list_tickets(current_user: User = Depends(get_current_user)):
    """Liste les tickets. Les admins/agents voient tout, les clients ne voient que les leurs."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    url = url_joiner(config['GLPI_API_URL'], 'Ticket')
    try:
        params = {
            'is_deleted': 'false',
            'range': '0-1000',
            'expand_dropdowns': 'true',
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        all_tickets = response.json()

        email_header_prefix = "Email du demandeur: "
        for ticket in all_tickets:
            content = ticket.get('content', '')
            if content.startswith(email_header_prefix):
                try:
                    first_line = content.splitlines()[0]
                    extracted_email = first_line[len(email_header_prefix):].strip()
                    ticket['requester_email'] = extracted_email
                except (IndexError, ValueError):
                    ticket['requester_email'] = None
            else:
                ticket['requester_email'] = None

        if current_user.role.value not in ["admin", "agent_support"]:
            user_tickets = [t for t in all_tickets if t.get('requester_email') == current_user.email]
            return user_tickets
        else:
            return all_tickets

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

@router.get("/tickets/{ticket_id}")
def glpi_get_ticket(ticket_id: int, current_user: User = Depends(get_current_user)):
    """Récupère les détails d'un ticket spécifique."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], f'Ticket/{ticket_id}?expand_dropdowns=true')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        ticket = response.json()

        email_header_prefix = "Email du demandeur: "
        content = ticket.get('content', '')
        if content.startswith(email_header_prefix):
            try:
                first_line = content.splitlines()[0]
                extracted_email = first_line[len(email_header_prefix):].strip()
                ticket['requester_email'] = extracted_email
            except (IndexError, ValueError):
                ticket['requester_email'] = None
        else:
            ticket['requester_email'] = None

        if current_user.role.value not in ["admin", "agent_support"]:
            if ticket.get('requester_email') != current_user.email:
                raise HTTPException(status_code=403, detail="Accès non autorisé à ce ticket.")
        
        return ticket
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Ticket introuvable.")
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

@router.get("/tickets/{ticket_id}/followups")
def glpi_get_ticket_followups(ticket_id: int, current_user: User = Depends(get_current_user)):
    """Récupère les suivis pour un ticket. Accessible aux admins, agents, et au client demandeur."""
    glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], f'ITILFollowup?tickets_id={ticket_id}&expand_dropdowns=true&sort=date_mod&order=ASC')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logging.error(f"Erreur HTTP lors de la récupération des suivis: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Erreur GLPI: {e.response.text}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur de connexion GLPI: {e}")

@router.post("/tickets/{ticket_id}/followups")
def glpi_add_followup(ticket_id: int, content: str = Body(..., embed=True), current_user: User = Depends(get_current_user)):
    """Ajoute un suivi à un ticket. Le préfixe est géré par cette fonction."""
    glpi_get_ticket(ticket_id, current_user)

    result = _create_ticket_followup_internal(ticket_id=ticket_id, content=content, user=current_user)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result["followup"]