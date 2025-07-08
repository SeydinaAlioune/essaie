#routeur principal pour tout ce qui concerne GLPI
from fastapi import APIRouter, Body, Depends, HTTPException
from models.user import User
from routers.auth import get_current_user
from config import GLPI_API_URL, GLPI_APP_TOKEN, GLPI_USER_TOKEN
import requests
router = APIRouter()

# Fonction utilitaire pour obtenir un session_token GLPI
import requests

def get_session_token():
    url = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
        "GLPI_API_URL":GLPI_API_URL,
        "GLPI_APP_TOKEN": GLPI_APP_TOKEN,
        "GLPI_USER_TOKEN": GLPI_USER_TOKEN
    }

@router.post("/glpi/session")
def glpi_init_session():
    """
    Initialise une session avec l'API GLPI et retourne le session_token ou une erreur.
    """
    url = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
    }
    try:
        response = requests.post(url, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}
## permet de recuperer et de liste les tickets
@router.get("/glpi/tickets")
def glpi_list_tickets(password_glpi: str = Body(None, embed=True), current_user: User = Depends(get_current_user)):
    """
    Récupère la liste des tickets depuis GLPI en utilisant les infos d'authentification connues.
    """
    # 1. Obtenir un session_token
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
    url_tickets = f"{GLPI_API_URL}/Ticket"
    headers_tickets = {
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    try:
        tickets_response = requests.get(url_tickets, headers=headers_tickets)
        tickets = tickets_response.json()
        # Filtrage côté Python selon le rôle
        if current_user.role not in ["admin", "agent support", "support"]:
            from routers.glpi import get_or_create_glpi_user
            glpi_user_id = get_or_create_glpi_user(
    session_token,
    current_user.email,
    current_user.name,
    password_glpi,
    getattr(current_user, "role", None)
)
            if glpi_user_id is None and not password_glpi:
                return {"error": "Veuillez fournir votre mot de passe GLPI pour la création du compte GLPI."}
            print(f"[DEBUG LIST] User MCP: {current_user.email}, User GLPI ID: {glpi_user_id}")
            user_tickets = []
            for t in tickets:
                ticket_id = t.get("id")
                if not ticket_id:
                    continue
                # Récupère les demandeurs du ticket
                url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User?tickets_id={ticket_id}"
                ticket_users_resp = requests.get(url_ticket_users, headers=headers_tickets)
                ticket_users_data = ticket_users_resp.json()
                demandeur_ids = [tu.get("users_id") for tu in ticket_users_data if tu.get("type") == 1]
                print(f"[DEBUG LIST] Ticket {ticket_id} demandeurs: {demandeur_ids}")
                if glpi_user_id and str(glpi_user_id) in [str(uid) for uid in demandeur_ids]:
                    user_tickets.append(t)
            return user_tickets
        return tickets
    except Exception as e:
        return {"error": f"Erreur lors de la récupération des tickets: {e}"}

# Fonction utilitaire pour obtenir ou créer l'utilisateur GLPI correspondant à l'utilisateur MCP
# et retourner son id GLPI

def get_or_create_glpi_user(session_token, email, name, password=None, role=None):
    """
    Cherche un utilisateur GLPI par email. Si non trouvé, le crée avec le mot de passe et le profil correspondant au rôle. Retourne l'id GLPI.
    """
    # 1. Chercher l'utilisateur par email
    url = f"{GLPI_API_URL}/User?searchText={email}"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    try:
        response = requests.get(url, headers=headers)
        users = response.json()
        email_clean = (email or '').strip().lower()
        if isinstance(users, list) and users:
            found = False
            for user in users:
                user_email = (user.get("email", "") or '').strip().lower()
                user_name = (user.get("name", "") or '').strip().lower()
                print(f"[DEBUG USER] Test utilisateur: id={user.get('id')} | email='{user_email}' | name='{user_name}' vs recherché='{email_clean}'")
                if user_email == email_clean or user_name == email_clean:
                    print(f"[DEBUG USER] Utilisateur GLPI trouvé pour {email_clean} (email ou name): {user}")
                    # Utilisateur déjà existant, inutile de demander le mot de passe pour les tickets suivants
                    return user["id"]
            print(f"[DEBUG USER] Aucun utilisateur GLPI avec l'email ou le name exact '{email_clean}' trouvé dans la liste. Users retournés : {users}")
        else:
            print(f"[DEBUG USER] Réponse inattendue lors de la recherche utilisateur GLPI : {users}")
    except Exception as e:
        print(f"[DEBUG USER] Erreur recherche utilisateur : {e}")
    # 2. Si non trouvé, créer l'utilisateur
    # Mapping rôle -> profiles_id GLPI
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
    print("[DEBUG USER] Payload création utilisateur GLPI (corrigé) :", payload)
    resp = requests.post(f"{GLPI_API_URL}/User", headers=headers, json=payload)
    user = resp.json()
    print("[DEBUG USER] Résultat création utilisateur GLPI :", user)
    # Si la création retourne un dict avec 'id', OK
    if isinstance(user, dict) and "id" in user:
        print(f"[DEBUG USER] Utilisateur GLPI créé avec succès pour {email}")
        return user.get("id")
    # Si erreur 'existe déjà', relancer une recherche stricte
    elif isinstance(user, list) and "existe déjà" in str(user).lower():
        print("[DEBUG USER] Erreur création GLPI (existe déjà), relance la recherche GET pour récupérer l'ID...")
        url_list = f"{GLPI_API_URL}/User"
        resp = requests.get(url_list, headers=headers)
        users = resp.json()
        email_clean = (email or '').strip().lower()
        for user in users:
            user_email = (user.get("email", "") or '').strip().lower()
            if user_email == email_clean:
                print("[DEBUG USER] User GLPI retrouvé après erreur (existe déjà) :", user)
                return user["id"]
        print(f"[ERREUR GLPI] Aucun utilisateur GLPI correspondant à l'email ou name '{email_clean}' trouvé après création échouée.")
        raise Exception("Un utilisateur GLPI existe déjà avec cet email ou login, mais il n'est pas visible dans la liste. Veuillez vérifier et nettoyer les utilisateurs dans GLPI (y compris les désactivés ou supprimés).")
    else:
        print("[ERREUR GLPI] Erreur inattendue lors de la création de l'utilisateur GLPI :", user)
        return None

@router.post("/glpi/ticket/create")
def glpi_create_ticket(
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
    password_glpi: str = Body(None, embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Crée un nouveau ticket dans GLPI avec le titre et le contenu donnés.
    Associe le ticket au vrai utilisateur MCP (traçabilité) via users_id_recipient.
    """
    # 1. Obtenir un session_token
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
    glpi_user_id = get_or_create_glpi_user(
        session_token,
        current_user.email,
        current_user.name,
        password_glpi,
        getattr(current_user, "role", None)
    )
    if glpi_user_id is None and not password_glpi:
        return {"error": "Veuillez fournir votre mot de passe GLPI pour la création du compte GLPI."}

    # 3. Créer le ticket avec users_id_recipient pour la traçabilité
    url_create = f"{GLPI_API_URL}/Ticket"
    headers_create = {
        "App-Token": GLPI_APP_TOKEN,
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

    # 2bis. Mise à jour du ticket pour que users_id_recipient soit l'utilisateur GLPI réel
    url_update_ticket = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    payload_update = {
        "input": {
            "users_id_recipient": glpi_user_id
        }
    }
    try:
        resp_update = requests.put(url_update_ticket, headers=headers_create, json=payload_update)
        update_data = resp_update.json()
        print(f"[DEBUG GLPI] Ticket mis à jour (users_id_recipient): {update_data}")
    except Exception as e:
        print(f"[DEBUG GLPI] Exception lors de la mise à jour users_id_recipient: {e}")
        update_data = {"error": str(e)}

    # 3. Retourner les infos du ticket, du demandeur ajouté et de la mise à jour
    return {
        "ticket": ticket_data,
        "ticket_user": ticket_user_data,
        "update_recipient": update_data
    }


@router.put("/glpi/ticket/update/{ticket_id}")
def glpi_update_ticket(
    ticket_id: int,
    title: str = Body(None, embed=True),
    content: str = Body(None, embed=True),
    current_user: User = Depends(get_current_user)#verifie les droits avec get_current_user pourfaire cette action
):
    """
    Met à jour le titre ou le contenu d'un ticket GLPI existant.
    """
    # 1. Obtenir un session_token (même logique que précédemment)
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    # Si le ticket n'existe pas ou erreur
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    # Vérification du droit (fiable via /Ticket_User/)
    url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User/?tickets_id={ticket_id}"
    ticket_users_resp = requests.get(url_ticket_users, headers=headers_get)
    ticket_users = ticket_users_resp.json() if ticket_users_resp.ok else []
    demandeur_ids = [tu.get("users_id") for tu in ticket_users if tu.get("type") == 1]
    # Récupérer l'id GLPI de current_user
    from routers.glpi import get_or_create_glpi_user
    glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
    if current_user.role not in ["admin", "support"] and str(glpi_user_id) not in [str(uid) for uid in demandeur_ids]:
        raise HTTPException(status_code=403, detail="Accès interdit : vous ne pouvez modifier que vos propres tickets")
    # 3. Mise à jour du ticket
    url_update = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_update = {
        "App-Token": GLPI_APP_TOKEN,
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

@router.get("/glpi/tickets/search")
def glpi_search_tickets(keyword: str, current_user: User = Depends(get_current_user)):
    """
    Recherche les tickets dont le titre contient le mot-clé donné.
    """
    # 1. Obtenir un session_token
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
    url_tickets = f"{GLPI_API_URL}/Ticket"
    headers_tickets = {
        "App-Token": GLPI_APP_TOKEN,
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
def glpi_delete_ticket(ticket_id: int, password_glpi: str = Body(None, embed=True), current_user: User = Depends(get_current_user)):
    """
    Supprime un ticket GLPI par son id.
    """
    # 1. Obtenir un session_token
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    # Si le ticket n'existe pas ou erreur
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    # Vérification du droit (robuste)
    allowed = False
    from routers.glpi import get_or_create_glpi_user
    glpi_user_id = get_or_create_glpi_user(
        session_token,
        current_user.email,
        current_user.name,
        password_glpi,
        getattr(current_user, "role", None)
    )
    if glpi_user_id is None and not password_glpi:
        return {"error": "Veuillez fournir votre mot de passe GLPI pour la création du compte GLPI."}
    # Extraction robuste des IDs des demandeurs du ticket
    demandeur_ids = []
    users = ticket_data.get('users', {})
    if isinstance(users, dict):
        # '2' correspond au rôle "demandeur" dans GLPI
        demandeur_ids = users.get('2', [])
        if isinstance(demandeur_ids, dict):
            demandeur_ids = [demandeur_ids.get('id')]
        elif isinstance(demandeur_ids, list):
            demandeur_ids = [u.get('id') if isinstance(u, dict) else u for u in demandeur_ids]
        elif isinstance(demandeur_ids, int):
            demandeur_ids = [demandeur_ids]
    # Fallback si la liste des demandeurs est vide : utiliser users_id_recipient
    if not demandeur_ids:
        recipient_id = ticket_data.get('users_id_recipient')
        if recipient_id:
            demandeur_ids = [recipient_id]
    # DEBUG : log des IDs pour diagnostic
    print(f"[DEBUG DELETE] Vérif droits : glpi_user_id={glpi_user_id} | demandeur_ids={demandeur_ids}")
    demandeur_ids_str = [str(uid) for uid in demandeur_ids if uid is not None]
    if glpi_user_id is not None and str(glpi_user_id) in demandeur_ids_str:
        allowed = True
    if not allowed:
        # Vérification supplémentaire via /Ticket_User/ (sécurité maximale)
        url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User?tickets_id={ticket_id}"
        headers_get = {
            "App-Token": GLPI_APP_TOKEN,
            "Session-Token": session_token
        }
        try:
            resp = requests.get(url_ticket_users, headers=headers_get)
            ticket_users_data = resp.json()
            demandeur_ids_2 = [tu.get("users_id") for tu in ticket_users_data if tu.get("type") == 1]
            print(f"[DEBUG DELETE] Vérif via /Ticket_User/: {demandeur_ids_2}")
            if glpi_user_id is not None and str(glpi_user_id) in [str(uid) for uid in demandeur_ids_2]:
                allowed = True
        except Exception as e:
            print(f"[DEBUG DELETE] Exception lors de la vérif /Ticket_User/: {e}")
        if not allowed:
            print(f"[DEBUG DELETE] REFUS : user GLPI {glpi_user_id} n'est pas dans les demandeurs du ticket {ticket_id}")
            print(f"[DEBUG DELETE] Ticket brut: {ticket_data}")
            raise HTTPException(status_code=403, detail="Accès interdit : vous ne pouvez supprimer que vos propres tickets")
    # 3. Suppression du ticket
    url_delete = f"http://localhost:8080/apirest.php/Ticket/{ticket_id}"
    headers_delete = {
        "App-Token": GLPI_APP_TOKEN,
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
    print(">>> TEST LOG GLPI_REMIND_TICKET <<<")
    """
    Ajoute un suivi (relance) à un ticket GLPI existant.
    Seul le demandeur ou un agent support/admin peut relancer.
    """
    # 1. Obtenir un session_token
    url_session = f"{GLPI_API_URL}/initSession"
    headers = {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}"
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
        "App-Token": GLPI_APP_TOKEN,
        "Session-Token": session_token
    }
    ticket_resp = requests.get(url_ticket, headers=headers_get)
    ticket_data = ticket_resp.json()
    if not isinstance(ticket_data, dict) or ticket_data.get("id") is None:
        raise HTTPException(status_code=404, detail="Ticket introuvable")
    # Vérification du droit (fiable via /Ticket_User/)
    url_ticket_users = f"http://localhost:8080/apirest.php/Ticket_User?tickets_id={ticket_id}"
    ticket_users_resp = requests.get(url_ticket_users, headers=headers_get)
    ticket_users = ticket_users_resp.json() if ticket_users_resp.ok else []
    from routers.glpi import get_or_create_glpi_user
    glpi_user_id = get_or_create_glpi_user(session_token, current_user.email, current_user.name)
    demandeur_ids = [str(tu.get("users_id")) for tu in ticket_users if tu.get("type") == 1]
    print(f"[DEBUG REMIND] --- DIAGNOSTIC ---")
    print(f"[DEBUG REMIND] current_user: email={getattr(current_user, 'email', None)} | id={getattr(current_user, 'id', None)} | role={getattr(current_user, 'role', None)}")
    print(f"[DEBUG REMIND] glpi_user_id: {glpi_user_id}")
    print(f"[DEBUG REMIND] demandeur_ids: {demandeur_ids}")
    print(f"[DEBUG REMIND] ticket_users (brut): {ticket_users}")
    print(f"[DEBUG REMIND] ticket_data (brut): {ticket_data}")
    if not demandeur_ids:
        print(f"[DEBUG REMIND][WARN] Aucun demandeur trouvé pour le ticket {ticket_id} ! Vérifiez la base GLPI.")
    if current_user.role not in ["admin", "support", "agent support"] and str(glpi_user_id) not in demandeur_ids:
        print(f"[DEBUG REMIND] REFUS : user GLPI {glpi_user_id} n'est pas dans les demandeurs du ticket {ticket_id} (demandeurs: {demandeur_ids})")
        raise HTTPException(status_code=403, detail="Accès interdit : vous ne pouvez relancer que vos propres tickets")

    # 3. Ajouter un suivi (relance)
    url_followup = "http://localhost:8080/apirest.php/ITILFollowup"
    headers_followup = {
        "App-Token": GLPI_APP_TOKEN,
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