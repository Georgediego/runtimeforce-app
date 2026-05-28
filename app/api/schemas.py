"""
Shared Pydantic schemas for API endpoints.
Used across all routers for request/response validation.
"""
from pydantic import BaseModel
from typing import List, Dict, Optional


class ChatCompletionPayload(BaseModel):
    """Request body for streaming chat completion."""
    session_id: str
    messages: List[Dict[str, str]]
    strategy: Optional[str] = "auto"
    model_lock: Optional[str] = None
    temperature: Optional[float] = 0.2


class KeysUpdatePayload(BaseModel):
    """Request body for hot-reloading provider API keys."""
    keys: Dict[str, str]


class SessionCreatePayload(BaseModel):
    """Request body for creating a new chat session."""
    title: str
    id: Optional[str] = None


class WorkspaceCreatePayload(BaseModel):
    """Request body for creating a new workspace (local or SSH)."""
    name: str
    type: str  # 'local' or 'ssh'
    host: Optional[str] = None
    port: Optional[int] = 22
    username: Optional[str] = None
    path: Optional[str] = None
    auth_type: Optional[str] = None  # 'password' or 'key'
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None
    activate: Optional[bool] = True