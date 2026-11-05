"""
RuntimeForce IDE — FastAPI main application entry point with LiteLLM & HuggingFace Log Suppression.
"""
import os
import re
import base64
import logging
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
import subprocess
import sys

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from fastapi import FastAPI, Request, Response, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import httpx
from fastapi.responses import HTMLResponse

from app.container import container
from app.api import register_all
from app.core.version_utils import is_newer_version

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
    version="1.0.6",
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

# Read the stable IDE version from the public GitHub main changelog.
IDE_CHANGELOG_URL = "https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/CHANGELOG.md"
IDE_CHANGELOG_API_URL = "https://api.github.com/repos/Georgediego/runtimeforce-app/contents/CHANGELOG.md?ref=main"

def parse_stable_ide_version(changelog: str) -> str:
    match = re.search(
        r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?",
        changelog,
        re.MULTILINE,
    )
    if not match or match.group(1) == "0.0.0":
        raise RuntimeError("GitHub main changelog does not contain a valid stable IDE version")
    return f"v{match.group(1)}"

async def fetch_latest_ide_version():
    """Read GitHub main, trying raw content first and the GitHub API as fallback."""
    headers = {"Cache-Control": "no-cache", "Accept": "application/vnd.github+json"}
    errors = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for url, source in (
            (IDE_CHANGELOG_URL, "github-main-changelog"),
            (IDE_CHANGELOG_API_URL, "github-api"),
        ):
            try:
                remote = await client.get(url, headers=headers)
                remote.raise_for_status()
                if source == "github-api":
                    payload = remote.json()
                    content = base64.b64decode(payload["content"]).decode("utf-8")
                else:
                    content = remote.text
                return parse_stable_ide_version(content), source
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Unable to read GitHub main CHANGELOG; " + " | ".join(errors))

@app.get("/api/v1/version")
async def get_version_api():
    return {"version": get_app_version()}


@app.get("/api/v1/updates/check")
async def check_ide_updates(
    response: Response,
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
            "installed_newer": is_newer_version(current_version, latest_version),
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


_update_state = {"status": "idle", "message": ""}


def _apply_ide_update():
    """Safely fast-forward the clean IDE checkout to stable main and restart Uvicorn."""
    global _update_state
    root = BASE_DIR.parent.resolve()

    def run_git(*args, timeout=60):
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    try:
        _update_state = {"status": "updating", "message": "Checking the local installation..."}
        top_level = run_git("rev-parse", "--show-toplevel")
        if top_level.returncode != 0 or Path(top_level.stdout.strip()).resolve() != root:
            raise RuntimeError("The IDE installation is not a Git repository.")

        branch = run_git("branch", "--show-current")
        if branch.returncode != 0 or branch.stdout.strip() != "main":
            raise RuntimeError("Automatic updates require the stable main branch.")

        remote = run_git("remote", "get-url", "origin")
        allowed_remotes = {
            "https://github.com/Georgediego/runtimeforce-app.git",
            "https://github.com/Georgediego/runtimeforce-app",
            "git@github.com:Georgediego/runtimeforce-app.git",
        }
        if remote.returncode != 0 or remote.stdout.strip().rstrip("/") not in allowed_remotes:
            raise RuntimeError("The configured Git origin is not the official RuntimeForce IDE repository.")

        changes = run_git("status", "--porcelain")
        if changes.returncode != 0 or changes.stdout.strip():
            raise RuntimeError("Local changes detected. Commit or stash them before updating.")

        _update_state = {"status": "updating", "message": "Downloading the latest stable release..."}
        fetched = run_git("fetch", "origin", "main", "--quiet", timeout=180)
        if fetched.returncode != 0:
            raise RuntimeError(fetched.stderr.strip() or "Unable to fetch the latest release.")

        ancestry = run_git("merge-base", "--is-ancestor", "HEAD", "origin/main")
        if ancestry.returncode != 0:
            raise RuntimeError("The local branch cannot be updated with a safe fast-forward.")

        merged = run_git("merge", "--ff-only", "origin/main")
        if merged.returncode != 0:
            raise RuntimeError(merged.stderr.strip() or "Unable to apply the stable release.")

        _update_state = {"status": "installing", "message": "Installing application dependencies..."}
        installed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if installed.returncode != 0:
            raise RuntimeError((installed.stderr or installed.stdout).strip()[-1200:] or "Dependency installation failed.")

        if "uvicorn" not in Path(sys.argv[0]).as_posix().lower():
            raise RuntimeError("The code was updated, but automatic restart is unavailable for this launch method.")

        _update_state = {"status": "restarting", "message": "Restarting RuntimeForce IDE..."}
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except Exception as exc:
        logger.exception("IDE automatic update failed")
        _update_state = {"status": "error", "message": str(exc)[:1200]}


@app.post("/api/v1/updates/apply")
async def apply_ide_update(request: Request, background_tasks: BackgroundTasks):
    host = request.headers.get("host", "").split(":")[0].lower()
    origin = request.headers.get("origin", "")
    if host not in {"localhost", "127.0.0.1"} or origin not in {
        f"http://{host}:8000",
        f"https://{host}:8000",
    }:
        raise HTTPException(status_code=403, detail="Update requests are allowed only from the local IDE.")

    if _update_state["status"] in {"updating", "installing", "restarting"}:
        return {"accepted": True, "status": _update_state["status"]}

    background_tasks.add_task(_apply_ide_update)
    return {"accepted": True, "status": "updating"}


@app.get("/api/v1/updates/status")
async def get_ide_update_status():
    return dict(_update_state)


register_all(app)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "runtimeforce-app"}
