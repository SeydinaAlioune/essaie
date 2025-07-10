import json
from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_admin_user

CONFIG_FILE = "config.json"

router = APIRouter()

def load_glpi_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Retourne une configuration par défaut ou vide si le fichier n'existe pas ou est corrompu
        return {
            "GLPI_API_URL": "",
            "GLPI_APP_TOKEN": "",
            "GLPI_USER_TOKEN": "",
            "TOGETHER_API_KEY": ""
        }

def save_glpi_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)

@router.get("/glpi", dependencies=[Depends(get_current_admin_user)])
def get_glpi_config():
    """
    Récupère la configuration GLPI actuelle. Pour la sécurité, le token n'est pas retourné.
    """
    config = load_glpi_config()
    # Ne jamais exposer les tokens via une API GET
    return {"GLPI_API_URL": config.get("GLPI_API_URL")}

@router.post("/glpi", dependencies=[Depends(get_current_admin_user)])
def update_glpi_config(new_config: dict):
    """
    Met à jour la configuration GLPI.
    Le frontend doit envoyer un objet avec les clés GLPI_API_URL et GLPI_APP_TOKEN.
    """
    if not all(k in new_config for k in ["GLPI_API_URL", "GLPI_APP_TOKEN"]):
        raise HTTPException(status_code=400, detail="Les clés GLPI_API_URL et GLPI_APP_TOKEN sont requises.")

    current_config = load_glpi_config()
    
    # Mettre à jour les valeurs
    current_config["GLPI_API_URL"] = new_config["GLPI_API_URL"]
    current_config["GLPI_APP_TOKEN"] = new_config["GLPI_APP_TOKEN"]
    # Le user_token n'est pas modifié via cette interface pour le moment

    save_glpi_config(current_config)
    
    return {"message": "Configuration GLPI mise à jour avec succès."}

@router.get("/middleware", dependencies=[Depends(get_current_admin_user)])
def get_middleware_config():
    """
    Récupère la configuration actuelle du middleware (niveau de log, cache).
    """
    config = load_glpi_config()
    # Retourne la configuration du middleware ou des valeurs par défaut
    return config.get("middleware", {
        "log_level": "INFO",
        "cache_enabled": False
    })

@router.post("/middleware", dependencies=[Depends(get_current_admin_user)])
def update_middleware_config(new_config: dict):
    """
    Met à jour la configuration du middleware.
    Le frontend doit envoyer un objet avec les clés 'log_level' et/ou 'cache_enabled'.
    """
    if "log_level" not in new_config and "cache_enabled" not in new_config:
        raise HTTPException(status_code=400, detail="Au moins une clé de configuration est requise.")

    current_config = load_glpi_config()
    if "middleware" not in current_config:
        current_config["middleware"] = {}

    if "log_level" in new_config:
        # TODO: Ajouter une validation pour les niveaux de log (e.g., INFO, DEBUG, ERROR)
        current_config["middleware"]["log_level"] = new_config["log_level"]
    
    if "cache_enabled" in new_config:
        current_config["middleware"]["cache_enabled"] = bool(new_config["cache_enabled"])

    save_glpi_config(current_config)
    
    # Note: La modification dynamique du niveau de log sans redémarrage est complexe
    # et n'est pas implémentée ici. La configuration sera appliquée au prochain redémarrage.
    return {"message": "Configuration du middleware mise à jour. Un redémarrage peut être nécessaire."}

