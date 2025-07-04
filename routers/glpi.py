from fastapi import APIRouter, Body, Depends, HTTPException
from models.user import User
from routers.auth import get_current_user
import config
import requests
router = APIRouter()

# Fonction utilitaire pour obtenir un session_token GLPI
import requests

def get_session_token():
    url = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url, headers=headers)
        data = response.json()
        if isinstance(data, dict):
            return data.get("session_token")
        return None
    except Exception as e:
        print(f"Erreur get_session_token: {e}")
        return None

##endpoint “/glpi/ping”
@router.get("/glpi/ping")
def glpi_ping():
    """
    Endpoint de test pour vérifier la future connexion avec GLPI.
    Pour l'instant, il retourne juste un message de test.
    """
    return {"message": "GLPI route opérationnelle !"}



@router.get("/glpi/info")
def glpi_info():
    """
    Retourne les infos de configuration GLPI (pour test)
    """
    return {
        "GLPI_API_URL":"http://localhost:8080/apirest.php",
        "GLPI_APP_TOKEN": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "GLPI_USER_TOKEN": "PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }

@router.post("/glpi/session")
def glpi_init_session():
    """
    Initialise une session avec l'API GLPI et retourne le session_token ou une erreur.
    """
    url = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}
## permet de recuperer et de liste les tickets
@router.get("/glpi/tickets")
def glpi_list_tickets(current_user: User = Depends(get_current_user)):
    """
    Récupère la liste des tickets depuis GLPI en utilisant les infos d'authentification connues.
    """
    # 1. Obtenir un session_token
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try: 
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}

    # 2. Utiliser le session_token pour lister les tickets
    url_tickets = "http://localhost:8080/apirest.php/Ticket"
    headers_tickets = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    try:
        tickets_response = requests.get(url_tickets, headers=headers_tickets)
        tickets = tickets_response.json()
        # Filtrage côté Python selon le rôle
        if current_user.role not in ["admin", "agent support"]:
            # On ne retourne que les tickets créés par cet utilisateur (si champ requester_email existe)
            filtered = [t for t in tickets if t.get("requester_email") == current_user.email]
            return filtered
        return tickets
    except Exception as e:
        return {"error": f"Erreur lors de la récupération des tickets: {e}"}

# Fonction utilitaire pour obtenir ou créer l'utilisateur GLPI correspondant à l'utilisateur MCP
# et retourner son id GLPI

def get_or_create_glpi_user(session_token, email, name):
    """
    Cherche un utilisateur GLPI par email. Si non trouvé, le crée avec entité et profil par défaut. Retourne l'id GLPI.
    """
    url_search = f"http://localhost:8080/apirest.php/User?searchText={email}"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    # 1. Recherche utilisateur existant (filtrée côté serveur)
    resp = requests.get(url_search, headers=headers)
    users = resp.json()
    print("Réponse brute GET /User?searchText :", users)
    email_clean = email.strip().lower()
    for user in users:
        user_email = (user.get("email", "") or "").strip().lower()
        user_name = (user.get("name", "") or "").strip().lower()
        if user_email == email_clean:
            print("User GLPI trouvé (filtré email):", user)
            return user["id"]
        # Cas où GLPI stocke l'email dans le champ 'name'
        if user_email == '' and user_name == email_clean:
            print("User GLPI trouvé (filtré name=email):", user)
            return user["id"]
    # Sinon, créer le user dans GLPI avec email MCP pour 'name' ET 'email'
    url_create = "http://localhost:8080/apirest.php/User"
    payload = {
        "input": {
            "name": email,  # On force le champ name à l'email pour garantir le mapping
            "email": email,
            "password": "TempPass#2025",
            "entities_id": 0,
            "profiles_id": 2
        }
    }
    resp = requests.post(url_create, headers=headers, json=payload)
    user = resp.json()
    print("User GLPI créé :", user)
    # Si la création retourne un dict avec 'id', OK
    if isinstance(user, dict) and "id" in user:
        return user.get("id")
    # Si erreur 'existe déjà', relancer une recherche stricte
    elif isinstance(user, list) and "existe déjà" in str(user).lower():
        print("Erreur création GLPI (existe déjà), relance la recherche GET pour récupérer l'ID...")
        url_list = "http://localhost:8080/apirest.php/User"
        resp = requests.get(url_list, headers=headers)
        users = resp.json()
        email_clean = email.strip().lower()
        found = False
        for user in users:
            user_email = (user.get("email", "") or "").strip().lower()
            user_name = (user.get("name", "") or "").strip().lower()
            print(f"[DEBUG GLPI] Test utilisateur: id={user.get('id')} | email='{user_email}' | name='{user_name}' vs email recherché='{email_clean}'")
            if (user_email and user_email == email_clean) or (user_name and user_name == email_clean):
                print("User GLPI retrouvé après erreur :", user)
                found = True
                return user["id"]
        if not found:
            print(f"[ERREUR GLPI] Aucun utilisateur GLPI correspondant à l'email '{email_clean}' trouvé après création échouée.")
        return None
    else:
        print("Erreur création GLPI :", user)
        return None

