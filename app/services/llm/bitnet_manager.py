import asyncio
import logging
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("runtimeforce.bitnet")

BITNET_CATALOG = {
    "bitnet-b1.58-2b-4t": {
        "name": "BitNet-b1.58-2B-4T",
        "repo": "microsoft/BitNet-b1.58-2B-4T",
        "directory": "BitNet-b1.58-2B-4T",
        "file": "ggml-model-i2_s.gguf",
        "quant": "i2_s",
        "official_repo": True,
    },
    "falcon3-7b-instruct-1.58bit": {
        "name": "Falcon3-7B-Instruct-1.58bit",
        "repo": "tiiuae/Falcon3-7B-Instruct-1.58bit",
        "directory": "Falcon3-7B-Instruct-1.58bit",
        "file": "ggml-model-i2_s.gguf",
        "quant": "i2_s",
        "official_repo": False,
    },
}


class BitNetManager:
    def __init__(self) -> None:
        data_home = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local/share"))
        self.root = data_home / "runtimeforce" / "bitnet"
        self.source = self.root / "source"
        self.models = self.root / "models"
        self.python_env = self.root / "venv"
        self.log_path = self.root / "bitnet.log"
        self.host = "127.0.0.1"
        self.port = int(os.getenv("RUNTIMEFORCE_BITNET_PORT", "8088"))
        self.process: Optional[asyncio.subprocess.Process] = None
        self.active_model: Optional[str] = None
        self.install_state: Dict[str, Any] = {"status": "not_installed", "model": None, "message": ""}
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_model_id(model_id: str) -> str:
        value = str(model_id or "").strip()
        if value.startswith("bitnet/"):
            value = value.split("/", 1)[1]
        value = value.lower()
        aliases = {
            "bitnet-b1.58-2b-4t": "bitnet-b1.58-2b-4t",
            "bitnet-b1.58-2b-4t-gguf": "bitnet-b1.58-2b-4t",
            "falcon3-7b-instruct-1.58bit": "falcon3-7b-instruct-1.58bit",
        }
        return aliases.get(value, value)

    def hardware(self) -> Dict[str, Any]:
        machine = platform.machine().lower()
        flags = set()
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith(("flags", "features")) and ":" in line:
                    flags.update(line.split(":", 1)[1].lower().split())
        except OSError:
            pass
        cores = os.cpu_count() or 1
        return {
            "architecture": machine,
            "cpu_cores": cores,
            "threads": max(1, min(cores, max(1, cores - 1))),
            "avx2": "avx2" in flags,
            "avx": "avx" in flags,
            "neon": "neon" in flags or machine in ("aarch64", "arm64"),
            "kernel": "i2_s",
            "generic_x86_build": machine in ("x86_64", "amd64") and "avx2" not in flags,
        }

    def catalog(self) -> list:
        result = []
        for model_id, item in BITNET_CATALOG.items():
            model_dir = self.models / item["directory"]
            expected = model_dir / item["file"]
            files = [expected] if expected.is_file() else []
            result.append({
                "id": f"bitnet/{model_id}",
                "key": model_id,
                "name": item["name"],
                "repo": item["repo"],
                "installed": bool(files),
                "path": str(files[0]) if files else None,
                "quantization": item["quant"],
            })
        return result

    def _server_binary(self) -> Path:
        candidates = [
            self.source / "build/bin/llama-server",
            self.source / "build/bin/Release/llama-server",
        ]
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise RuntimeError("BitNet server binary is missing. Install a BitNet model first.")

    def _model_file(self, model_id: str) -> Path:
        key = self.normalize_model_id(model_id)
        item = BITNET_CATALOG.get(key)
        if not item:
            raise ValueError("Unsupported BitNet model.")
        model_dir = self.models / item["directory"]
        expected = model_dir / item["file"]
        if expected.is_file():
            return expected
        raise RuntimeError(f"Model weights are not installed: {item['name']}.")

    async def _stop_unlocked(self) -> None:
        proc = self.process
        self.process = None
        self.active_model = None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    async def install_model(self, model_id: str) -> Dict[str, Any]:
        key = self.normalize_model_id(model_id)
        async with self._lock:
            if self.install_state["status"] == "installing":
                raise RuntimeError("A BitNet installation is already running.")
            item = BITNET_CATALOG.get(key)
            if not item:
                raise ValueError("Unsupported BitNet model.")
            await self._stop_unlocked()
            self.root.mkdir(parents=True, exist_ok=True)
            self.models.mkdir(parents=True, exist_ok=True)
            self.install_state = {"status": "installing", "model": key, "message": "Preparing BitNet runtime"}
            try:
                setup = self.source / "setup_env.py"
                if not setup.is_file():
                    if self.source.exists():
                        shutil.rmtree(self.source)
                    clone = await asyncio.create_subprocess_exec(
                        "git", "clone", "--recursive", "--depth", "1",
                        "https://github.com/microsoft/BitNet.git", str(self.source),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    )
                    output, _ = await clone.communicate()
                    if clone.returncode:
                        raise RuntimeError(output.decode(errors="replace")[-3000:])
                if not setup.is_file():
                    raise RuntimeError("The BitNet source checkout does not contain setup_env.py.")
                architecture = self.hardware()["architecture"]
                if architecture not in ("x86_64", "amd64", "aarch64", "arm64"):
                    raise RuntimeError(f"bitnet.cpp does not support this CPU architecture: {architecture}")
                clang_path = shutil.which("clang-18")
                clangxx_path = shutil.which("clang++-18")
                if not clang_path or not clangxx_path:
                    raise RuntimeError("Clang 18 is required. Run /usr/share/runtimeforce/install-bitnet-prerequisites.sh first.")
                cmake_path = shutil.which("cmake")
                if not cmake_path:
                    raise RuntimeError("CMake 3.22 or newer is required. Install the BitNet build prerequisites first.")
                cmake_proc = await asyncio.create_subprocess_exec(cmake_path, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                cmake_output, _ = await cmake_proc.communicate()
                cmake_match = re.search(rb"cmake version (\d+)\.(\d+)", cmake_output, re.IGNORECASE)
                if not cmake_match or (int(cmake_match.group(1)), int(cmake_match.group(2))) < (3, 22):
                    raise RuntimeError("CMake 3.22 or newer is required to build bitnet.cpp.")
                env = os.environ.copy()
                env["CC"] = clang_path
                env["CXX"] = clangxx_path
                env["PATH"] = "/usr/lib/llvm-18/bin:" + env.get("PATH", "")
                hw = self.hardware()
                if hw["generic_x86_build"]:
                    env["CFLAGS"] = (env.get("CFLAGS", "") + " -march=x86-64").strip()
                    env["CXXFLAGS"] = (env.get("CXXFLAGS", "") + " -march=x86-64").strip()
                if not self.python_env.exists():
                    venv_proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "venv", str(self.python_env),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    )
                    venv_output, _ = await venv_proc.communicate()
                    if venv_proc.returncode:
                        raise RuntimeError("Could not create the isolated BitNet Python environment: " + venv_output.decode(errors="replace")[-2000:])
                bitnet_python = self.python_env / "bin/python"
                dependency_marker = self.root / "python-dependencies-installed"
                if not dependency_marker.exists():
                    dependency_proc = await asyncio.create_subprocess_exec(
                        str(bitnet_python), "-m", "pip", "install", "-r", str(self.source / "requirements.txt"),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    )
                    dependency_output, _ = await dependency_proc.communicate()
                    if dependency_proc.returncode:
                        raise RuntimeError("BitNet Python dependency installation failed: " + dependency_output.decode(errors="replace")[-3000:])
                    dependency_marker.write_text("installed", encoding="utf-8")
                args = [
                    str(bitnet_python), str(setup),
                    "--hf-repo", item["repo"],
                    "--model-dir", str(self.models),
                    "--quant-type", item["quant"],
                ]
                self.install_state["message"] = "Downloading weights and compiling the CPU inference server"
                with self.log_path.open("a", encoding="utf-8") as log:
                    proc = await asyncio.create_subprocess_exec(
                        *args, cwd=self.source, env=env,
                        stdout=log, stderr=asyncio.subprocess.STDOUT,
                    )
                    code = await proc.wait()
                if code:
                    tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"BitNet setup failed (exit {code}): {tail}")
                model_file = self._model_file(key)
                self.install_state = {"status": "installed", "model": key, "message": "Weights and runtime are ready", "path": str(model_file)}
                return dict(self.install_state)
            except Exception as exc:
                self.install_state = {"status": "error", "model": key, "message": str(exc)[:4000]}
                raise

    async def ensure_running(self, model_id: str) -> str:
        key = self.normalize_model_id(model_id)
        async with self._lock:
            if self.process and self.process.returncode is None:
                if self.active_model == key and await self._healthy():
                    return f"http://{self.host}:{self.port}/v1"
                await self._stop_unlocked()
            model_file = self._model_file(key)
            binary = self._server_binary()
            hw = self.hardware()
            self.root.mkdir(parents=True, exist_ok=True)
            log = self.log_path.open("a", encoding="utf-8")
            self.process = await asyncio.create_subprocess_exec(
                str(binary), "--model", str(model_file),
                "--host", self.host, "--port", str(self.port),
                "--threads", str(hw["threads"]), "--ctx-size", "8192",
                "--n-predict", "4096", "-ngl", "0",
                "--parallel", "1", "--cont-batching",
                stdout=log, stderr=asyncio.subprocess.STDOUT,
            )
            self.active_model = key
            for _ in range(180):
                if self.process and self.process.returncode is not None:
                    tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                    raise RuntimeError(f"BitNet server exited with code {self.process.returncode}: {tail}")
                if await self._healthy():
                    return f"http://{self.host}:{self.port}/v1"
                await asyncio.sleep(1)
            await self._stop_unlocked()
            raise RuntimeError("BitNet server did not become healthy within 180 seconds.")

    async def _healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(f"http://{self.host}:{self.port}/health")
                if response.status_code == 200:
                    return True
                response = await client.get(f"http://{self.host}:{self.port}/v1/models")
                return response.status_code == 200
        except Exception:
            return False

    async def stop(self) -> Dict[str, Any]:
        async with self._lock:
            await self._stop_unlocked()
        return {"status": "stopped"}

    async def status(self) -> Dict[str, Any]:
        running = bool(self.process and self.process.returncode is None and await self._healthy())
        return {
            "running": running,
            "model": self.active_model,
            "port": self.port,
            "base_url": f"http://{self.host}:{self.port}/v1",
            "installation": dict(self.install_state),
            "hardware": self.hardware(),
            "models": self.catalog(),
        }


bitnet_manager = BitNetManager()
