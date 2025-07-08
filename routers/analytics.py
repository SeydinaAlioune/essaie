from fastapi import APIRouter, Depends, HTTPException
from routers.auth import require_role
from routers.glpi import get_session_token
from routers.configuration import load_glpi_config
import requests

router = APIRouter()

# Statuts considérés comme "résolus"
RESOLVED_STATUSES = [5, 6]  # 5: solved, 6: closed

def _get_all_glpi_tickets(session_token: str):
    """Utilitaire pour récupérer tous les tickets de GLPI en gérant la pagination."""
    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    all_tickets = []
    range_start = 0
    range_size = 50  # Récupérer 50 tickets à la fois

    while True:
        url = f"{config['GLPI_API_URL']}/Ticket?range={range_start}-{range_start + range_size}"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            tickets = response.json()
            if not tickets:
                break  # Plus de tickets à récupérer
            all_tickets.extend(tickets)
            range_start += range_size
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la récupération des tickets GLPI: {e}")
            raise HTTPException(status_code=503, detail="Erreur de communication avec GLPI.")
    return all_tickets

@router.get("/stats", dependencies=[Depends(require_role("admin"))])
def get_main_stats():
    """
    Fournit les statistiques clés pour le dashboard.
    """
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    tickets = _get_all_glpi_tickets(session_token)
    total_tickets = len(tickets)

    if total_tickets == 0:
        return {
            "total_tickets": 0,
            "avg_response_time_hours": 0,
            "resolution_rate_percent": 0
        }

    # Calcul du taux de résolution
    resolved_count = sum(1 for t in tickets if t.get('status') in RESOLVED_STATUSES)
    resolution_rate = (resolved_count / total_tickets) * 100 if total_tickets > 0 else 0

    # Calcul du temps de réponse moyen (en heures)
    total_response_time_seconds = sum(t.get('takeintoaccount_delay_stat', 0) for t in tickets)
    avg_response_time_seconds = total_response_time_seconds / total_tickets if total_tickets > 0 else 0
    avg_response_time_hours = avg_response_time_seconds / 3600

    return {
        "total_tickets": total_tickets,
        "avg_response_time_hours": round(avg_response_time_hours, 2),
        "resolution_rate_percent": round(resolution_rate, 2)
    }

from datetime import datetime, timedelta
import re
from collections import Counter

# Liste simple de stop words en français pour filtrer les mots non pertinents
STOP_WORDS = set([
    "un", "une", "des", "le", "la", "les", "de", "du", "ce", "cet", "cette", "ces", "mon", "ton", "son",
    "ma", "ta", "sa", "mes", "tes", "ses", "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
    "qui", "que", "quoi", "dont", "où", "pour", "avec", "sans", "dans", "sur", "est", "ai", "as", "a",
    "sommes", "êtes", "sont", "suis", "es", "et", "ou", "donc", "or", "ni", "car", "mais", "si",
    "probleme", "ticket", "demande", "aide", "support", "bonjour", "merci", "svp", "stp", "urgent"
])

@router.get("/recurring-issues", dependencies=[Depends(require_role("admin"))])
def get_recurring_issues(days: int = 30):
    """
    Analyse les titres des tickets sur une période donnée (par défaut 30 jours)
    pour identifier les problèmes les plus fréquents.
    """
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    tickets = _get_all_glpi_tickets(session_token)
    
    # Filtrer les tickets de la période spécifiée
    recent_tickets = []
    limit_date = datetime.now() - timedelta(days=days)
    for t in tickets:
        try:
            ticket_date = datetime.strptime(t.get('date_creation', ''), '%Y-%m-%d %H:%M:%S')
            if ticket_date >= limit_date:
                recent_tickets.append(t)
        except (ValueError, TypeError):
            # Ignorer les tickets avec une date invalide ou manquante
            continue

    # Analyser les titres
    all_words = []
    for t in recent_tickets:
        title = t.get('name', '').lower()
        words = re.findall(r'\b\w+\b', title)  # Extraire les mots
        all_words.extend([word for word in words if word not in STOP_WORDS and not word.isdigit()])

    # Compter la fréquence des mots
    word_counts = Counter(all_words)
    
    # Retourner les 10 problèmes les plus fréquents
    return word_counts.most_common(10)

def _get_ticket_details(session_token: str, ticket_id: int):
    """Récupère les détails complets d'un ticket, y compris les suivis."""
    config = load_glpi_config()
    headers = {"Session-Token": session_token, "App-Token": config['GLPI_APP_TOKEN']}
    
    # Récupérer le ticket principal
    try:
        url_ticket = f"{config['GLPI_API_URL']}/Ticket/{ticket_id}"
        ticket_resp = requests.get(url_ticket, headers=headers)
        ticket_resp.raise_for_status()
        ticket = ticket_resp.json()
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=404, detail="Ticket non trouvé ou erreur de communication.")

    # Récupérer les suivis
    try:
        url_followups = f"{config['GLPI_API_URL']}/Ticket/{ticket_id}/ITILFollowup"
        followups_resp = requests.get(url_followups, headers=headers)
        followups_resp.raise_for_status()
        ticket['followups'] = followups_resp.json()
    except requests.exceptions.RequestException:
        ticket['followups'] = [] # Pas de suivis ou erreur, on continue

    return ticket

def _call_llm_for_summary(context: str):
    """Appelle le LLM local pour générer un résumé."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma:2b", "prompt": context, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("response", "Le résumé n'a pas pu être généré.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur LLM: {e}")
        raise HTTPException(status_code=503, detail="Le service de résumé est indisponible.")

@router.get("/ticket-summary/{ticket_id}", dependencies=[Depends(require_role("admin"))])
def get_ticket_summary(ticket_id: int):
    """
    Génère un résumé intelligent d'un ticket spécifique en utilisant un LLM.
    """
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    ticket = _get_ticket_details(session_token, ticket_id)

    # Construire le contexte pour le LLM
    context = f"Titre du Ticket: {ticket.get('name', '')}\n\nDescription initiale:\n{ticket.get('content', '')}\n\n---\nÉchanges et suivis:\n"
    
    # Trier les suivis par date pour un résumé cohérent
    sorted_followups = sorted(ticket.get('followups', []), key=lambda f: f.get('date_creation', ''))

    for followup in sorted_followups:
        user_type = "Client" if followup.get('requesttypes_id') == 1 else "Support"
        context += f"- [{user_type} - {followup.get('date_creation', '')}]: {followup.get('content', '')}\n"
    
    prompt = f"Voici un ticket GLPI. Résume-le de manière concise en 3 points : 1. Problème initial, 2. Actions réalisées, 3. Résolution ou état actuel.\n\n---\n{context}"

    summary = _call_llm_for_summary(prompt)
    return {"summary": summary}
