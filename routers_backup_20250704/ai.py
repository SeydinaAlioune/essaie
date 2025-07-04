import re
from fastapi import APIRouter, Depends, Body
from routers.auth import get_current_user
# Import explicite de get_session_token pour éviter UnboundLocalError
# Import explicite de toutes les fonctions GLPI nécessaires
from routers.glpi import glpi_create_ticket, get_session_token, get_or_create_glpi_user, glpi_delete_ticket, glpi_update_ticket, glpi_list_tickets
from search_vector_llm import search_vector, build_prompt, call_ollama
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from glpi_remind import remind_ticket

# Fonction utilitaire pour convertir tous les ObjectId en str dans les retours MongoDB
# À utiliser systématiquement avant tout return d'un document MongoDB dans FastAPI
def mongo_to_json(doc):
    if isinstance(doc, list):
        return [mongo_to_json(item) for item in doc]
    if isinstance(doc, dict):
        return {k: mongo_to_json(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc

router = APIRouter()

# Connexion MongoDB pour la traçabilité (adapte selon ta config)
mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["mcp_backend"]
logs_collection = db["chatbot_logs"]

@router.post("/chatbot/ask")
def ask_chatbot(
    question: str = Body(..., embed=True),
    password_glpi: str = Body(None, embed=True),
    current_user=Depends(get_current_user)
):
    """
    Endpoint principal pour dialoguer avec le chatbot et router vers GLPI.
    - question: texte posé à l'IA
    - password_glpi: mot de passe GLPI (optionnel, requis si création de compte GLPI)
    Exemple body:
    {
      "question": "créer un ticket pour moi",
      "password_glpi": "monMotDePasseGLPI"
    }
    """
    import os
    user_id = getattr(current_user, "id", None) or getattr(current_user, "_id", None) or getattr(current_user, "email", None)
    action_type = "faq"
    result = None

    # 1. Détection d'intention via LLM
    # Charger le prompt d'intention
    with open(os.path.join(os.path.dirname(__file__), '../intent_llm_prompt.md'), encoding='utf-8') as f:
        intent_prompt = f.read().replace('{question}', question)
    intent = call_ollama(intent_prompt)

    # Initialisation robuste de params pour éviter NameError
    params = {}
    # Si le modèle LLM ou la fonction d'intent fournit des paramètres structurés, les extraire ici
    # Ex : intent, params = detect_intent(question)

    # DEBUG : log de l'intention détectée et de la question
    print(f"[DEBUG CHATBOT] intent détecté: {intent} | question: {question}")
    # Traitement prioritaire de la relance de ticket
    if intent == 'remind_ticket':
        action_type = "remind_ticket"
        ticket_id = None
        m = re.search(r"ticket\s*(\d+)", question.lower())
        if m:
            ticket_id = int(m.group(1))
        print(f"[DEBUG REMIND] ticket_id détecté: {ticket_id}")
        if ticket_id:
            session_token = get_session_token()
            if not session_token:
                result = {"type": "remind_ticket", "error": "Impossible d'authentifier GLPI"}
            else:
                remind_result = remind_ticket(session_token, ticket_id)
                print(f"[DEBUG REMIND] remind_result brut: {remind_result}")
                if not remind_result:
                    result = {"type": "remind_ticket", "ticket_id": ticket_id, "error": "Aucune réponse de la relance GLPI", "message": f"Échec de la relance pour le ticket {ticket_id}"}
                elif isinstance(remind_result, dict) and remind_result.get('error'):
                    result = {"type": "remind_ticket", "ticket_id": ticket_id, "error": remind_result.get('error'), "message": f"Erreur lors de la relance du ticket {ticket_id} : {remind_result.get('error')}"}
                elif isinstance(remind_result, dict) and remind_result.get('id'):
                    result = {"type": "remind_ticket", "ticket_id": ticket_id, "message": f"Relance envoyée pour le ticket {ticket_id}", "remind_result": remind_result}
                else:
                    result = {"type": "remind_ticket", "ticket_id": ticket_id, "remind_result": remind_result, "message": f"Réponse brute de la relance pour le ticket {ticket_id}"}
        else:
            result = {"type": "remind_ticket", "error": "Numéro de ticket non détecté dans la question."}
        log_data = {
            "user_id": user_id,
            "question": question,
            "action_type": action_type,
            "result": result,
            "timestamp": datetime.now()
        }
        log_id = logs_collection.insert_one(log_data).inserted_id
        print(f"[DEBUG RETURN] result envoyé: {result}")
        return mongo_to_json({"success": True, "result": result, "log_id": log_id})
    # Routage selon l'intention détectée
    # Si l'intention n'est pas reconnue mais que la question contient 'ticket', fallback sur la création de ticket
    elif intent == 'create_ticket' or (intent not in ['delete_ticket', 'update_ticket', 'list_tickets', 'get_ticket_status', 'remind_ticket', 'search_ticket'] and 'ticket' in question.lower()):
        # Fallback création de ticket UNIQUEMENT si ce n'est PAS une intention GLPI connue
        # Jamais pour remind_ticket ou si la question contient relancer/remind/suivi
        mots_relance = ['relancer', 'remind', 'suivi']
        if intent == 'remind_ticket' or any(word in question.lower() for word in mots_relance):
            result = {"error": "Vous n'êtes pas autorisé à relancer ce ticket ou l'action n'est pas permise."}
            log_data = {
                "user_id": user_id,
                "question": question,
                "action_type": "remind_ticket",
                "result": result,
                "timestamp": datetime.now()
            }
            log_id = logs_collection.insert_one(log_data).inserted_id
            print(f"[DEBUG RETURN] Fallback refusé pour relance : {result}")
            return mongo_to_json({"success": False, "result": result, "log_id": log_id})
        else:
            session_token = get_session_token()
            glpi_user_id = get_or_create_glpi_user(
                session_token,
                current_user.email,
                current_user.name,
                password_glpi,
                getattr(current_user, "role", None)
            )
            if glpi_user_id is None and not password_glpi:
                return {"error": "Veuillez fournir votre mot de passe GLPI pour la création du compte GLPI."}
            print(f"[DEBUG CHATBOT] params reçus pour création ticket: {params}")
            title = params.get('title') or question
            content = params.get('content') or question
            if not title:
                return {"error": "Impossible de créer le ticket : titre manquant (params['title']) dans la requête."}
            ticket = glpi_create_ticket(
                current_user=current_user,
                title=title,
                content=content,
                password_glpi=password_glpi
            )
            result = {"type": "ticket", "ticket": ticket, "message": "Ticket créé avec succès"}
    elif intent in ['delete_ticket', 'update_ticket', 'list_tickets', 'get_ticket_status', 'remind_ticket', 'search_ticket']:
        # Pour toutes ces actions, on vérifie juste l'existence du compte GLPI et on ne demande jamais le mot de passe
        session_token = get_session_token()
        glpi_user_id = get_or_create_glpi_user(
            session_token,
            current_user.email,
            current_user.name,
            None,  # Pas besoin du mot de passe
            getattr(current_user, "role", None)
        )
        if intent == 'delete_ticket':
            ticket_id = params.get('ticket_id')
            if not ticket_id:
                # Extraction fallback si params absent
                m = re.search(r"ticket\s*(\d+)", question.lower())
                if m:
                    ticket_id = int(m.group(1))
            if ticket_id:
                deleted = glpi_delete_ticket(ticket_id=ticket_id, current_user=current_user, password_glpi=None)
                # On considère que si la suppression retourne une clé 'error', c'est un échec, sinon c'est un succès
                if isinstance(deleted, dict) and deleted.get('error'):
                    result = {"type": "delete_ticket", "ticket_id": ticket_id, "error": deleted.get('error')}
                else:
                    result = {"type": "delete_ticket", "ticket_id": ticket_id, "message": f"Le ticket {ticket_id} a bien été supprimé."}
                # On retourne directement, sans enchaîner sur get_ticket_status ou autre
                log_data = {
                    "user_id": user_id,
                    "question": question,
                    "action_type": "delete_ticket",
                    "result": result,
                    "timestamp": datetime.now()
                }
                log_id = logs_collection.insert_one(log_data).inserted_id
                print(f"[LOG] Interaction sauvegardée avec _id: {log_id}")
                # Toujours renvoyer un dict non vide pour result
                if not result or not isinstance(result, dict) or len(result) == 0:
                    result = {"error": "Aucune réponse générée par le chatbot pour cette intention."}
                print(f"[DEBUG RETURN] result envoyé: {result}")
                return mongo_to_json({"success": True, "result": result, "log_id": log_id})
        
        if intent == 'update_ticket':
            ticket_id = params.get('ticket_id')
            if not ticket_id:
                m = re.search(r"ticket\s*(\d+)", question.lower())
                if m:
                    ticket_id = int(m.group(1))
            print(f"[DEBUG UPDATE] ticket_id détecté pour update_ticket: {ticket_id}")
            if ticket_id:
                # On suppose que le contenu à modifier est la question, sinon adapter ici
                updated = glpi_update_ticket(ticket_id=ticket_id, title=None, content=question, current_user=current_user)
                print(f"[DEBUG UPDATE] Résultat update_ticket: {updated}")
                result = {"type": "update_ticket", "ticket_id": ticket_id, "update_result": updated}
            else:
                result = {"type": "update_ticket", "error": "Numéro de ticket non détecté dans la question."}
            # Log et retour immédiat
            log_data = {
                "user_id": user_id,
                "question": question,
                "action_type": "update_ticket",
                "result": result,
                "timestamp": datetime.now()
            }
            log_id = logs_collection.insert_one(log_data).inserted_id
            print(f"[DEBUG RETURN] result envoyé: {result}")
            return mongo_to_json({"success": True, "result": result, "log_id": log_id})
        elif intent == 'list_tickets':
            tickets = glpi_list_tickets(current_user=current_user)
            result = {"type": "list_tickets", "tickets": tickets}
        elif intent == 'get_ticket_status':
            ticket_id = None
            m = None
            if params.get('ticket_id'):
                ticket_id = params.get('ticket_id')
            else:
                m = re.search(r"ticket\s*(\d+)", question.lower())
                if m:
                    ticket_id = int(m.group(1))
            if ticket_id:
                # À implémenter : fonction pour récupérer le statut du ticket
                result = {"type": "get_ticket_status", "ticket_id": ticket_id, "status": "À implémenter"}
                # Recherche le ticket par ID dans la liste
                tickets = glpi_list_tickets(current_user=current_user)
                ticket = next((t for t in tickets if str(t.get('id')) == str(ticket_id)), None)
                if ticket:
                    result = {"type": "get_ticket_status", "ticket_id": ticket_id, "status": ticket.get('status'), "ticket": ticket}
                else:
                    result = {"type": "get_ticket_status", "error": f"Aucun ticket trouvé avec l'ID {ticket_id}"}
            else:
                result = {"type": "get_ticket_status", "error": "Numéro de ticket non détecté dans la question."}
    else:
        # Fallback : FAQ classique (vector search + LLM)
        context = search_vector(question)
        prompt = build_prompt(question, context)
        llm_response = call_ollama(prompt)
        result = {"type": "faq", "answer": llm_response, "context": context, "intent": intent}

    # Log dans MongoDB
    log_data = {
        "user_id": user_id,
        "question": question,
        "action_type": action_type,
        "result": result,
        "timestamp": datetime.now()
    }
    log_id = logs_collection.insert_one(log_data).inserted_id
    print(f"[LOG] Interaction sauvegardée avec _id: {log_id}")
    # Conversion sécurisée de tout retour MongoDB
    return mongo_to_json({"success": True, "result": result, "log_id": log_id})