@router.post("/glpi/ticket/create")
def glpi_create_ticket(
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Crée un nouveau ticket dans GLPI avec le titre et le contenu donnés.
    Associe le ticket au vrai utilisateur MCP (traçabilité) via users_id_recipient.
    """
    # 1. Obtenir un session_token
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}

    # 2. Obtenir ou créer l'utilisateur GLPI correspondant à l'utilisateur MCP
    glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)

    # 3. Créer le ticket avec users_id_recipient pour la traçabilité
    url_create = "http://localhost:8080/apirest.php/Ticket"
    headers_create = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token,
        "Content-Type": "application/json"
    }
    # 1. Création du ticket SANS demandeur (GLPI 10.x)
    payload = {
        "input": {
            "name": title,
            "content": content
        }
    }
    try:
        create_response = requests.post(url_create, headers=headers_create, json=payload)
        ticket_data = create_response.json()
        ticket_id = ticket_data.get("id")
        if not ticket_id:
            return {"error": f"Ticket non créé ou id non retourné : {ticket_data}"}
    except Exception as e:
        return {"error": f"Erreur lors de la création du ticket: {e}"}

    # 2. Ajout du demandeur via /Ticket_User/ (type=1)
    url_ticket_user = "http://localhost:8080/apirest.php/Ticket_User"
    payload_ticket_user = {
        "input": {
            "tickets_id": ticket_id,
            "users_id": glpi_user_id,
            "type": 1  # 1 = Demandeur (requester)
        }
    }
    print(f"[DEBUG GLPI] ticket_id créé: {ticket_id}")
    print(f"[DEBUG GLPI] glpi_user_id utilisé comme demandeur: {glpi_user_id}")
    print(f"[DEBUG GLPI] payload envoyé à /Ticket_User/: {payload_ticket_user}")
    try:
        resp_ticket_user = requests.post(url_ticket_user, headers=headers_create, json=payload_ticket_user)
        ticket_user_data = resp_ticket_user.json()
        print(f"[DEBUG GLPI] Réponse API /Ticket_User/: {ticket_user_data}")
    except Exception as e:
        print(f"[DEBUG GLPI] Exception lors de l'ajout du demandeur: {e}")
        return {"error": f"Erreur lors de l'ajout du demandeur: {e}"}

    # 3. Retourner les infos du ticket et du demandeur ajouté
    return {
        "ticket": ticket_data,
        "ticket_user": ticket_user_data
    }


# --- LOGIQUE INTERNE DE CONSULTATION DE TICKET GLPI ---
def internal_glpi_get_ticket(ticket_id: int, current_user: User):
    """
    Fonction interne pour consulter un ticket GLPI (statut, titre, description, etc.).
    Seul le demandeur ou admin/support peut consulter le ticket.
    """
    session_token = get_session_token()
    if not session_token:
        return {"error": "Impossible d'authentifier GLPI"}
    # Récupérer les infos du ticket
    url_ticket = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    try:
        ticket_resp = requests.get(url_ticket, headers=headers)
        ticket_data = ticket_resp.json()
        if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
            return {"error": "Ticket introuvable"}
        # Vérification permission (demandeur ou admin/support)
        if current_user.role not in ["admin", "support"]:
            glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
            if not glpi_user_id:
                return {"error": "Impossible de retrouver votre utilisateur GLPI"}
            url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User/?tickets_id={ticket_id}"
            headers_ticket_users = headers
            resp_ticket_users = requests.get(url_ticket_users, headers=headers_ticket_users)
            ticket_users = resp_ticket_users.json()
            is_requester = any(
                u.get("users_id") == int(glpi_user_id) and u.get("type") == 1
                for u in ticket_users if isinstance(u, dict)
            )
            if not is_requester:
                return {"error": "Accès interdit : vous ne pouvez consulter que vos propres tickets"}
        # Retourne les infos principales du ticket
        return {
            "id": ticket_data.get("id"),
            "titre": ticket_data.get("name"),
            "statut": ticket_data.get("status"),
            "description": ticket_data.get("content"),
            "date_creation": ticket_data.get("date"),
            "demandeur_id": ticket_data.get("users_id_recipient"),
            "raw": ticket_data
        }
    except Exception as e:
        return {"error": f"Erreur lors de la récupération du ticket : {e}"}

# --- LOGIQUE INTERNE DE MISE À JOUR DE TICKET GLPI ---
def internal_glpi_update_ticket(ticket_id: int, title: str, content: str, current_user: User):
    """
    Fonction interne pour mettre à jour un ticket GLPI. Réutilisable par le route handler et le chatbot.
    """
    # 1. Obtenir un session_token (même logique que précédemment)
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}
    # 2. Vérification droit : seul admin/support ou créateur du ticket
    url_ticket = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_get = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        return {"error": "Ticket introuvable"}
    # Vérification robuste : seul admin/support ou demandeur GLPI peut modifier
    if current_user.role not in ["admin", "support"]:
        # 1. Récupérer l'id GLPI du current_user
        glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
        if not glpi_user_id:
            return {"error": "Impossible de retrouver votre utilisateur GLPI"}
        # 2. Récupérer les utilisateurs liés au ticket
        url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User/?tickets_id={ticket_id}"
        headers_ticket_users = {
            "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
            "Session-Token": session_token
        }
        resp_ticket_users = requests.get(url_ticket_users, headers=headers_ticket_users)
        ticket_users = resp_ticket_users.json()
        # 3. Vérifier si current_user est demandeur (type: 1)
        is_requester = any(
            u.get("users_id") == int(glpi_user_id) and u.get("type") == 1
            for u in ticket_users if isinstance(u, dict)
        )
        if not is_requester:
            return {"error": "Accès interdit : vous ne pouvez modifier que vos propres tickets"}
    # 3. Mise à jour du ticket
    url_update = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_update = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token,
        "Content-Type": "application/json"
    }
    payload = {"input": {}}
    if title:
        payload["input"]["name"] = title
    if content:
        payload["input"]["content"] = content
    try:
        update_response = requests.put(url_update, headers=headers_update, json=payload)
        return update_response.json()
    except Exception as e:
        return {"error": f"Erreur lors de la mise à jour du ticket: {e}"}

# --- ROUTE HANDLER GLPI UPDATE ---
@router.put("/glpi/ticket/update/{ticket_id}")
def glpi_update_ticket(
    ticket_id: int,
    title: str = Body(None, embed=True),
    content: str = Body(None, embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Route FastAPI : met à jour le titre ou le contenu d'un ticket GLPI existant.
    """
    return internal_glpi_update_ticket(ticket_id, title, content, current_user)

@router.get("/glpi/tickets/search")
def glpi_search_tickets(keyword: str, current_user: User = Depends(get_current_user)):
    """
    Recherche les tickets dont le titre contient le mot-clé donné.
    """
    # 1. Obtenir un session_token
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}

    # 2. Recherche des tickets
    url_tickets = "http://localhost:8080/apirest.php/Ticket"
    headers_tickets = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    try:
        tickets_response = requests.get(url_tickets, headers=headers_tickets)
        tickets = tickets_response.json()
        # Filtrer côté Python (GLPI ne gère pas la recherche fulltext par défaut)
        # Filtrage selon le rôle
        if current_user.role in ["admin", "support"]:
            filtered = [t for t in tickets if keyword.lower() in t.get("name", "").lower()]
            return filtered
        else:
            filtered = [t for t in tickets if keyword.lower() in t.get("name", "").lower() and t.get("requester_email") == current_user.email]
            return filtered
    except Exception as e:
        return {"error": f"Erreur lors de la recherche des tickets: {e}"}
        

