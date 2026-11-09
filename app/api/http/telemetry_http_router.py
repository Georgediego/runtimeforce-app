"""
HTTP API Router for Telemetry statistics and Model Scores.
"""
import os
import time
from pathlib import Path
from fastapi import APIRouter, Depends
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_telemetry_repo
from app.repository.telemetry_db_repository import TelemetryDBRepository

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

_system_sample = {"cpu": None, "network": None, "at": 0.0}

def _read_proc_stat():
    try:
        values = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        nums = [int(value) for value in values]
        return sum(nums), nums[3] + (nums[4] if len(nums) > 4 else 0)
    except (OSError, ValueError, IndexError):
        return None

def _read_network_bytes():
    try:
        rx = tx = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            if ":" not in line:
                continue
            fields = line.split(":", 1)[1].split()
            if len(fields) >= 9:
                rx += int(fields[0])
                tx += int(fields[8])
        return rx, tx
    except (OSError, ValueError):
        return None

def _read_temperature():
    for sensor in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            raw = float(sensor.read_text().strip())
            value = raw / 1000 if raw > 1000 else raw
            if 0 < value < 130:
                return round(value, 1)
        except (OSError, ValueError):
            continue
    return None

@router.get("/system")
async def get_system_metrics(user_id: str = Depends(require_authenticated_user)):
    """Read host metrics locally; unsupported sensors return null instead of fake values."""
    now = time.monotonic()
    cpu_now, net_now = _read_proc_stat(), _read_network_bytes()
    previous = _system_sample.copy()
    cpu_percent = None
    upload = download = 0
    if cpu_now and previous["cpu"]:
        total_delta = cpu_now[0] - previous["cpu"][0]
        idle_delta = cpu_now[1] - previous["cpu"][1]
        if total_delta > 0:
            cpu_percent = round(max(0, min(100, (1 - idle_delta / total_delta) * 100)), 1)
    if net_now and previous["network"] and previous["at"]:
        elapsed = max(0.1, now - previous["at"])
        download = round(max(0, net_now[0] - previous["network"][0]) / elapsed)
        upload = round(max(0, net_now[1] - previous["network"][1]) / elapsed)
    _system_sample.update({"cpu": cpu_now, "network": net_now, "at": now})
    memory_percent = None
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        if total:
            memory_percent = round((total - available) / total * 100, 1)
    except (OSError, ValueError, IndexError):
        pass
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "temperature_c": _read_temperature(),
        "network_up_bps": upload,
        "network_down_bps": download,
        "sampled_at": time.time(),
    }

@router.get("/scores")
async def get_scores(
    user_id: str = Depends(require_authenticated_user),
    repo: TelemetryDBRepository = Depends(get_telemetry_repo)
):
    return {"scores": repo.get_model_scores(user_id)}

@router.get("/stats")
async def get_stats(
    hours: int = 24,
    user_id: str = Depends(require_authenticated_user),
    repo: TelemetryDBRepository = Depends(get_telemetry_repo)
):
    return {"stats": repo.get_telemetry_stats(hours, user_id)}
