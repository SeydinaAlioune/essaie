from fastapi import APIRouter, Body, Depends, HTTPException
from models import User
from dependencies import get_current_user, get_current_admin_user
from routers.configuration import load_glpi_config
import requests
import logging

router = APIRouter()

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
        print(f"Erreur get_session_token: {e}")
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
        print(f"[DEBUG USER] Erreur recherche utilisateur : {e}")

    # 2. Si non trouvé, créer l'utilisateur
    role_to_profile = {
        "admin": 4,         # exemple: 4 = admin dans GLPI
        "support": 3,       # exemple: 3 = support
        "agent support": 3, # idem support
        "client": 2         # exemple: 2 = self-service
    }
    profiles_id = role_to_profile.get(role, 2)  # défaut: self-service

    payload = {
        "input": {
            "name": email,  # Pour garantir la recherche future
            "realname": name,  # Affichage humain
            "password": password if password else "TempPass#2025",
            "email": email,  # Toujours renseigner l'email
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
        elif isinstance(user, list) and "existe déjà" in str(user).lower():
            print("[DEBUG USER] Erreur création GLPI (existe déjà), relance la recherche GET pour récupérer l'ID...")
            resp = requests.get(url_joiner(config['GLPI_API_URL'], 'User'), headers=headers)
            users = resp.json()
            email_clean = (email or '').strip().lower()
            for user_item in users:
                user_email = (user_item.get("email", "") or '').strip().lower()
                if user_email == email_clean:
                    return user_item["id"]
            raise Exception("Un utilisateur GLPI existe déjà avec cet email, mais il n'est pas visible.")
        else:
            print(f"Erreur inattendue lors de la création de l'utilisateur GLPI: {user}")
            return None
    except Exception as e:
        print(f"Exception lors de la création de l'utilisateur GLPI: {e}")
        return None

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
        # Fusion des paramètres pour inclure `forcedisplay`
        params = {
            'is_deleted': 'false',
            'range': '0-1000',
            'expand_dropdowns': 'true',
            'forcedisplay[0]': '_users_id_requester'
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        all_tickets = response.json()

        # Si l'utilisateur n'est pas un admin ou un agent, filtrer les tickets.
        if current_user.role.value not in ["admin", "agent_support", "agent_interne"]:
            # CONTOURNEMENT: Filtre les tickets en lisant l'email dans le contenu
            user_tickets = []
            email_header_prefix = "Email du demandeur: "
            for ticket in all_tickets:
                content = ticket.get('content', '')
                if content.startswith(email_header_prefix):
                    try:
                        # Extrait la première ligne et l'email
                        first_line = content.splitlines()[0]
                        extracted_email = first_line[len(email_header_prefix):].strip()
                        if extracted_email == current_user.email:
                            user_tickets.append(ticket)
                    except (IndexError, ValueError):
                        # Ignore les tickets où l'extraction échoue
                        continue
            return user_tickets
        else:
            # Les admins et agents voient tous les tickets
            return all_tickets

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _create_ticket_internal(title: str, content: str, user: User):
    """Logique interne pour créer un ticket GLPI. Ajoute l'email du demandeur au contenu."""
    session_token = get_session_token()
    if not session_token:
        return {"success": False, "error": "Connexion à GLPI impossible."}

    glpi_user_id = get_or_create_glpi_user(session_token, user.email, user.name, role=user.role)
    if not glpi_user_id:
        return {"success": False, "error": f"Utilisateur GLPI non trouvé pour {user.email}"}

    config = load_glpi_config()

    # CONTOURNEMENT: Ajoute l'email au contenu car GLPI ignore _users_id_requester
    logging.info(f"Tentative de création de ticket pour l'utilisateur {user.email} avec le titre: '{title}'")
    email_header = f"Email du demandeur: {user.email}\n\n"
    content_with_email = email_header + content

    url = url_joiner(config['GLPI_API_URL'], 'Ticket')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    ticket_data = {"input": {"name": title, "content": content_with_email, "_users_id_requester": glpi_user_id}}
    
    try:
        response = requests.post(url, headers=headers, json=ticket_data)
        response.raise_for_status()
        ticket_info = response.json()
        logging.info(f"Ticket créé avec succès dans GLPI avec l'ID: {ticket_info.get('id')}")
        return {"success": True, "ticket": ticket_info}
    except requests.exceptions.RequestException as e:
        error_message = f"Erreur création ticket GLPI: {e}"
        logging.error(f"Échec de la création du ticket pour {user.email}. Erreur: {error_message}")
        return {"success": False, "error": error_message}

def _create_ticket_followup_internal(ticket_id: int, content: str, user: User):
    """Logique interne pour créer un suivi de ticket (ITILFollowup) avec préfixe de rôle."""
    session_token = get_session_token()
    if not session_token:
        return {"success": False, "error": "Connexion à GLPI impossible."}

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], 'ITILFollowup')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    is_agent = user.role.value in ["admin", "agent_support", "agent_interne"]
    prefix = "AGENT_MSG::" if is_agent else "CLIENT_MSG::"
    content_with_prefix = f"{prefix}{content}"

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
        logging.info(f"Suivi ajouté avec succès au ticket {ticket_id}")
        return {"success": True, "followup": followup_info}
    except requests.exceptions.RequestException as e:
        error_text = e.response.text if e.response else 'No response'
        error_message = f"Erreur création suivi GLPI: {e} - {error_text}"
        logging.error(f"Échec de l'ajout du suivi au ticket {ticket_id}. Erreur: {error_message}")
        return {"success": False, "error": error_message}


@router.post("/tickets")
def glpi_create_ticket(title: str = Body(..., embed=True), content: str = Body(..., embed=True), current_user: User = Depends(get_current_user)):
    """Crée un nouveau ticket dans GLPI via la route API."""
    result = _create_ticket_internal(title=title, content=content, user=current_user)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result["ticket"]


@router.get("/tickets/{ticket_id}/followups")
def glpi_get_ticket_followups(ticket_id: int, current_user: User = Depends(get_current_user)):
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=500, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], f'Ticket/{ticket_id}/ITILFollowup')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        followups = response.json()

        processed_followups = []
        for f in followups:
            content = f.get('content', '')
            if content.startswith('CLIENT_MSG::'):
                f['author_role'] = 'client'
                f['content'] = content[len('CLIENT_MSG::'):]
            elif content.startswith('AGENT_MSG::'):
                f['author_role'] = 'agent'
                f['content'] = content[len('AGENT_MSG::'):]
            else:
                # Pour les anciens messages ou ceux sans préfixe, on se base sur users_id
                f['author_role'] = 'client' if f.get('users_id') == 0 else 'agent'
            processed_followups.append(f)
        return processed_followups
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI lors de la récupération des suivis: {e}")

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

        if current_user.role.value not in ["admin", "agent support"]:
            glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
            user_ticket_ids = get_user_ticket_ids(session_token, glpi_user_id)
            if ticket_id not in user_ticket_ids:
                raise HTTPException(status_code=403, detail="Accès non autorisé à ce ticket.")
        return ticket
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Ticket introuvable.")
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

