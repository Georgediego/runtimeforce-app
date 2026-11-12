"""
RuntimeForce Application Configuration.
Single Source of Truth for system constants, ports, and environment defaults.
"""
import os
from dataclasses import dataclass

@dataclass
class AppConfig:
    APP_NAME: str = "RuntimeForce IDE"
    VERSION: str = "1.1.17"
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1")

config = AppConfig()
