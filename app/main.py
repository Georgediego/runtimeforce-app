"""AI Runtime IDE - thin entry point."""
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.api import register_all
from app.core.ssh import ssh_manager
from app.core.llm import orchestrator, model_registry
from app.memory.store import store
from app.core.crypto import decrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_runtime.main")

app = FastAPI(title="AI Runtime IDE", version="2.0.0")
templates = Jinja2Templates(directory="app/templates")

# Register all API routers
register_all(app)

# Mount static files
_static_dir = str(Path(__file__).resolve().parent / "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.on_event("startup")
async def startup_load_keys():
    try:
        encrypted_keys = store.get_all_provider_keys()
        if not encrypted_keys:
            logger.info("No provider keys in DB.")
            return
        decrypted = {}
        for provider, enc in encrypted_keys.items():
            try:
                decrypted[provider] = decrypt(enc)
            except Exception as e:
                logger.warning(f"Failed to decrypt key for {provider}: {e}")
        if decrypted:
            orchestrator.set_provider_keys(decrypted)
            await model_registry.refresh_all(decrypted)
            total = len(model_registry.get_available_models())
            logger.info(f"Loaded {len(decrypted)} keys, discovered {total} models")
    except Exception as e:
        logger.error(f"Startup keys failed: {e}")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.on_event("shutdown")
async def shutdown():
    await ssh_manager.close_all()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
