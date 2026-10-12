"""Opt-in inert artifact capture after the existing benchmark wake has settled.

The TS backup/artifact owner verifies source stability and materialized bytes.
Python adapts the owned wake, source admission and explicit operator file list;
it never restores claims, starts a model or certifies a complete research point.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path, PurePosixPath
from typing import Any

from loopx.control_plane.effect_runtime import effect_runtime_result
from loopx.control_plane.quota.settlement import read_heartbeat_settlement


def normalize_checkpoint_request_path(value: str) -> str:
    """An explicit guest path; no ambient host variable enables capture."""
    if (not isinstance(value, str) or not value or
            not PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value or
            ".." in PurePosixPath(value).parts):
        raise ValueError("checkpoint_request_path must be a normalized absolute guest file path")
    return value


def capture_after_wake(env: dict[str, str], receipt: dict[str, Any]) -> None:
    request_path = env.get("LOOPX_CHECKPOINT_REQUEST")
    if not request_path:
        return  # Feature-off path performs no additional read or write.
    receipt["checkpoint"] = {"captured": False, "research_point_qualified": False}
    if (not receipt.get("ok") or receipt.get("stage") != "execute" or
            receipt.get("mode") not in {"heartbeat", "turn"} or receipt.get("budget_exhausted")):
        receipt["checkpoint"]["reason"] = "wake_not_successful_work"
        return
    started = time.monotonic()
    try:
        phase_deadline = env.get("LOOPX_PHASE_DEADLINE_EPOCH")
        deadline = time.time() + 30
        if phase_deadline is not None:
            original_deadline = float(phase_deadline)
            if not math.isfinite(original_deadline):
                raise ValueError("checkpoint requires a finite original phase deadline")
            deadline = min(deadline, original_deadline)
        if deadline <= time.time():
            receipt["checkpoint"]["reason"] = "capture_window_closed"
            return
        raw = Path(request_path).read_bytes()
        request = json.loads(raw)
        if not isinstance(request, dict) or set(request) != {"destination", "components", "point_metadata"}:
            raise ValueError("checkpoint request requires destination, components and point_metadata")
        # This is a private evidence artifact below the runner's log owner.
        destination = Path(request["destination"])
        root = Path(env["LOOPX_WAKE_LOG_DIR"]).parent / "checkpoints"
        if not destination.is_absolute() or destination != destination.resolve() or destination.parent != root:
            raise ValueError("checkpoint destination must be a normalized direct child of this trial's checkpoints directory")
        if destination.exists():
            receipt["checkpoint"]["reason"] = "destination_already_present_no_replay"
            return
        observed = read_heartbeat_settlement(
            Path(env["LOOPX_RUNTIME_ROOT"]), goal_id=env["LOOPX_GOAL_ID"],
            agent_id=env["LOOPX_AGENT_ID"], todo_id=None,
            turn_instance_id=receipt["turn_id"], resolve_original_binding=True,
            registry_path=Path(env["LOOPX_REGISTRY"]),
        )
        if observed is None or (observed.progress or {}).get("state") != "settled":
            receipt["checkpoint"]["reason"] = "owned_turn_not_settled"
            return
        identity = observed.identity.value
        if identity is None:
            raise ValueError("checkpoint settlement identity is unavailable")
        # Only this returned typed owner decision admits the capture boundary.
        # Point metadata remains evidence, never authority or scientific validity.
        metadata = {
            "operator_metadata": request["point_metadata"],
            "wake_turn_id": receipt["turn_id"],
            "settlement_effect_id": identity.effect_id,
            "session": receipt.get("session"),
            "request_sha256": hashlib.sha256(raw).hexdigest(),
        }
        probe = effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "probe", "components": request["components"],
            "deadline_epoch_ms": deadline * 1000,
        }, timeout=max(.1, deadline - time.time()), retry_safe=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        captured = effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "capture", "destination": str(destination),
            "components": request["components"], "point_metadata": metadata,
            "expected_source_sha256": probe["source_sha256"],
            "deadline_epoch_ms": deadline * 1000,
        }, timeout=max(.1, deadline - time.time()), retry_safe=False)
        receipt["checkpoint"] = {"captured": True, "destination": str(destination), **captured}
    except Exception as error:
        # Capture failure is explicit but cannot rewrite an already settled work
        # outcome or replay its model/evaluation. Keep the source trial running.
        receipt["checkpoint"].update(reason="capture_failed", error_kind=type(error).__name__, error=str(error)[:500])
    finally:
        receipt["checkpoint"]["elapsed_seconds"] = time.monotonic() - started
