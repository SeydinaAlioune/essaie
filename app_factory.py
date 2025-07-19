# Imports from standard library or third-party packages
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Imports from this project
from database import create_db_and_tables, SessionLocal
from auth import hash_password
import models
from routers import (
    users,
    auth,
    knowledge,
    configuration,
    glpi,
    middleware,
    analytics,
    admin,
    docs,
    knowledge_base,
)

def create_default_admin():
    """Crée un utilisateur administrateur par défaut s'il n'existe pas."""
    db = SessionLocal()
    try:
        admin_user = db.query(models.User).filter(models.User.email == "admin@example.com").first()
        if not admin_user:
            hashed_password = hash_password("admin")
            new_admin = models.User(
                email="admin@example.com",
                name="admin",
                hashed_password=hashed_password,
                role="admin",
                status="active"
            )
            db.add(new_admin)
            db.commit()
    finally:
        db.close()

def create_app():
    """Crée et configure l'instance de l'application FastAPI."""
    app = FastAPI(
        title="MCP API",
        description="API pour le Moteur de Connaissances Professionnelles",
        version="1.0.0"
    )

    # Événements de démarrage
    @app.on_event("startup")
    def on_startup():
        create_db_and_tables()
        create_default_admin()

    # Configuration CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Doit être restreint en production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inclusion des routeurs
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
    app.include_router(configuration.router, prefix="/config", tags=["Configuration"])
    app.include_router(glpi.router, prefix="/glpi", tags=["GLPI"])
    app.include_router(middleware.router, prefix="/middleware", tags=["Middleware"])
    app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(docs.router, prefix="/docs-management", tags=["Docs Management"])
    app.include_router(knowledge_base.router, prefix="/kb", tags=["Knowledge Base"])

    @app.get("/", tags=["Root"])
    def read_root():
        return {"message": "Bienvenue sur le MCP backend !"}

    return app
