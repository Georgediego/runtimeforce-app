"""
Unified API Router Registry with Memory API.
"""
from app.api.http.workspace_http_router import router as workspace_router
from app.api.http.git_http_router import router as git_router
from app.api.http.session_http_router import router as session_router
from app.api.http.message_http_router import router as message_router
from app.api.http.model_http_router import router as model_router
from app.api.http.keys_http_router import router as keys_router
from app.api.http.telemetry_http_router import router as telemetry_router
from app.api.http.project_http_router import router as project_router
from app.api.http.billing_http_router import router as billing_router
from app.api.http.usage_http_router import router as usage_router
from app.api.http.audit_http_router import router as audit_router
from app.api.http.support_http_router import router as support_router
from app.api.http.memory_http_router import router as memory_router
from app.api.http.approval_http_router import router as approval_router
from app.api.websocket.chat_ws_router import router as chat_ws_router

ALL_ROUTERS = [
    workspace_router,
    git_router,
    session_router,
    message_router,
    model_router,
    keys_router,
    telemetry_router,
    project_router,
    billing_router,
    usage_router,
    audit_router,
    support_router,
    memory_router,
    approval_router,
    chat_ws_router,
]

def register_all(app):
    for r in ALL_ROUTERS:
        app.include_router(r)
