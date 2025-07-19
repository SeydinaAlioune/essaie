import json
from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_admin_user

CONFIG_FILE = "config.json"

router = APIRouter()

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)

@router.get("/glpi", dependencies=[Depends(get_current_admin_user)])
def get_glpi_config():
    config = load_config()
    return {"GLPI_API_URL": config.get("GLPI_API_URL", "")}

@router.post("/glpi", dependencies=[Depends(get_current_admin_user)])
def update_glpi_config(new_config: dict):
    if not all(k in new_config for k in ["GLPI_API_URL", "GLPI_APP_TOKEN"]):
        raise HTTPException(status_code=400, detail="Les clés GLPI_API_URL et GLPI_APP_TOKEN sont requises.")

    current_config = load_config()
    current_config["GLPI_API_URL"] = new_config["GLPI_API_URL"]
    current_config["GLPI_APP_TOKEN"] = new_config["GLPI_APP_TOKEN"]
    save_config(current_config)
    return {"message": "Configuration GLPI mise à jour avec succès."}

@router.get("/middleware", dependencies=[Depends(get_current_admin_user)])
def get_middleware_config():
    """
    Récupère la configuration actuelle du middleware.
    """
    config = load_config()
    return config.get("middleware", {
        "log_level": "INFO",
        "waf_enabled": False,
        "rate_limiting_enabled": True,
        "maintenance_mode": False
    })

@router.post("/middleware", dependencies=[Depends(get_current_admin_user)])
def update_middleware_config(new_config: dict):
    """
    Met à jour la configuration du middleware.
    """
    current_config = load_config()
    if "middleware" not in current_config:
        current_config["middleware"] = {}

    # Mettre à jour chaque clé si elle est présente dans la requête
    for key in ["log_level", "waf_enabled", "rate_limiting_enabled", "maintenance_mode"]:
        if key in new_config:
            if isinstance(new_config[key], bool):
                 current_config["middleware"][key] = bool(new_config[key])
            else:
                 current_config["middleware"][key] = new_config[key]

    save_config(current_config)
    return {"message": "Configuration du middleware mise à jour. Un redémarrage peut être nécessaire."}

