from fastapi import FastAPI
from routers import health
from routers import glpi
from routers import docs
from routers import auth
from routers import admin
from routers import ai

app = FastAPI()
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])
app.include_router(glpi.router, prefix="/glpi", tags=["glpi"])
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])

##endpoint “/”
@app.get("/")
def read_root():
    return {"message": "Bienvenue sur le MCP backend !"}
