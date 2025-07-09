from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables, SessionLocal
from routers import auth as auth_router, glpi, health, ai, analytics, admin, configuration, docs, knowledge_base
import models
from auth import hash_password

def create_default_admin():
    db = SessionLocal()
    try:
        # Vérifier si un admin existe déjà
        admin_user = db.query(models.User).filter(models.User.email == "admin@example.com").first()
        if not admin_user:
            # Créer l'utilisateur admin s'il n'existe pas
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
            print("Utilisateur admin par défaut créé.")
    finally:
        db.close()

def create_app():
    app = FastAPI(
        title="MCP API",
        description="API pour la gestion de la plateforme MCP",
        version="1.0.0"
    )

    # Configuration CORS
    origins = [
        "http://localhost:5173",  # Frontend Vite/React
        "http://localhost:3000",  # Autre port de développement frontend possible
        "http://localhost:8080",  # GLPI local
        "http://localhost",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup():
        create_db_and_tables()
        create_default_admin()

    # Enregistrement des routeurs
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(auth_router.router, prefix="/auth", tags=["Authentication"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(glpi.router, prefix="/api/glpi", tags=["GLPI"])
    app.include_router(ai.router, prefix="/ai", tags=["AI"])
    app.include_router(analytics.router)
    app.include_router(configuration.router, prefix="/config", tags=["Configuration"])
    app.include_router(docs.router, prefix="/docs-api", tags=["Documents"])
    app.include_router(knowledge_base.router, prefix="/kb", tags=["Knowledge Base"])

    @app.get("/", tags=["Root"])
    def read_root():
        return {"message": "Bienvenue sur le MCP backend !"}

    return app
