"""Opt-in inert artifact capture after the existing benchmark wake has settled.

The TS backup/artifact owner verifies source stability and materialized bytes.
Python adapts the owned wake, source admission and explicit operator file list;
it never restores claims, starts a model or certifies a complete research point.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
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


def read_checkpoint_request(path: str) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    return parse_checkpoint_request(raw), raw


def parse_checkpoint_request(raw: bytes) -> dict[str, Any]:
    """Validate the same explicit declaration before staging and before capture."""
    request = json.loads(raw)
    if (not isinstance(request, dict) or
            set(request) - {"destination", "components", "point_metadata", "native_session", "evaluation_opportunity", "trigger"} or
            not {"destination", "components", "point_metadata"}.issubset(request)):
        raise ValueError("checkpoint request requires destination, components and point_metadata")
    if "native_session" in request and type(request["native_session"]) is not bool:
        raise ValueError("checkpoint native_session must be an explicit boolean")
    if "evaluation_opportunity" in request and type(request["evaluation_opportunity"]) is not bool:
        raise ValueError("checkpoint evaluation_opportunity must be an explicit boolean")
    if "trigger" in request and request["trigger"] != "fresh_replan":
        raise ValueError("checkpoint trigger must be fresh_replan or omitted")
    if not isinstance(request["components"], list) or not request["components"]:
        raise ValueError("checkpoint requires explicit components")
    if not isinstance(request["point_metadata"], dict):
        raise ValueError("checkpoint point_metadata must be an object")
    return request


def capture_before_replan(env: dict[str, str], receipt: dict[str, Any], body: str) -> str:
    """Preload the original guard once, then capture before invoking the model.

    The typed owner selects only an admitted replan identity. The prior wake's
    existing settlement owner still qualifies the source boundary. A missed
    point is explicit and cannot be replaced by an after-decision capture.
    """
    path = env.get("LOOPX_CHECKPOINT_REQUEST")
    if not path:
        return body
    request, raw = read_checkpoint_request(path)
    if request.get("trigger") != "fresh_replan":
        return body
    if receipt.get("mode") != "heartbeat" or receipt.get("stage") != "execute":
        raise ValueError("fresh_replan checkpoint trigger requires a heartbeat execute wake")
    started = time.monotonic()
    guard_path = Path(env["LOOPX_WAKE_LOG_DIR"]) / receipt["turn_id"] / "checkpoint-start-guard.json"
    command = [env["LOOPX_CLI"], "--format", "json", "--registry", env["LOOPX_REGISTRY"],
               "--runtime-root", env["LOOPX_RUNTIME_ROOT"], "quota", "should-run",
               "--goal-id", env["LOOPX_GOAL_ID"], "--agent-id", env["LOOPX_AGENT_ID"],
               "--runtime-profile", "generic_cli", "--turn-instance-id", receipt["turn_id"],
               "--available-capability", "shell", "--available-capability", "filesystem_write"]
    guard_run = subprocess.run(command, cwd=env["LOOPX_PROJECT"], env=env, capture_output=True,
                               text=True, timeout=120, check=True)
    guard = json.loads(guard_run.stdout)
    if not isinstance(guard, dict) or guard.get("ok") is not True:
        raise ValueError("checkpoint requires a successful original quota guard")
    guard_path.write_text(guard_run.stdout, encoding="utf-8")
    guard_path.chmod(0o600)
    preloaded_body = (f"Host checkpoint preflight has already executed this wake's original quota guard once. "
        f"Read the complete packet at {guard_path} before work, then follow its interaction_contract. "
        "Do not repeat the initial guard below; use its selection or recovery command when required.\n\n" + body)
    receipt["checkpoint"] = {"captured": False, "research_point_qualified": False, "phase": "before_replan"}
    try:
        intent = effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "select_replan", "quota": guard, "goal_id": env["LOOPX_GOAL_ID"],
            "agent_id": env["LOOPX_AGENT_ID"], "turn_instance_id": receipt["turn_id"],
        })
        if not intent["capture"]:
            receipt["checkpoint"]["reason"] = intent["reason"]
        else:
            root = Path(env["LOOPX_WAKE_LOG_DIR"]).parent / "checkpoints"
            requested_root = Path(request["destination"])
            if not requested_root.is_absolute() or requested_root != requested_root.resolve() or requested_root != root:
                raise ValueError("fresh_replan destination must be this trial's checkpoints directory")
            destination = root / intent["obligation_id"]
            if destination.parent != root or destination != destination.resolve():
                raise ValueError("replan checkpoint identity must select a direct child")
            if destination.exists():
                # Readback of the first point, never overwrite it with later work.
                manifest = json.loads((destination / "checkpoint.json").read_text())
                metadata = manifest["point_metadata"]
                if (metadata["request_sha256"] != hashlib.sha256(raw).hexdigest() or
                        metadata["operator_metadata"]["replan"]["obligation_id"] != intent["obligation_id"]):
                    raise ValueError("existing replan point has a different declaration")
                verified = effect_runtime_result("runtime.checkpoint_artifacts", {
                    "action": "verify", "root": str(destination), "expected_sha256": manifest["sha256"],
                })
                receipt["checkpoint"].update(reason="replan_already_captured", destination=str(destination), **verified)
            else:
                # A failed first capture is a missed point. Once its model is
                # allowed to decide/work, a retry must not relabel later state
                # as the original pre-decision checkpoint.
                attempts = root / ".replan-attempts"
                attempts.mkdir(parents=True, exist_ok=True, mode=0o700)
                if attempts != attempts.resolve():
                    raise ValueError("replan attempt directory must not contain symlinks")
                attempt_path = attempts / (intent["obligation_id"] + ".json")
                attempt = {"obligation_id": intent["obligation_id"], "turn_id": receipt["turn_id"],
                           "request_sha256": hashlib.sha256(raw).hexdigest()}
                try:
                    with attempt_path.open("x", encoding="utf-8") as marker:
                        marker.write(json.dumps(attempt))
                    attempt_path.chmod(0o600)
                except FileExistsError:
                    if attempt_path.is_symlink():
                        raise ValueError("replan attempt must not be a symlink")
                    prior_attempt = json.loads(attempt_path.read_text())
                    if (prior_attempt["obligation_id"] != attempt["obligation_id"] or
                            prior_attempt["request_sha256"] != attempt["request_sha256"]):
                        raise ValueError("existing replan attempt has a different declaration")
                    receipt["checkpoint"]["reason"] = "pre_decision_capture_already_attempted"
                    return preloaded_body
                prior_paths = sorted(Path(env["LOOPX_WAKE_LOG_DIR"]).glob("wake-*/receipt.json"))
                prior_paths = [p for p in prior_paths if p.parent.name != receipt["turn_id"]]
                if not prior_paths:
                    raise ValueError("replan capture has no completed prior Host wake")
                prior = json.loads(prior_paths[-1].read_text())
                if prior.get("stage") != "execute" or prior.get("mode") != "heartbeat" or not prior.get("ok"):
                    raise ValueError("replan capture requires the latest successful work wake")
                effective_request = {**request, "destination": str(destination),
                    "point_metadata": {**request["point_metadata"], "replan": intent,
                                       "capture_order": "before_model_replan_decision"}}
                effective_request.pop("trigger")
                capture_after_wake(env, prior, supplied_request=(effective_request, raw))
                receipt["checkpoint"].update(prior["checkpoint"], phase="before_replan")
                receipt["checkpoint"]["source_turn_id"] = prior["turn_id"]
    except Exception as error:
        receipt["checkpoint"].update(reason="capture_failed", error_kind=type(error).__name__, error=str(error)[:500])
    finally:
        receipt["checkpoint"]["elapsed_seconds"] = time.monotonic() - started
    # The model consumes exactly the owner's original decision and keeps its
    # selection, settlement, required-read and recovery instructions intact.
    return preloaded_body


def capture_after_wake(env: dict[str, str], receipt: dict[str, Any], *,
                       supplied_request: tuple[dict[str, Any], bytes] | None = None) -> None:
    request_path = env.get("LOOPX_CHECKPOINT_REQUEST")
    if not request_path:
        return  # Feature-off path performs no additional read or write.
    if supplied_request is None and (receipt.get("checkpoint") or {}).get("phase") == "before_replan":
        return  # The after-wake hook cannot replace the pre-decision point.
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
        if supplied_request is None:
            request, raw = read_checkpoint_request(request_path)
        else:
            request, raw = supplied_request
        if request.get("trigger") == "fresh_replan":
            receipt["checkpoint"]["reason"] = "pre_replan_hook_required"
            return
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
        components = request["components"]
        if request.get("evaluation_opportunity"):
            from .sforge_checkpoint import capture_opportunity

            opportunity = capture_opportunity(env, timeout=max(.1, deadline - time.time()))
            evidence = Path(env["LOOPX_WAKE_LOG_DIR"]) / receipt["turn_id"] / "checkpoint-opportunity.json"
            evidence.write_text(json.dumps(opportunity), encoding="utf-8")
            evidence.chmod(0o600)
            components = [*components, {"id": "evaluation_opportunity", "source_path": str(evidence)}]
        if request.get("native_session"):
            from .native_checkpoint import native_session_checkpoint

            session = receipt.get("session") or {}
            native = native_session_checkpoint(env, session.get("session_id", ""),
                                               timeout=max(.1, deadline - time.time()))
            components = [*components, *native["components"]]
            metadata["native_session"] = native["metadata"]
        probe = effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "probe", "components": components,
            "deadline_epoch_ms": deadline * 1000,
        }, timeout=max(.1, deadline - time.time()), retry_safe=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        captured = effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "capture", "destination": str(destination),
            "components": components, "point_metadata": metadata,
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
