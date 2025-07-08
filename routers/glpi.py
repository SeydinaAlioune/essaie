from fastapi import APIRouter, Body, Depends, HTTPException
from models.user import User
from routers.auth import get_current_user, require_role
from routers.configuration import load_glpi_config
import requests

router = APIRouter()

# --- Fonctions Utilitaires GLPI ---

def get_session_token():
    """Obtient un session_token GLPI."""
    try:
        config = load_glpi_config()
        url = f"{config['GLPI_API_URL']}/initSession"
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

def get_or_create_glpi_user(session_token, email, name):
    """Récupère ou crée un utilisateur dans GLPI et retourne son ID."""
    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    
    # 1. Chercher l'utilisateur par email
    try:
        search_url = f"{config['GLPI_API_URL']}/User?searchText={email}"
        resp = requests.get(search_url, headers=headers)
        resp.raise_for_status()
        users = resp.json()
        for user in users:
            if (user.get("email", "") or "").strip().lower() == email.strip().lower():
                return user["id"]
    except requests.exceptions.RequestException as e:
        print(f"Avertissement: La recherche d'utilisateur GLPI a échoué: {e}")

    # 2. Si non trouvé, le créer
    try:
        url_create = f"{config['GLPI_API_URL']}/User"
        user_data = {"input": {
            "name": name.lower().replace(" ", "_"), "email": email,
            "firstname": name.split(' ')[0] if ' ' in name else name,
            "realname": name.split(' ')[-1] if ' ' in name else '',
            "entities_id": 0, "profiles_id": 4, "password": "password"
        }}
        create_response = requests.post(url_create, headers=headers, json=user_data)
        create_response.raise_for_status()
        user = create_response.json()
        return user.get("id")
    except requests.exceptions.RequestException as e:
        print(f"Erreur API GLPI (get_or_create_glpi_user): {e}")
        return None

def get_user_ticket_ids(session_token: str, glpi_user_id: int):
    """Récupère les IDs de tous les tickets d'un utilisateur GLPI."""
    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/Ticket_User?users_id={glpi_user_id}&type=1"
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return [tu['tickets_id'] for tu in response.json()]
    except (requests.exceptions.RequestException, KeyError) as e:
        print(f"Impossible de récupérer les tickets de l'utilisateur: {e}")
        return []

# --- Endpoints Publics ---

@router.get("/ping")
def glpi_ping():
    return {"message": "GLPI route opérationnelle !"}

@router.get("/info", dependencies=[Depends(require_role("admin"))])
def glpi_info():
    """Retourne les infos de configuration GLPI (URL seulement)."""
    config = load_glpi_config()
    return {"GLPI_API_URL": config.get("GLPI_API_URL")}

@router.get("/tickets")
def glpi_list_tickets(current_user: User = Depends(get_current_user)):
    """Liste les tickets. Les admins/agents voient tout, les autres leurs propres tickets."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/Ticket?expand_dropdowns=true&range=0-100"
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tickets = response.json()

        if current_user.role in ["admin", "agent support"]:
            return tickets
        else:
            glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
            if not glpi_user_id:
                return []
            user_ticket_ids = get_user_ticket_ids(session_token, glpi_user_id)
            return [t for t in tickets if t['id'] in user_ticket_ids]
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

@router.post("/tickets")
def glpi_create_ticket(title: str = Body(..., embed=True), content: str = Body(..., embed=True), current_user: User = Depends(get_current_user)):
    """Crée un nouveau ticket dans GLPI."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
    if not glpi_user_id:
        raise HTTPException(status_code=404, detail=f"Utilisateur GLPI non trouvé pour {current_user.email}")

    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/Ticket"
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    ticket_data = {"input": {"name": title, "content": content, "_users_id_requester": glpi_user_id}}
    try:
        response = requests.post(url, headers=headers, json=ticket_data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur création ticket GLPI: {e}")

@router.get("/tickets/{ticket_id}")
def glpi_get_ticket(ticket_id: int, current_user: User = Depends(get_current_user)):
    """Récupère les détails d'un ticket spécifique."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/Ticket/{ticket_id}?expand_dropdowns=true"
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        ticket = response.json()

        if current_user.role not in ["admin", "agent support"]:
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
    ticket = glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/Ticket/{ticket_id}"
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

@router.post("/tickets/{ticket_id}/followups")
def glpi_add_followup(ticket_id: int, content: str = Body(..., embed=True), is_private: bool = Body(False, embed=True), current_user: User = Depends(get_current_user)):
    """Ajoute un suivi à un ticket."""
    ticket = glpi_get_ticket(ticket_id, current_user)

    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    url = f"{config['GLPI_API_URL']}/ITILFollowup"
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    payload = {"input": {"itemtype": "Ticket", "items_id": ticket_id, "content": content, "is_private": 1 if is_private else 0}}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur ajout suivi GLPI: {e}")