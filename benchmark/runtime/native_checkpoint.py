"""Codex-specific checkpoint inventory and native history readback.

This transport adapter does not decide research validity or adopt authority.
The artifact owner seals its declared native-store members after the Host exits.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from loopx.capabilities.benchmark_toolkit.native_codex_goal import StdioNativeGoalTransport


def _complete_history(request, session_id: str) -> list[dict[str, Any]]:
    turns = []
    cursor = None
    seen = set()
    while True:
        page = request("thread/turns/list", {
            "threadId": session_id, "sortDirection": "asc", "itemsView": "full", "limit": 100,
            **({"cursor": cursor} if cursor else {}),
        })
        if not isinstance(page.get("data"), list):
            raise ValueError("native checkpoint history page is unavailable")
        turns.extend(page["data"])
        cursor = page.get("nextCursor")
        if not cursor:
            break
        if cursor in seen:
            raise ValueError("native checkpoint repeated history cursor")
        seen.add(cursor)
    if not turns or any(t.get("status") not in {"completed", "failed", "interrupted"} or not t.get("id") for t in turns):
        raise ValueError("native checkpoint requires complete retained turns")
    if turns[-1].get("status") != "completed":
        raise ValueError("native checkpoint requires a completed final cursor")
    ids = [t["id"] for t in turns]
    if len(set(ids)) != len(ids):
        raise ValueError("native checkpoint history contains duplicate turns")
    return turns


def native_session_checkpoint(env: dict[str, str], session_id: str, *, timeout: float) -> dict[str, Any]:
    home = Path(env["CODEX_HOME"])
    if not session_id or timeout <= 0:
        raise ValueError("native checkpoint requires a session and an open capture window")
    deadline = time.monotonic() + timeout
    version = subprocess.check_output([env["CODEX_BIN"], "--version"], env=env, text=True,
                                      timeout=timeout).strip()
    # Native storage is opaque. Retain both rollout and paginated/index stores;
    # auth, logs, memories and the symlinked skill installation are not members.
    with StdioNativeGoalTransport.spawn(
        [env["CODEX_BIN"], "-c", "features.goals=false", "app-server", "--listen", "stdio://"],
        cwd=env["LOOPX_PROJECT"], env=env, stderr=subprocess.DEVNULL,
        response_timeout_sec=timeout,
    ) as transport:
        def request(method, params):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native checkpoint window closed")
            transport.response_timeout_sec = remaining
            return transport.request(method, params)
        request("initialize", {"clientInfo": {"name": "loopx_checkpoint", "version": "0.1.0"},
                                          "capabilities": {"experimentalApi": True}})
        transport.notify("initialized", {})
        readback = request("thread/read", {"threadId": session_id, "includeTurns": False})
        if readback.get("thread", {}).get("id") != session_id:
            raise ValueError("native checkpoint session identity mismatch")
        workspace = Path(env["LOOPX_PROJECT"])
        if (not workspace.is_absolute() or workspace.resolve(strict=True) != workspace or
                readback["thread"].get("cwd") != str(workspace)):
            raise ValueError("native checkpoint session workspace differs from the declared code basis")
        turns = _complete_history(request, session_id)
        ids = [t["id"] for t in turns]
    members = []
    for entry in sorted(home.iterdir()):
        if entry.name in {"sessions", "archived_sessions", "session_index.jsonl"} or re.fullmatch(
            r"(?:state|thread_history)_[0-9]+\.sqlite", entry.name
        ):
            members.append({"id": "native_" + entry.name.replace(".", "_"), "source_path": str(entry)})
    if not any(m["id"].startswith("native_state_") for m in members):
        raise ValueError("native checkpoint session index is unavailable")
    encoded = json.dumps(turns, sort_keys=True, separators=(",", ":")).encode()
    return {"components": members, "metadata": {
        "session_id": session_id, "completed_turn_id": ids[-1], "turn_ids": ids,
        "visible_history_sha256": hashlib.sha256(encoded).hexdigest(), "host_version": version,
        "guest_home": str(home), "guest_workspace": env["LOOPX_PROJECT"],
        "path_profile": "preserve_guest_paths_in_isolated_environment",
        "config_sha256": hashlib.sha256((home / "config.toml").read_bytes()).hexdigest(),
        "store_members": [{"id": c["id"], "name": Path(c["source_path"]).name} for c in members],
        "model_calls": 0, "execution_authority_granted": False,
    }}


def fork_native_checkpoint(env: dict[str, str], unit: Path, expected_sha256: str,
                           config_path: Path, *, timeout: float) -> dict[str, Any]:
    """Reconstruct one native branch in a new, fixed-path isolated environment.

    No model starts and no LoopX binding is registered. Existing session/Goal
    owners must separately admit this new session before useful continuation.
    """
    from loopx.control_plane.effect_runtime import effect_runtime_result

    deadline = time.monotonic() + timeout
    effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "verify", "root": str(unit), "expected_sha256": expected_sha256,
    }, timeout=timeout)
    manifest = json.loads((unit / "checkpoint.json").read_text())
    native = manifest["point_metadata"]["native_session"]
    home = Path(env["CODEX_HOME"])
    if str(home) != native["guest_home"] or env["LOOPX_PROJECT"] != native["guest_workspace"]:
        raise ValueError("native checkpoint requires its qualified fixed guest paths")
    if home.exists() or home.is_symlink():
        raise ValueError("native checkpoint destination home must be new")
    config = config_path.read_bytes()
    if hashlib.sha256(config).hexdigest() != native["config_sha256"]:
        raise ValueError("native checkpoint effective configuration differs")
    version = subprocess.check_output([env["CODEX_BIN"], "--version"], env=env, text=True,
                                      timeout=max(.1, deadline - time.monotonic())).strip()
    if version != native["host_version"]:
        raise ValueError("native checkpoint Host version differs")
    names = set()
    for member in native["store_members"]:
        name = member["name"]
        if (name in names or member["id"] != "native_" + name.replace(".", "_") or
                not (name in {"sessions", "archived_sessions", "session_index.jsonl"} or
                     re.fullmatch(r"(?:state|thread_history)_[0-9]+\.sqlite", name))):
            raise ValueError("native checkpoint member inventory is invalid")
        names.add(name)
    home.mkdir(parents=True, mode=0o700)
    for member in native["store_members"]:
        source, destination = unit / "components" / member["id"], home / member["name"]
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    (home / "config.toml").write_bytes(config)
    with StdioNativeGoalTransport.spawn(
        [env["CODEX_BIN"], "-c", "features.goals=false", "app-server", "--listen", "stdio://"],
        cwd=env["LOOPX_PROJECT"], env=env, stderr=subprocess.DEVNULL,
        response_timeout_sec=max(.1, deadline - time.monotonic()),
    ) as transport:
        def request(method, params):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native checkpoint reconstruction window closed")
            transport.response_timeout_sec = remaining
            return transport.request(method, params)
        request("initialize", {"clientInfo": {"name": "loopx_checkpoint", "version": "0.1.0"},
                               "capabilities": {"experimentalApi": True}})
        transport.notify("initialized", {})
        fork = request("thread/fork", {"threadId": native["session_id"],
            "lastTurnId": native["completed_turn_id"], "cwd": env["LOOPX_PROJECT"],
            "sandbox": "read-only", "approvalPolicy": "never", "deferGoalContinuation": True,
            "excludeTurns": True})
        session = fork.get("thread", {}).get("id")
        if not session or session == native["session_id"]:
            raise ValueError("native checkpoint did not create a distinct session")
        turns = _complete_history(request, session)
        encoded = json.dumps(turns, sort_keys=True, separators=(",", ":")).encode()
        if ([t["id"] for t in turns] != native["turn_ids"] or
                hashlib.sha256(encoded).hexdigest() != native["visible_history_sha256"]):
            raise ValueError("native checkpoint reconstructed history differs")
    return {"session_id": session, "completed_turn_id": native["completed_turn_id"],
            "visible_history_sha256": native["visible_history_sha256"], "history_verified": True,
            "model_calls": 0, "execution_authority_granted": False, "continuation_qualified": False}
