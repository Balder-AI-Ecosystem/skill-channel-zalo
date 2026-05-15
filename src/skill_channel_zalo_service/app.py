from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def _is_core_repo(candidate: Path) -> bool:
    return candidate.is_dir() and (candidate / "pyproject.toml").is_file() and (candidate / "ecosystem").is_dir()


def _candidate_core_repos() -> list[Path]:
    current_file = Path(__file__).resolve()
    repo_root = current_file.parents[2]
    candidates: list[Path] = []

    configured = str(os.getenv("AUTOBOT_CORE_REPO", "")).strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    for anchor in (current_file.parent, Path.cwd().resolve()):
        candidates.extend([anchor, *anchor.parents])

    parent_dir = repo_root.parent
    if parent_dir.exists():
        candidates.extend(path for path in parent_dir.iterdir() if path.is_dir())

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _default_core_repo() -> Path:
    for candidate in _candidate_core_repos():
        if _is_core_repo(candidate):
            return candidate
    raise RuntimeError("Unable to locate the core repo. Set AUTOBOT_CORE_REPO to a valid core repo path.")


def _ensure_core_repo_on_path() -> Path:
    candidate = _default_core_repo()
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    return candidate


_CORE_REPO = _ensure_core_repo_on_path()

if TYPE_CHECKING:
    from ecosystem.domains.channels.zalo import ZaloChannelManager


class ExecuteRequest(BaseModel):
    capability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    session_id: str | None = None


class ExecuteResponse(BaseModel):
    task_id: str
    status: str
    detail: str
    capability: str
    module_name: str = "skill-channel-zalo"
    artifacts: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    failure_category: str | None = None


app = FastAPI(title="skill-channel-zalo", version="0.1.0")


def _manager(parameters: dict[str, Any] | None = None) -> "ZaloChannelManager":
    from ecosystem.domains.channels.zalo import ZaloChannelManager

    params = dict(parameters or {})
    state_dir_raw = str(params.get("state_dir") or "").strip()
    outputs_dir_raw = str(params.get("outputs_dir") or "").strip()
    state_dir = Path(state_dir_raw) if state_dir_raw else None
    if state_dir is None:
        raise HTTPException(status_code=400, detail="skill-channel-zalo requires state_dir.")
    outputs_dir = Path(outputs_dir_raw) if outputs_dir_raw else None
    return ZaloChannelManager(state_dir=state_dir, outputs_dir=outputs_dir)


def _manifest() -> dict[str, Any]:
    return {
        "name": "skill-channel-zalo",
        "version": "0.1.0",
        "mode": "service",
        "entrypoint": "src.skill_channel_zalo_service.app:app",
        "core_api": ">=1.0,<2.0",
        "service": {
            "base_url": "http://127.0.0.1:8422",
            "execute_path": "/execute",
            "health_path": "/health",
        },
        "capabilities": [
            "channel_gateway.zalo_status",
            "channel_gateway.zalo_webhook",
        ],
    }


def _task_result(
    *,
    task_id: str,
    capability: str,
    status: str,
    detail: str,
    artifacts: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    failure_category: str | None = None,
) -> ExecuteResponse:
    return ExecuteResponse(
        task_id=task_id,
        status=status,
        detail=detail,
        capability=capability,
        artifacts=dict(artifacts or {}),
        evidence=dict(evidence or {}),
        next_actions=list(next_actions or []),
        failure_category=failure_category,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    settings = _manager({"state_dir": str(_CORE_REPO / "runtime" / "state")})
    snapshot = settings.snapshot()
    snapshot["service"] = _manifest()["service"]
    return snapshot


@app.get("/manifest")
def manifest() -> dict[str, Any]:
    return _manifest()


@app.post("/execute")
async def execute(request: ExecuteRequest) -> dict[str, Any]:
    task_id = str(request.task_id or f"skill-channel-zalo-{uuid4().hex}")
    capability = str(request.capability or "").strip()
    parameters = dict(request.parameters or {})
    manager = _manager(parameters)

    if capability == "channel_gateway.zalo_status":
        payload = manager.snapshot()
        return _task_result(
            task_id=task_id,
            capability=capability,
            status="completed",
            detail="Zalo gateway snapshot ready.",
            artifacts={"result": payload},
            evidence={"service_mode": True},
        ).model_dump()

    if capability == "channel_gateway.zalo_webhook":
        from ecosystem.runtime.orchestrator import run_turn

        payload = parameters.get("payload") if isinstance(parameters.get("payload"), dict) else None
        if payload is None:
            raise HTTPException(status_code=400, detail="channel_gateway.zalo_webhook requires payload.")
        provided_secret = str(parameters.get("provided_secret") or "").strip() or None
        if not manager.verify_webhook_secret(provided_secret):
            result = {
                "status": "blocked",
                "detail": "Zalo webhook secret mismatch.",
                "failure_category": "permission_denied",
            }
            return _task_result(
                task_id=task_id,
                capability=capability,
                status="blocked",
                detail=result["detail"],
                artifacts={"result": result},
                evidence={"service_mode": True},
                failure_category="permission_denied",
            ).model_dump()
        webhook_result = await manager.handle_webhook(payload, turn_runner=run_turn)
        return _task_result(
            task_id=task_id,
            capability=capability,
            status=str(webhook_result.get("status") or "failed"),
            detail=str(webhook_result.get("detail") or "Zalo webhook processed."),
            artifacts={"result": webhook_result},
            evidence={"service_mode": True, "session_id": request.session_id},
            next_actions=list(webhook_result.get("next_actions") or []),
            failure_category=str(webhook_result.get("failure_category") or "").strip() or None,
        ).model_dump()

    raise HTTPException(status_code=404, detail=f"Unsupported capability: {capability}")
