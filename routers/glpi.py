from fastapi import APIRouter, Body, Depends, HTTPException
from models import User
from dependencies import get_current_user, get_current_admin_user
from routers.configuration import load_glpi_config
import requests

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

def get_user_ticket_ids(session_token: str, glpi_user_id: int) -> list[int]:
    """Récupère les IDs de tous les tickets d'un utilisateur GLPI de manière sécurisée."""
    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    url = url_joiner(config['GLPI_API_URL'], 'Ticket')
    params = {
        'is_deleted': 'false',
        'range': '0-1000', # Augmenter la portée si nécessaire
        'criteria[0][field]': 'users_id_recipient',
        'criteria[0][searchtype]': 'equals',
        'criteria[0][value]': glpi_user_id,
        'forcedisplay[0]': 'id' # Optimisation: ne récupérer que le champ ID
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        tickets = response.json()

        # L'API peut retourner un dictionnaire avec l'ID comme clé, ou une liste.
        if isinstance(tickets, dict):
            return [int(k) for k in tickets.keys()]
        elif isinstance(tickets, list):
            return [ticket['id'] for ticket in tickets]
        return []
    except (requests.exceptions.RequestException, KeyError, TypeError) as e:
        print(f"Impossible de récupérer les tickets de l'utilisateur: {e}")
        return []

# --- Endpoints Publics ---

@router.get("/ping")
def glpi_ping():
    return {"message": "GLPI route opérationnelle !"}

@router.get("/info", dependencies=[Depends(get_current_admin_user)])
def glpi_info(current_user: User = Depends(get_current_admin_user)):
    """Retourne les infos de configuration GLPI (URL seulement). Route protégée pour admin."""
    config = load_glpi_config()
    return {"GLPI_API_URL": config.get("GLPI_API_URL")}

@router.get("/tickets")
def glpi_list_tickets(current_user: User = Depends(get_current_user)):
    """Liste les tickets. Les admins/agents voient tout, les clients ne voient que les leurs."""
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}

    try:
        # Pour les admins et agents, on récupère tous les tickets.
        if current_user.role.value in ["admin", "agent_support", "agent_interne"]:
            # Les admins et les agents peuvent voir tous les tickets.
            url = url_joiner(config['GLPI_API_URL'], 'Ticket')
            params = {'is_deleted': 'false', 'range': '0-1000'}
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

        # Pour les clients, on applique la méthode sécurisée en 2 étapes.
        else:
            # Étape 1: Obtenir l'ID de l'utilisateur dans GLPI.
            glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
            if not glpi_user_id:
                return []  # Pas d'utilisateur, donc pas de tickets.

            # Étape 2: Obtenir la liste des IDs de tickets autorisés pour cet utilisateur.
            user_ticket_ids = get_user_ticket_ids(session_token, glpi_user_id)
            if not user_ticket_ids:
                return []  # Pas de tickets pour cet utilisateur.

            # Étape 3: Récupérer les détails complets UNIQUEMENT pour les tickets autorisés.
            # Nous devons faire un nouvel appel à l'API GLPI pour obtenir les tickets par leurs IDs.
            # C'est cette étape qui garantit la sécurité.
            url = url_joiner(config['GLPI_API_URL'], 'Ticket')
            params = {
                'is_deleted': 'false',
                'range': '0-1000',
                'criteria[0][field]': 'id',
                'criteria[0][searchtype]': 'equals',
                'criteria[0][value]': '|'.join(map(str, user_ticket_ids))
            }
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur GLPI: {e}")

def _create_ticket_internal(title: str, content: str, user: User):
    """Logique interne pour créer un ticket GLPI. Peut être appelée par d'autres parties du backend."""
    session_token = get_session_token()
    if not session_token:
        return {"success": False, "error": "Connexion à GLPI impossible."}

    glpi_user_id = get_or_create_glpi_user(session_token, user.email, user.name, role=user.role)
    if not glpi_user_id:
        return {"success": False, "error": f"Utilisateur GLPI non trouvé pour {user.email}"}

    config = load_glpi_config()
    url = url_joiner(config['GLPI_API_URL'], 'Ticket')
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    ticket_data = {"input": {"name": title, "content": content, "_users_id_requester": glpi_user_id}}
    try:
        response = requests.post(url, headers=headers, json=ticket_data)
        response.raise_for_status()
        return {"success": True, "ticket": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Erreur création ticket GLPI: {e}"}

@router.post("/tickets")
def glpi_create_ticket(title: str = Body(..., embed=True), content: str = Body(..., embed=True), current_user: User = Depends(get_current_user)):
    """Crée un nouveau ticket dans GLPI via la route API."""
    result = _create_ticket_internal(title=title, content=content, user=current_user)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result["ticket"]

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