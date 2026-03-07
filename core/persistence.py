import json
import os
import redis
from core.state import AgentState
from dotenv import load_dotenv

load_dotenv()

_r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)

TTL = 60 * 60 * 24  # 24 hours


def save_state(state: AgentState) -> None:
    key = f"run:{state.run_id}"
    _r.setex(key, TTL, state.model_dump_json())
    # Keep a sorted index of run IDs by timestamp for listing
    _r.zadd("runs:index", {state.run_id: _timestamp_score(state.started_at)})


def load_state(run_id: str) -> AgentState | None:
    raw = _r.get(f"run:{run_id}")
    if not raw:
        return None
    return AgentState.model_validate_json(raw)


def list_runs(limit: int = 50) -> list[str]:
    """Return recent run IDs, newest first."""
    return _r.zrevrange("runs:index", 0, limit - 1)


def delete_run(run_id: str) -> None:
    _r.delete(f"run:{run_id}")
    _r.zrem("runs:index", run_id)


def _timestamp_score(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0
