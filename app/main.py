"""AI Runtime IDE - thin entry point."""
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import register_all
from app.core.ssh import ssh_manager
from app.core.llm import orchestrator
from app.memory.store import store
from app.core.crypto import decrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_runtime.main")

app = FastAPI(title="AI Runtime IDE", version="2.0.0")

# Register all API routers via central registry
register_all(app)

# Mount static files
_static_dir = str(Path(__file__).resolve().parent / "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.on_event("startup")
async def startup_event():
    """Load provider keys from DB on startup."""
    try:
        encrypted_keys = store.get_all_provider_keys()
        decrypted_keys = {}
        for provider, key_enc in encrypted_keys.items():
            try:
                decrypted_keys[provider] = decrypt(key_enc)
            except Exception as e:
                logger.warning(f"Failed to decrypt {provider}: {e}")
        if decrypted_keys:
            orchestrator.set_provider_keys(decrypted_keys)
            logger.info(f"Loaded {len(decrypted_keys)} provider keys")
        else:
            logger.warning("No provider keys in DB.")
    except Exception as e:
        logger.error(f"Startup key load failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    await ssh_manager.close_all()
    logger.info("SSH connections closed")

@app.get("/")
async def root():
    """Serve main IDE page as static file (no Jinja2 parsing)."""
    return FileResponse("app/templates/index.html")