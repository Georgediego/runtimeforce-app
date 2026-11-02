"""
RuntimeForce IDE — FastAPI main application entry point with LiteLLM & HuggingFace Log Suppression.
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.container import container
from app.api import register_all

# Suppress noisy third-party loggers completely
logging.getLogger("litellm").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

try:
    import litellm
    litellm.suppress_debug_info = True
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("runtimeforce.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 RuntimeForce IDE starting...")
    yield
    logger.info("🛑 RuntimeForce IDE shutting down...")
    try:
        await container.ssh_pool.close_all()
    except Exception as e:
        logger.warning(f"SSH cleanup failed: {e}")

app = FastAPI(
    title="RuntimeForce IDE",
    version="0.5.2",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_cached_app_version: Optional[str] = None
_changelog_mtime: float = 0.0

def get_app_version() -> str:
    global _cached_app_version, _changelog_mtime
    try:
        changelog_path = BASE_DIR.parent / "CHANGELOG.md"
        if not changelog_path.exists():
            changelog_path = Path("CHANGELOG.md")
        if changelog_path.exists():
            mtime = changelog_path.stat().st_mtime
            if _cached_app_version is not None and _changelog_mtime == mtime:
                return _cached_app_version
            content = changelog_path.read_text(encoding="utf-8")
            match = re.search(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", content, re.MULTILINE)
            if match:
                ver = match.group(1).strip()
                _cached_app_version = f"v{ver}" if not ver.startswith("v") else ver
                _changelog_mtime = mtime
                return _cached_app_version
    except Exception:
        pass
    if _cached_app_version is not None:
        return _cached_app_version
    _cached_app_version = "0.0.0"
    return _cached_app_version

templates.env.globals["app_version"] = get_app_version()

@app.get("/api/v1/version")
async def get_version_api():
    return {"version": get_app_version()}

register_all(app)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "runtimeforce-app"}
