import re
from fastapi import APIRouter, Depends, Body
from routers.auth import get_current_user
from routers.glpi import glpi_create_ticket, get_session_token
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
def ask_chatbot(question: str = Body(...), current_user=Depends(get_current_user)):
    user_id = getattr(current_user, "id", None) or getattr(current_user, "_id", None) or getattr(current_user, "email", None)
    action_type = "faq"
    result = {}

    # --- LOGIQUE MULTI-TOURS POUR CRÉATION DE TICKET, CONFIRMATION ET FAQ INTELLIGENTE ---
    # On utilise MongoDB pour stocker l'état du ticket en cours (clé: user_id+'_ticket_draft')
    ticket_draft_key = f"{user_id}_ticket_draft"
    ticket_draft = db["chatbot_ticket_drafts"].find_one({"_id": ticket_draft_key}) or {}
    # --- PRIORITÉ : Si la question concerne le statut d’un ticket, on traite cette demande immédiatement ---
    if any(word in question.lower() for word in ["statut", "status", "état"]):
        ticket_match = re.search(r"ticket\s*(\d+)", question.lower())
        if ticket_match:
            ticket_id = ticket_match.group(1)
            try:
                from routers.glpi import internal_glpi_get_ticket
                status_result = internal_glpi_get_ticket(ticket_id=int(ticket_id), current_user=current_user)
                return {"type": "ticket_status", "ticket_id": ticket_id, "status_result": status_result, "message": f"Statut du ticket {ticket_id} récupéré."}
            except Exception as e:
                return {"type": "ticket_status", "ticket_id": ticket_id, "error": str(e)}
        else:
            return {"type": "ticket_status", "error": "Numéro de ticket non trouvé dans la question."}
    # Si un draft existe, on complète les champs manquants
    if ticket_draft.get("in_progress"):
        next_field = ticket_draft.get("next_field")
        # 1. FAQ intelligente : l'utilisateur doit répondre si la FAQ a résolu le problème
        if next_field == "faq_feedback":

            if question.strip().lower() in ["oui", "yes", "merci", "résolu", "ok"]:
                db["chatbot_ticket_drafts"].delete_one({"_id": ticket_draft_key})
                return {"type": "faq_resolved", "message": "Heureux d'avoir pu vous aider !"}
            elif question.strip().lower() in ["non", "no", "pas résolu", "toujours bloqué", "pas ok"]:
                # On démarre la collecte multi-tours
                ticket_draft["next_field"] = "titre"
                db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
                return {"type": "ask_field", "field": "titre", "message": "Merci de préciser le titre du ticket."}
            else:
                return {"type": "ask_field", "field": "faq_feedback", "message": "Est-ce que cette réponse a résolu votre problème ? (oui/non)"}
        # 2. Confirmation classique
        if next_field == "confirmation":
            if question.strip().lower() in ["oui", "yes", "y"]:
                # Avant de lancer la collecte, on tente une FAQ intelligente
                context = search_vector(ticket_draft.get("original_question", ""))
                llm_response = call_ollama(build_prompt(ticket_draft.get("original_question", ""), context))
                if llm_response and len(llm_response.strip()) > 0:
                    # On suggère la FAQ et attend feedback utilisateur
                    ticket_draft["faq_suggested"] = llm_response
                    ticket_draft["next_field"] = "faq_feedback"
                    db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
                    return {
                        "type": "faq_suggestion",
                        "faq_answer": llm_response,
                        "message": "Voici une réponse qui pourrait résoudre votre problème. Cette réponse vous aide-t-elle ? (oui/non)"
                    }
                # Sinon, on démarre directement la collecte multi-tours
                ticket_draft["next_field"] = "titre"
                db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
                return {"type": "ask_field", "field": "titre", "message": "Merci de préciser le titre du ticket."}
            elif question.strip().lower() in ["non", "no", "n"]:
                db["chatbot_ticket_drafts"].delete_one({"_id": ticket_draft_key})
                return {"type": "confirmation_cancelled", "message": "Création de ticket annulée."}
            else:
                return {"type": "ask_field", "field": "confirmation", "message": "Merci de répondre par oui ou non. Voulez-vous que je crée un ticket pour ce problème ?"}
        # 3. Collecte multi-tours classique
        if next_field == "titre":
            ticket_draft["titre"] = question.strip()
            ticket_draft["next_field"] = "description"
            db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
            return {"type": "ask_field", "field": "description", "message": "Merci de décrire le problème à signaler."}
        elif next_field == "description":
            ticket_draft["description"] = question.strip()
            ticket_draft["next_field"] = "priorite"
            db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
            return {"type": "ask_field", "field": "priorite", "message": "Quelle est la priorité du ticket ? (basse, normale, haute, urgente)"}
        elif next_field == "priorite":
            ticket_draft["priorite"] = question.strip().lower()
            ticket_draft["next_field"] = "categorie"
            db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
            return {"type": "ask_field", "field": "categorie", "message": "Quelle est la catégorie du problème ? (matériel, logiciel, réseau, autre)"}
        elif next_field == "categorie":
            ticket_draft["categorie"] = question.strip().lower()
            ticket_draft["next_field"] = "urgence"
            db["chatbot_ticket_drafts"].update_one({"_id": ticket_draft_key}, {"$set": ticket_draft}, upsert=True)
            return {"type": "ask_field", "field": "urgence", "message": "Ce problème est-il urgent ? (oui/non)"}
        elif next_field == "urgence":
            ticket_draft["urgence"] = question.strip().lower()
            # Tous les champs sont remplis, on crée le ticket
            titre = ticket_draft["titre"]
            description = ticket_draft["description"]
            priorite = ticket_draft["priorite"]
            categorie = ticket_draft["categorie"]
            urgence = ticket_draft["urgence"]
            db["chatbot_ticket_drafts"].delete_one({"_id": ticket_draft_key})
            ticket = glpi_create_ticket(
                current_user=current_user,
                title=f"{titre} [Priorité: {priorite}, Catégorie: {categorie}, Urgence: {urgence}]",
                content=description
            )
            result = {"type": "ticket", "ticket": ticket, "message": "Ticket créé avec succès avec toutes les informations."}
            action_type = "ticket"
        else:
            db["chatbot_ticket_drafts"].delete_one({"_id": ticket_draft_key})
            return {"type": "error", "message": "Erreur dans la collecte des informations du ticket. Veuillez recommencer."}
    # --- FIN LOGIQUE MULTI-TOURS ---

    # 1. Analyse d’intention (relance ticket)
    relance_match = re.search(r"relancer(?:\s+le)?\s+ticket\s*(\d+)|rappeler(?:\s+le)?\s+ticket\s*(\d+)", question.lower())
    if relance_match:
        # Extraire le numéro de ticket
        ticket_id = relance_match.group(1) or relance_match.group(2)
        # Authentification GLPI (session_token)
        session_token = get_session_token()
        if not session_token:
            result = {"type": "relance", "error": "Impossible d'authentifier GLPI"}
        else:
            remind_result = remind_ticket(session_token, ticket_id)
            result = {"type": "relance", "ticket_id": ticket_id, "remind_result": remind_result, "message": f"Relance envoyée pour le ticket {ticket_id}"}
        action_type = "relance"
    # 2. Analyse d’intention (modification ticket)
    elif re.search(r"(modifie|modifier|update|corrige|corriger)[^\d]*(\d+)", question.lower()):
        # Extraction du numéro de ticket et du nouveau contenu éventuel
        update_match = re.search(r"(modifie|modifier|update|corrige|corriger)[^\d]*(\d+)", question.lower())
        ticket_id = update_match.group(2)
        # Recherche d'un nouveau titre ou contenu dans la question (optionnel)
        # Ici, on prend tout après le numéro comme contenu
        content_match = re.search(r"(modifie|modifier|update|corrige|corriger)[^\d]*(\d+)\s*[:-]?\s*(.*)", question.lower())
        new_content = content_match.group(3) if content_match and content_match.group(3) else None
        try:
            # Appel direct à la fonction interne (et non plus au route handler FastAPI)
            from routers.glpi import internal_glpi_update_ticket
            update_result = internal_glpi_update_ticket(ticket_id=int(ticket_id), title=None, content=new_content, current_user=current_user)
            result = {"type": "update_ticket", "ticket_id": ticket_id, "update_result": update_result, "message": f"Ticket {ticket_id} modifié."}
        except Exception as e:
            result = {"type": "update_ticket", "ticket_id": ticket_id, "error": str(e)}
        action_type = "update_ticket"
    # 3. Analyse d’intention (statut/état ticket) -- doit être AVANT la création de ticket !
    elif any(word in question.lower() for word in ["statut", "status", "état"]):
        # Extraction du numéro de ticket
        ticket_match = re.search(r"ticket\s*(\d+)", question.lower())
        if ticket_match:
            ticket_id = ticket_match.group(1)
            try:
                from routers.glpi import internal_glpi_get_ticket
                status_result = internal_glpi_get_ticket(ticket_id=int(ticket_id), current_user=current_user)
                result = {"type": "ticket_status", "ticket_id": ticket_id, "status_result": status_result, "message": f"Statut du ticket {ticket_id} récupéré."}
            except Exception as e:
                result = {"type": "ticket_status", "ticket_id": ticket_id, "error": str(e)}
        else:
            result = {"type": "ticket_status", "error": "Numéro de ticket non trouvé dans la question."}
        action_type = "ticket_status"
    # 4. Suppression/fermeture de ticket (non supportée par le chatbot)
    elif any(word in question.lower() for word in ["supprimer", "delete", "remove", "fermer", "close"]):
        # Extraction éventuelle du numéro de ticket
        ticket_match = re.search(r"ticket\s*(\d+)", question.lower())
        ticket_id = ticket_match.group(1) if ticket_match else None
        result = {
            "type": "unsupported_action",
            "ticket_id": ticket_id,
            "error": "La suppression ou la fermeture de ticket n'est pas supportée via le chatbot. Veuillez contacter le support directement si nécessaire."
        }
        action_type = "unsupported_action"
    # 5. Création ticket (incident, bug, etc. -- intention explicite)
    elif (
        any(keyword in question.lower() for keyword in ["incident", "problème", "bug", "erreur", "panne", "plantage", "crash"]) or
        re.search(r"cr[ée]e?(-| )?moi( un)? ticket", question.lower()) or
        re.search(r"ouvrir( un)? ticket", question.lower()) or
        re.search(r"j[’']ai un problème", question.lower())
    ):
        # --- Empêcher la création pour commande générique sans contenu ---
        commande_ticket = (
            re.fullmatch(r"(cr[ée]e?(-| )?moi( un)? ticket|ouvrir( un)? ticket|j[’']ai un problème)", question.strip().lower())
        )
        if commande_ticket:
            missing_fields = ["titre du ticket", "description du problème"]
            result = {
                "type": "ticket_incomplete",
                "missing_fields": missing_fields,
                "message": "Merci de préciser le titre du ticket et décrire le problème à signaler."
            }
            action_type = "ticket_incomplete"
            return result
        # --- Complétion d'informations manquantes classique ---
        titre = question.strip()
        description = question.strip()
        missing_fields = []
        if len(titre) < 10:
            missing_fields.append("titre (au moins 10 caractères)")
        if len(description) < 15:
            missing_fields.append("description (au moins 15 caractères)")
        if missing_fields:
            result = {
                "type": "ticket_incomplete",
                "missing_fields": missing_fields,
                "message": f"Merci de préciser : {', '.join(missing_fields)}"
            }
            action_type = "ticket_incomplete"
            return result
        # --- Création directe si tout est OK ---
        action_type = "ticket"
        ticket = glpi_create_ticket(
            current_user=current_user,
            title=titre,
            content=description
        )
        result = {"type": "ticket", "ticket": ticket, "message": "Ticket créé avec succès"}

    # 5.bis. INTENTION FLOUE : demander confirmation avant création de ticket
    elif (
        any(keyword in question.lower() for keyword in ["problème", "besoin d'aide", "ça ne marche pas", "ça bug", "impossible d'utiliser", "fonctionne pas"]) and
        not any(keyword in question.lower() for keyword in ["incident", "bug", "crée", "ouvrir", "ticket", "plantage", "crash"])
    ):
        # --- Demande de confirmation explicite, on démarre un draft ---
        ticket_draft = {
            "_id": ticket_draft_key,
            "in_progress": True,
            "next_field": "confirmation",
            "original_question": question
        }
        db["chatbot_ticket_drafts"].replace_one({"_id": ticket_draft_key}, ticket_draft, upsert=True)
        return {
            "type": "confirmation_ticket",
            "question": "Voulez-vous que je crée un ticket pour ce problème ?",
            "original_question": question
        }

    else:
        # 6. Fallback : question générale ou FAQ (aucune création de ticket !)
        # Recherche vectorielle + génération LLM
        context = search_vector(question)
        llm_response = call_ollama(build_prompt(question, context))
        result = {
            "type": "faq",
            "llm_response": llm_response,
            "message": "Réponse générée par le chatbot (aucune création de ticket)."
        }
        action_type = "faq"
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
