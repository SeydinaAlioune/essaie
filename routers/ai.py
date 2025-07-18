import re
from fastapi import APIRouter, Depends, Body
from routers.auth import get_current_user
from routers.glpi import _create_ticket_internal, _create_ticket_followup_internal
from pydantic import BaseModel
from typing import Optional
from search_vector_llm import search_vector, build_prompt, call_llm
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId

# --- Configuration ---
mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["mcp_backend"]
logs_collection = db["chatbot_logs"] # Pour obtenir un handle vers la collection chabot_logs
drafts_collection = db["chatbot_ticket_drafts"] # Pour obtenir un handle(ref)vers notre collection chatbot_ticket_drafts.C'est la memoire a court terme du chatbot pour une conversation donnee 
router = APIRouter()

# --- Fonctions Utilitaires ---

def mongo_to_json(doc):
    """Convertit récursivement les ObjectId en str pour la sérialisation JSON."""
    if isinstance(doc, list):
        return [mongo_to_json(item) for item in doc]
    if isinstance(doc, dict):
        return {k: mongo_to_json(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc

def parse_llm_response(response_text: str) -> dict:
    """Analyse la réponse, potentiellement mal formatée, du LLM en un dictionnaire.
    Gère les clés avec ou sans formatage markdown (astérisques).
    """
    parsed_data = {}
    # Regex améliorée pour capturer une clé (lettres majuscules, _) et sa valeur.
    # La clé peut être optionnellement entourée d'astérisques.
    pattern = re.compile(r"\**([A-Z_]+)\**:\s*(.*?)(?=\n\**[A-Z_]+\**:|$)", re.DOTALL)
    matches = pattern.findall(response_text)
    
    for key, value in matches:
        cleaned_value = value.strip()
        parsed_data[key.strip()] = cleaned_value if cleaned_value else "inconnue"
        
    return parsed_data

def is_valid_for_ticket_creation(fields: dict) -> bool:
    """Vérifie si le contenu extrait est suffisamment qualitatif pour créer un ticket."""
    title = fields.get('titre', '').lower().strip()
    description = fields.get('description', '').lower().strip()
    
    # Mots-clés génériques à rejeter
    generic_terms = ["bonjour", "salut", "merci", "question", "aide", "test", "inconnue"]
    
    # Le titre ne doit pas être un terme générique et doit avoir une longueur minimale
    if not title or title in generic_terms or len(title) < 5:
        return False
        
    # La description ne doit pas être générique et doit avoir une longueur minimale
    if not description or description in generic_terms or len(description) < 10:
        return False
        
    return True

# --- Route Principale du Chatbot ---

class ChatbotRequest(BaseModel):
    question: str
    ticket_id: Optional[int] = None

@router.post("/chatbot/ask")
def ask_chatbot(request: ChatbotRequest, current_user=Depends(get_current_user)):
    question = request.question

    logs_collection.insert_one({
        "type": "request_received",
        "user_id": str(getattr(current_user, "id", None) or getattr(current_user, "_id", None) or getattr(current_user, "email", "unknown_user")),
        "question": question,
        "has_ticket_id": bool(request.ticket_id),
        "ticket_id": request.ticket_id,
        "timestamp": datetime.utcnow()
    }) # permet de looger toutes requete dans mongodb qui va servir de boite noire 

    # --- 0. GESTION PRIORITAIRE : AJOUT D'UN SUIVI À UN TICKET EXISTANT ---
    if request.ticket_id:
        logs_collection.insert_one({"type": "log", "message": f"Début de l'ajout d'un suivi au ticket {request.ticket_id}", "timestamp": datetime.utcnow()})
        followup_result = _create_ticket_followup_internal(
            ticket_id=request.ticket_id,
            content=question,
            user=current_user
        )
        if followup_result["success"]:
            logs_collection.insert_one({"type": "log", "message": f"Suivi ajouté avec succès au ticket {request.ticket_id}", "result": mongo_to_json(followup_result), "timestamp": datetime.utcnow()})
            return {"type": "followup_added", "message": "Votre suivi a bien été ajouté au ticket.", "followup": followup_result.get("followup")}
        else:
            logs_collection.insert_one({"type": "error", "message": f"Échec de l'ajout du suivi au ticket {request.ticket_id}", "error": followup_result.get('error'), "timestamp": datetime.utcnow()})
            return {"type": "error", "message": f"L'ajout de votre suivi a échoué: {followup_result.get('error')}"}

    user_id = str(getattr(current_user, "id", None) or getattr(current_user, "_id", None) or getattr(current_user, "email", "unknown_user"))
    ticket_draft_key = f"draft_{user_id}"

    # --- 1. GESTION DES INTENTIONS SIMPLES (Réponse rapide sans LLM) ---
    # Annulation explicite
    if question.strip().lower() in ["annuler", "stop", "laisse tomber"]:
        drafts_collection.delete_one({"_id": ticket_draft_key})
        return {"type": "cancelled", "message": "Opération annulée. N'hésitez pas si vous avez une autre question."}
        
    # Demande de statut de ticket
    if "statut" in question.lower() or "status" in question.lower() or "état" in question.lower():
        ticket_match = re.search(r"(\d+)", question)
        if ticket_match:
            ticket_id = int(ticket_match.group(1))
            from routers.glpi import internal_glpi_get_ticket
            # Note: internal_glpi_get_ticket doit être adaptée pour ne pas dépendre de Depends
            status_result = internal_glpi_get_ticket(ticket_id=ticket_id, current_user=current_user)
            return {"type": "ticket_status", "ticket_id": ticket_id, "status_result": mongo_to_json(status_result)}

    # --- 2. LOGIQUE DE CONVERSATION INTELLIGENTE (Pilotée par LLM) ---
    ticket_draft = drafts_collection.find_one({"_id": ticket_draft_key}) or {}
    history = ticket_draft.get("history", [])
    fields = ticket_draft.get("fields", {})

    # Appel au LLM avec l'historique complet pour comprendre le contexte
    context = search_vector(question)
    prompt = build_prompt(question, context, history)
    llm_response_text = call_llm(prompt) #qui permet d'envoyer le prompt a Together.aia
    parsed_response = parse_llm_response(llm_response_text)

    # Log de la transaction pour la traçabilité
    logs_collection.insert_one({
        "user_id": user_id, "question": question, "llm_prompt": prompt,
        "llm_raw_response": llm_response_text, "llm_parsed_response": parsed_response,
        "timestamp": datetime.utcnow()
    })

    # Si l'intention détectée par le LLM n'est PAS la création de ticket, et qu'aucune conversation n'est en cours
    if parsed_response.get("INTENTION") != "CREATION_TICKET" and not ticket_draft.get("in_progress"):
        # On gère les salutations de manière déterministe pour une meilleure expérience
        if parsed_response.get("INTENTION") == "SALUTATION":
            final_response = "Bonjour ! En quoi puis-je vous aider aujourd'hui ?"
        else:
            final_response = parsed_response.get("REPONSE", "Je continue de collecter les informations. Pouvez-vous m'en dire plus ?")
        return {"type": "faq", "message": final_response}

    # --- 3. CUMUL DES INFORMATIONS ET GESTION DE LA CRÉATION DE TICKET ---
    user_message = parsed_response.get("REPONSE", "Pouvez-vous préciser s'il vous plaît ?")

    # On met à jour les champs connus en cumulant les informations (ne jamais écraser une info par "inconnue")
    for key in ["TITRE", "DESCRIPTION", "PRIORITE", "CATEGORIE", "URGENCE"]:
        llm_value = parsed_response.get(key)
        if llm_value and llm_value not in ["inconnue", "non spécifié", ""]:
            fields[key.lower()] = llm_value

    # Vérifier si toutes les informations requises pour la création sont collectées
    required_fields = ["titre", "description"]
    is_complete = all(fields.get(f) and fields.get(f) not in ["inconnue", "non spécifié", ""] for f in required_fields)

    if is_complete and is_valid_for_ticket_creation(fields):
        # Tous les champs sont là, on crée le ticket
        creation_result = _create_ticket_internal(
            user=current_user,
            title=f"{fields.get('titre','Sans Titre')} [P: {fields.get('priorite','N/A')}, C: {fields.get('categorie','N/A')}]",
            content=fields.get('description', 'Pas de description.')
        )
        
        # Nettoyage du brouillon après la tentative de création
        drafts_collection.delete_one({"_id": ticket_draft_key})

        if creation_result["success"]:
            logs_collection.insert_one({"type": "log", "message": "Création de ticket réussie", "result": mongo_to_json(creation_result), "timestamp": datetime.utcnow()})
            ticket_info = creation_result.get("ticket", {})
            ticket_id = ticket_info.get("id", "inconnu")
            user_message = f"Ticket #{ticket_id} créé avec succès. Je reste à votre disposition si vous avez d'autres questions."
            return {"type": "ticket_created", "message": user_message, "ticket": mongo_to_json(ticket_info)}
        else:
            error_msg = creation_result.get("error", "une erreur inconnue")
            logs_collection.insert_one({"type": "error", "message": "Échec de la création du ticket", "error": error_msg, "timestamp": datetime.utcnow()})
            user_message = f"J'avais toutes les informations, mais la création du ticket a échoué en raison d'une erreur interne : {error_msg}. L'équipe technique a été notifiée."
            return {"type": "error", "message": user_message}

    # Si le ticket n'est pas complet, on continue la conversation
    history.append({"question": question, "response": user_message})
    drafts_collection.update_one(
        {"_id": ticket_draft_key},
        {"$set": {"in_progress": True, "history": history, "fields": fields}},
        upsert=True
    )

    return {"type": "conversation", "message": user_message}