@router.delete("/glpi/ticket/delete/{ticket_id}")
def glpi_delete_ticket(ticket_id: int, current_user: User = Depends(get_current_user)):
    """
    Supprime un ticket GLPI par son id.
    """
    # 1. Obtenir un session_token
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}

    # 2. Vérification droit : seul admin/support ou créateur du ticket
    url_ticket = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_get = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    # Si le ticket n'existe pas ou erreur
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    # Vérification du droit
    if current_user.role not in ["admin", "support"] and ticket_data.get("requester_email") != current_user.email:
        raise HTTPException(status_code=403, detail="Accès interdit : vous ne pouvez supprimer que vos propres tickets")
    # 3. Suppression du ticket
    url_delete = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_delete = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    try:
        delete_response = requests.delete(url_delete, headers=headers_delete)
        return delete_response.json()
    except Exception as e:
        return {"error": f"Erreur lors de la suppression du ticket: {e}"}

@router.post("/glpi/ticket/remind/{ticket_id}")
def glpi_remind_ticket(
    ticket_id: int,
    message: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Ajoute un suivi (relance) à un ticket GLPI existant.
    Seul le demandeur ou un agent support/admin peut relancer.
    """
    # 1. Obtenir un session_token
    url_session = "http://localhost:8080/apirest.php/initSession"
    headers = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Authorization": "user_token PIaHf4AUlNpEGJD44shfALJG3txpRNFoHKjYs560"
    }
    try:
        response = requests.post(url_session, headers=headers)
        data = response.json()
        if isinstance(data, list):
            return {"error": f"Réponse inattendue de GLPI (type liste): {data}"}
        session_token = data.get("session_token")
        if not session_token:
            return {"error": f"Impossible d'obtenir un session_token. Réponse: {data}"}
    except Exception as e:
        return {"error": f"Erreur lors de l'initSession: {e}"}

    # 2. Vérifier que l'utilisateur a le droit de relancer (demandeur ou support/admin)
    url_ticket = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_get = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    if current_user.role not in ["admin", "agent support"] and ticket_data.get("requester_email") != current_user.email:
        raise HTTPException(status_code=403, detail="Accès interdit : vous ne pouvez relancer que vos propres tickets")

    # 3. Ajouter un suivi (relance)
    url_followup = "http://localhost:8080/apirest.php/ITILFollowup"
    headers_followup = {
        "App-Token": "mStHpZsjGQuq7TAmjAD70ZrqacqMXgmRTLRpdMQO",
        "Session-Token": session_token,
        "Content-Type": "application/json"
    }
    payload = {
        "input": {
            "items_id": ticket_id,
            "itemtype": "Ticket",
            "content": message,
            "is_private": 0  # 0 = public, 1 = privé
        }
    }
    try:
        followup_resp = requests.post(url_followup, headers=headers_followup, json=payload)
        return followup_resp.json()
    except Exception as e:
        return {"error": f"Erreur lors de la relance du ticket: {e}"}