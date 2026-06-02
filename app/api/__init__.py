from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.api.workspaces import router as workspaces_router
from app.api.models import router as models_router
from app.api.keys import router as keys_router
from app.api.git import router as git_router
from app.api.telemetry import router as telemetry_router

ALL_ROUTERS = [
    chat_router,
    sessions_router,
    workspaces_router,
    models_router,
    keys_router,
    git_router,
    telemetry_router,
]

def register_all(app):
    """Register all API routers on the FastAPI app instance."""
    for r in ALL_ROUTERS:
        app.include_router(r)