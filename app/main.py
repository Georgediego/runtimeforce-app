"""
RuntimeForce IDE — FastAPI main application entry point with LiteLLM & HuggingFace Log Suppression.
"""
import os
import socket
import argparse
import logging
from pathlib import Path
from contextlib import asynccontextmanager
import uvicorn

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
    version="2.0.0",
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

register_all(app)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "runtimeforce-app"}


def find_free_port(start_port: int = 8000, max_attempts: int = 20, host: str = "127.0.0.1") -> int:
    port = start_port
    for _ in range(max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                if port != start_port:
                    print(f"Port {start_port} is busy. RuntimeForce UI/API is running on http://{host}:{port}")
                return port
            except (socket.error, OSError):
                port += 1
    raise RuntimeError(f"Could not find a free port after {max_attempts} attempts starting from {start_port}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RuntimeForce IDE")
    parser.add_argument("-p", "--port", type=int, help="Port to run the application on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    env_port = os.getenv("PORT")
    initial_port = args.port if args.port is not None else (int(env_port) if env_port else 8000)

    final_port = find_free_port(start_port=initial_port, host=args.host)

    uvicorn.run("app.main:app", host=args.host, port=final_port, reload=True)
