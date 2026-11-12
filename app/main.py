"""
RuntimeForce IDE — FastAPI main application entry point with LiteLLM & HuggingFace Log Suppression.
"""
import os
import re
import base64
import logging
import time
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
import subprocess
import sys
import shutil
import stat
import tempfile
import zipfile
from pathlib import PurePosixPath

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

LOG_LEVEL_NAME = os.getenv("RF_LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Uvicorn may configure handlers before importing this module; set the root
# logger level explicitly so RF_LOG_LEVEL still takes effect in that case.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger("runtimeforce.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 RuntimeForce IDE starting... (log level: %s)", LOG_LEVEL_NAME)
    yield
    logger.info("🛑 RuntimeForce IDE shutting down...")
    try:
        await container.command_approval_service.close_all()
    except Exception as e:
        logger.warning(f"Command approval cleanup failed: {e}")
    try:
        await container.ssh_pool.close_all()
    except Exception as e:
        logger.warning(f"SSH cleanup failed: {e}")

app = FastAPI(
    title="RuntimeForce IDE",
    version="1.1.17",
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

@app.middleware("http")
async def diagnostics_http_middleware(request: Request, call_next):
    """Log API request lifecycle without exposing request bodies, prompts, or credentials."""
    started = time.perf_counter()
    path = request.url.path
    is_api = path.startswith("/api/")
    if is_api:
        logger.debug("[HTTP] START %s %s", request.method, path)
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("[HTTP] EXCEPTION %s %s after %.1fms", request.method, path, elapsed_ms)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    if is_api or response.status_code >= 400:
        logger.info("[HTTP] %s %s -> %s (%.1fms)", request.method, path, response.status_code, elapsed_ms)
    return response

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
    """Install the latest public stable ZIP without relying on Git or user credentials."""
    global _update_state
    root = BASE_DIR.parent.resolve()
    archive_url = "https://codeload.github.com/Georgediego/runtimeforce-app/zip/refs/heads/main"
    max_archive_bytes = 200 * 1024 * 1024
    protected_dirs = {
        ".git", "venv", ".venv", "__pycache__", ".pytest_cache",
        "data", "runtime", "workspaces", "logs", "backups",
    }

    def is_protected(relative_path: PurePosixPath) -> bool:
        parts = relative_path.parts
        if not parts or any(part in protected_dirs for part in parts):
            return True
        name = parts[-1].lower()
        return name == ".env" or name.startswith(".env.") or name.endswith((".db", ".sqlite", ".sqlite3", ".log"))

    temp_root = None
    backups = {}
    created_files = []
    try:
        _update_state = {"status": "updating", "message": "Downloading the latest stable release..."}
        temp_root = Path(tempfile.mkdtemp(prefix="runtimeforce-update-"))
        archive_path = temp_root / "release.zip"
        with httpx.Client(timeout=httpx.Timeout(30.0, read=180.0), follow_redirects=True) as client:
            with client.stream("GET", archive_url, headers={"Accept": "application/zip"}) as response:
                response.raise_for_status()
                total = 0
                with archive_path.open("wb") as archive_file:
                    for chunk in response.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > max_archive_bytes:
                            raise RuntimeError("The release archive exceeds the permitted download size.")
                        archive_file.write(chunk)

        _update_state = {"status": "updating", "message": "Validating the stable release..."}
        staging = temp_root / "staging"
        staging.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members:
                raise RuntimeError("The downloaded release archive is empty.")
            roots = {PurePosixPath(item.filename).parts[0] for item in members if PurePosixPath(item.filename).parts}
            if len(roots) != 1:
                raise RuntimeError("The release archive has an unexpected directory structure.")
            archive_root = next(iter(roots))
            extracted_count = 0
            for item in members:
                raw_path = PurePosixPath(item.filename)
                if raw_path.is_absolute() or ".." in raw_path.parts or not raw_path.parts:
                    raise RuntimeError("The release archive contains an unsafe file path.")
                if raw_path.parts[0] != archive_root:
                    raise RuntimeError("The release archive contains an unexpected file.")
                relative = PurePosixPath(*raw_path.parts[1:])
                if not relative.parts or is_protected(relative):
                    continue
                mode = (item.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise RuntimeError("The release archive contains an unsupported symbolic link.")
                destination = staging.joinpath(*relative.parts)
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                archive_mode = (item.external_attr >> 16) & 0o777
                if archive_mode:
                    os.chmod(destination, archive_mode)
                extracted_count += 1

        staged_changelog = staging / "CHANGELOG.md"
        if not staged_changelog.is_file():
            raise RuntimeError("The release archive does not contain CHANGELOG.md.")
        staged_version = parse_stable_ide_version(staged_changelog.read_text(encoding="utf-8"))
        current_version = get_app_version()
        if not is_newer_version(staged_version, current_version):
            raise RuntimeError(f"No newer stable release is available (installed {current_version}, latest {staged_version}).")
        if extracted_count == 0:
            raise RuntimeError("The release archive contains no installable application files.")

        _update_state = {"status": "installing", "message": f"Installing RuntimeForce {staged_version}..."}
        backup_root = temp_root / "backup"
        for source in staging.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(staging)
            destination = root / relative
            if not destination.resolve().is_relative_to(root):
                raise RuntimeError("An update file resolves outside the application directory.")
            if destination.exists():
                if not destination.is_file():
                    raise RuntimeError(f"Cannot safely replace a non-file application path: {relative}")
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
                backups[destination] = backup
            else:
                created_files.append(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        installed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=root, capture_output=True, text=True, timeout=600, check=False,
        )
        if installed.returncode != 0:
            logger.error("Dependency installation failed: %s", (installed.stderr or installed.stdout).strip()[-3000:])
            raise RuntimeError("Dependency installation failed. The application files will be restored; check the IDE logs.")

        _update_state = {"status": "restarting", "message": f"Restarting RuntimeForce {staged_version}..."}
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root = None
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except Exception as exc:
        for destination in reversed(created_files):
            try:
                destination.unlink(missing_ok=True)
            except Exception:
                logger.exception("Could not remove partially installed file: %s", destination)
        for destination, backup in backups.items():
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, destination)
            except Exception:
                logger.exception("Could not restore application file: %s", destination)
        logger.exception("IDE automatic update failed")
        _update_state = {"status": "error", "message": str(exc)[:1200]}
    finally:
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)

@app.post("/api/v1/updates/apply")
async def apply_ide_update(request: Request, background_tasks: BackgroundTasks):
    global _update_state
    host = request.headers.get("host", "").split(":")[0].lower()
    origin = request.headers.get("origin", "")
    if host not in {"localhost", "127.0.0.1"} or origin not in {
        f"http://{host}:8000",
        f"https://{host}:8000",
    }:
        raise HTTPException(status_code=403, detail="Update requests are allowed only from the local IDE.")

    if _update_state["status"] in {"updating", "installing", "restarting"}:
        return {"accepted": True, "status": _update_state["status"]}

    _update_state = {"status": "updating", "message": "Starting the update..."}
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
