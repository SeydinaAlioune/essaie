from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import health, glpi, docs, auth, admin, ai, configuration, knowledge_base, analytics

app = FastAPI()

# Configuration CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routeurs
# Routes publiques
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(glpi.router, prefix="/api/glpi", tags=["glpi"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])

# Routes d'administration
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(configuration.router, prefix="/api/admin/config", tags=["config"])
app.include_router(knowledge_base.router, prefix="/api/admin/kb", tags=["knowledge_base"])

# Route pour la documentation (généralement non préfixée par /api)
app.include_router(docs.router, prefix="/docs", tags=["docs"])

##endpoint “/”
@app.get("/")
def read_root():
    return {"message": "Bienvenue sur le MCP backend !"}
