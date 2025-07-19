import json
from fastapi import APIRouter, HTTPException
from schemas import MiddlewareConfig

CONFIG_FILE = "middleware_config.json"

router = APIRouter(
    prefix="/middleware",
    tags=["middleware"],
)

def read_config():
    """Helper function to read the config file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Middleware configuration file not found.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error decoding middleware configuration file.")

def write_config(config: MiddlewareConfig):
    """Helper function to write to the config file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config.dict(), f, indent=4)

@router.get("/config", response_model=MiddlewareConfig)
async def get_middleware_config():
    """Retrieve the current middleware configuration."""
    config_data = read_config()
    return config_data

@router.post("/config")
async def set_middleware_config(config: MiddlewareConfig):
    """Update the middleware configuration."""
    write_config(config)
    return {"message": "Middleware configuration updated successfully."}
