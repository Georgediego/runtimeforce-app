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

from fastapi import FastAPI, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import httpx
from fastapi.responses import HTMLResponse

from app.container import container
from app.api import register_all
from app.core.version_utils import is_newer_version
from app.core.security.entitlements import require_plan_feature

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
    version="1.0.1",
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

# Prefer GitHub main; use the SaaS endpoint as a server-side network fallback.
IDE_CHANGELOG_URL = "https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/CHANGELOG.md"
IDE_VERSION_FALLBACK_URL = "https://runtimeforce.dev/api/v1/ide-version"

async def fetch_latest_ide_version():
    """Return the stable IDE version and its source, or raise if both sources fail."""
    sources = (
        ("github-main-changelog", IDE_CHANGELOG_URL),
        ("runtimeforce-server", IDE_VERSION_FALLBACK_URL),
    )
    last_error = None
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for source, url in sources:
            try:
                remote = await client.get(url, headers={"Cache-Control": "no-cache"})
                remote.raise_for_status()
                if source == "github-main-changelog":
                    match = re.search(
                        r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?",
                        remote.text,
                        re.MULTILINE,
                    )
                else:
                    payload = remote.json()
                    match = re.fullmatch(
                        r"v?(\d+\.\d+\.\d+)",
                        str(payload.get("version", "")).strip(),
                    )
                if not match or match.group(1) == "0.0.0":
                    raise ValueError(f"{source} did not return a valid stable IDE version")
                return f"v{match.group(1)}", source
            except Exception as exc:
                last_error = exc
                logger.debug("IDE version source %s unavailable: %s", source, exc)
    raise RuntimeError("All stable IDE version sources are unavailable") from last_error

@app.get("/api/v1/version")
async def get_version_api():
    return {"version": get_app_version()}


@app.get("/api/v1/updates/check")
async def check_ide_updates(
    response: Response,
    _user_id: str = Depends(require_plan_feature("software_updates")),
):
    """Compare the installed CHANGELOG version with the public GitHub main CHANGELOG."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    current_version = get_app_version()
    try:
        latest_version, source = await fetch_latest_ide_version()
        return {
            "current_version": current_version,
            "latest_version": latest_version,
            "update_available": is_newer_version(latest_version, current_version),
            "checked": True,
            "source": source,
        }
    except Exception as exc:
        logger.info("IDE update check unavailable: %s", exc)
        return {
            "current_version": current_version,
            "latest_version": None,
            "update_available": False,
            "checked": False,
        }

register_all(app)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "runtimeforce-app"}
