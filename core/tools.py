"""
Mock DevOps tools. Each returns a realistic response dict.
These are intentionally deterministic — no side effects in dev mode.
"""
import random
from datetime import datetime


def deploy_service(service: str, version: str, environment: str = "staging") -> dict:
    success = random.random() > 0.15  # 85% success rate to demo retry logic
    return {
        "tool": "deploy_service",
        "service": service,
        "version": version,
        "environment": environment,
        "success": success,
        "message": f"Deployed {service}@{version} to {environment}" if success
                   else f"Deploy failed: health check timeout for {service}",
        "timestamp": datetime.utcnow().isoformat(),
    }


def check_service_health(service: str) -> dict:
    statuses = ["healthy", "healthy", "healthy", "degraded", "unhealthy"]
    status = random.choice(statuses)
    return {
        "tool": "check_service_health",
        "service": service,
        "status": status,
        "latency_ms": random.randint(12, 950),
        "timestamp": datetime.utcnow().isoformat(),
    }


def rollback_service(service: str, target_version: str) -> dict:
    return {
        "tool": "rollback_service",
        "service": service,
        "target_version": target_version,
        "success": True,
        "message": f"Rolled back {service} to {target_version}",
        "timestamp": datetime.utcnow().isoformat(),
    }


def scale_service(service: str, replicas: int) -> dict:
    return {
        "tool": "scale_service",
        "service": service,
        "replicas": replicas,
        "success": True,
        "message": f"Scaled {service} to {replicas} replicas",
        "timestamp": datetime.utcnow().isoformat(),
    }


def fetch_logs(service: str, lines: int = 50) -> dict:
    sample_logs = [
        f"INFO  [{service}] Request handled in 42ms",
        f"WARN  [{service}] DB connection pool at 80%",
        f"INFO  [{service}] Cache hit ratio: 94%",
        f"ERROR [{service}] Upstream timeout — retrying",
    ]
    return {
        "tool": "fetch_logs",
        "service": service,
        "lines": min(lines, len(sample_logs)),
        "entries": sample_logs[:lines],
        "timestamp": datetime.utcnow().isoformat(),
    }


TOOL_MAP = {
    "deploy_service": deploy_service,
    "check_service_health": check_service_health,
    "rollback_service": rollback_service,
    "scale_service": scale_service,
    "fetch_logs": fetch_logs,
}


def run_tool(name: str, params: dict) -> dict:
    fn = TOOL_MAP.get(name)
    if not fn:
        return {"tool": name, "success": False, "message": f"Unknown tool: {name}"}
    try:
        return fn(**params)
    except TypeError as e:
        return {"tool": name, "success": False, "message": f"Bad params: {e}"}
