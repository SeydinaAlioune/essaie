print("\n\n*** CHARGEMENT DU FICHIER ANALYTICS.PY ***")
print(f"*** CHEMIN: {__file__} ***\n\n")

from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_agent_or_admin_user
from routers.glpi import get_session_token
from routers.configuration import load_glpi_config
import requests
from urllib.parse import urljoin
from datetime import datetime, timedelta
import re
from collections import Counter

router = APIRouter(
    prefix="/api/analytics",
    tags=["Analytics"],
)

# Statuts considérés comme "résolus"
RESOLVED_STATUSES = [5, 6]  # 5: solved, 6: closed

# Liste simple de stop words en français pour filtrer les mots non pertinents
STOP_WORDS = set([
    "un", "une", "des", "le", "la", "les", "de", "du", "ce", "cet", "cette", "ces", "mon", "ton", "son",
    "ma", "ta", "sa", "mes", "tes", "ses", "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
    "qui", "que", "quoi", "dont", "où", "pour", "avec", "sans", "dans", "sur", "est", "ai", "as", "a",
    "sommes", "êtes", "sont", "suis", "es", "et", "ou", "donc", "or", "ni", "car", "mais", "si",
    "probleme", "ticket", "demande", "aide", "support", "bonjour", "merci", "svp", "stp", "urgent"
])

def _get_glpi_count(session: requests.Session, glpi_url: str, params: dict = None) -> int:
    """Effectue un appel à l'API GLPI pour obtenir un nombre d'éléments."""
    if params is None:
        params = {}
    params['count'] = 'true'
    try:
        response = session.get(urljoin(glpi_url, 'Ticket'), params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        # Si la recherche ne trouve rien, GLPI peut renvoyer une liste vide au lieu de {'count': 0}
        if isinstance(data, dict):
            return data.get('count', 0)
        return 0
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Erreur de comptage GLPI: {e}")

@router.get("/stats", dependencies=[Depends(get_current_agent_or_admin_user)])
def get_main_stats():
    """Fournit les statistiques clés en utilisant des requêtes de comptage efficaces."""
    config = load_glpi_config()
    glpi_url = config.get("GLPI_API_URL")
    app_token = config.get("GLPI_APP_TOKEN")
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    with requests.Session() as session:
        session.headers.update({
            "Session-Token": session_token,
            "App-Token": app_token,
            "Content-Type": "application/json"
        })
        
        total_tickets = _get_glpi_count(session, glpi_url)
        
        resolved_params = {
            'criteria[0][field]': 'status',
            'criteria[0][searchtype]': 'equals',
        }
        for i, status in enumerate(RESOLVED_STATUSES):
            resolved_params[f'criteria[0][value][{i}]'] = status

        resolved_count = _get_glpi_count(session, glpi_url, params=resolved_params)

    if total_tickets == 0:
        return {"total_tickets": 0, "avg_response_time_hours": 0, "resolution_rate_percent": 0}

    resolution_rate = (resolved_count / total_tickets) * 100 if total_tickets > 0 else 0

    # Note: Le temps de réponse moyen ne peut pas être calculé efficacement sans récupérer tous les tickets.
    # Nous le mettons à 0 pour l'instant. Une autre stratégie serait nécessaire pour cette métrique.
    return {
        "total_tickets": total_tickets,
        "avg_response_time_hours": 0, # Métrique non calculable efficacement
        "resolution_rate_percent": round(resolution_rate, 2)
    }

@router.get("/recurring-issues", dependencies=[Depends(get_current_agent_or_admin_user)])
def get_recurring_issues(days: int = 30):
    """Analyse les titres des tickets récents pour identifier les problèmes fréquents."""
    config = load_glpi_config()
    glpi_url = config.get("GLPI_API_URL")
    app_token = config.get("GLPI_APP_TOKEN")
    session_token = get_session_token()
    if not session_token:
        raise HTTPException(status_code=503, detail="Connexion à GLPI impossible.")

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    params = {
        'criteria[0][field]': 'date_creation',
        'criteria[0][searchtype]': 'greater',
        'criteria[0][value]': cutoff_date,
        'is_deleted': '0'
    }

    with requests.Session() as session:
        session.headers.update({
            "Session-Token": session_token,
            "App-Token": app_token,
            "Content-Type": "application/json"
        })
        try:
            response = session.get(urljoin(glpi_url, 'Ticket'), params=params, timeout=30)
            response.raise_for_status()
            recent_tickets = response.json()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=503, detail=f"Impossible de récupérer les tickets récents: {e}")

    if not recent_tickets or not isinstance(recent_tickets, list):
        return []

    titles = [t.get('name', '') for t in recent_tickets]
    words = re.findall(r'\b\w+\b', ' '.join(titles).lower())
    filtered_words = [word for word in words if word not in STOP_WORDS and not word.isdigit()]
    word_counts = Counter(filtered_words)
    return word_counts.most_common(10)

def _get_ticket_details_for_summary(session: requests.Session, glpi_url: str, ticket_id: int):
    """Récupère les détails d'un ticket spécifique pour le résumé."""
    config = load_glpi_config()
    headers = {
        "Session-Token": get_session_token(),
        "App-Token": config.get("GLPI_APP_TOKEN"),
        "Content-Type": "application/json"
    }
    try:
        ticket_url = urljoin(glpi_url, f"Ticket/{ticket_id}")
        response = session.get(ticket_url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur de communication avec GLPI pour le ticket {ticket_id}: {e}")
        return None

def _call_llm_for_summary(prompt: str) -> str:
    """Simule un appel à un LLM pour générer un résumé."""
    # Dans une vraie application, ce serait un appel à une API comme OpenAI
    # Pour l'instant, nous retournons une version tronquée du prompt.
    return "Résumé intelligent du ticket généré par l'IA: " + prompt[:150] + "..."

@router.get("/ticket-summary/{ticket_id}", dependencies=[Depends(get_current_agent_or_admin_user)])
def get_ticket_summary(ticket_id: int):
    config = load_glpi_config()
    glpi_url = config.get("GLPI_API_URL")

    with requests.Session() as session:
        ticket = _get_ticket_details_for_summary(session, glpi_url, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket non trouvé ou erreur de communication GLPI.")

        # Utiliser le nom et le contenu du ticket pour le résumé
        prompt = f"Titre: {ticket.get('name', '')}\nDescription: {ticket.get('content', '')}"
        summary = _call_llm_for_summary(prompt)
        return {"summary": summary}