@router.put("/tickets/{ticket_id}")
def glpi_update_ticket(ticket_id: int, title: str = Body(None), content: str = Body(None), current_user: User = Depends(get_current_user)):
    """Met à jour le titre ou le contenu d'un ticket."""
    # Première, on vérifie si l'utilisateur a le droit de voir le ticket
    glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], f'Ticket/{ticket_id}')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    payload = {"input": {}}
    if title: payload["input"]["name"] = title
    if content: payload["input"]["content"] = content
    if not payload["input"]: raise HTTPException(status_code=400, detail="Rien à mettre à jour.")

    try:
        response = requests.put(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur mise à jour ticket GLPI: {e}")

@router.get("/tickets/{ticket_id}/followups")
def glpi_get_ticket_followups(ticket_id: int, current_user: User = Depends(get_current_user)):
    """Récupère tous les suivis (messages) d'un ticket."""
    # On vérifie d'abord que l'utilisateur a le droit de voir le ticket principal
    glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    # Note: L'API GLPI standard filtre par `tickets_id` pour l'objet ITILFollowup
    url = url_joiner(config['GLPI_API_URL'], f'ITILFollowup?tickets_id={ticket_id}&expand_dropdowns=true&sort=date_mod&order=ASC')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP lors de la récupération des suivis: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Erreur GLPI: {e.response.text}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur de connexion GLPI: {e}")

@router.post("/tickets/{ticket_id}/followups")
def glpi_add_followup(ticket_id: int, content: str = Body(..., embed=True), is_private: bool = Body(False, embed=True), current_user: User = Depends(get_current_user)):
    """Ajoute un suivi à un ticket."""
    # On vérifie que l'utilisateur a le droit de voir (et donc de commenter) le ticket
    glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], 'ITILFollowup')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    payload = {"input": {"itemtype": "Ticket", "items_id": ticket_id, "content": content, "is_private": 1 if is_private else 0}}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP lors de l'ajout du suivi: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Erreur GLPI: {e.response.text}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur de connexion GLPI: {e}")