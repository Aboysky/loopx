"""Explicit trial-local consumer of the product's native context transport.

No packet semantics live here. The existing worker stages exact product hooks
and trusts only their native hashes; quota owns projection and full recovery.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
import shlex


def prepare_context_delivery(env: dict[str, str], home: Path) -> None:
    from loopx.control_plane.turn_driver.codex_stdio import StdioNativeGoalTransport

    root = home / "loopx-context"
    traces = home / "context-traces"
    for directory in (root, traces):
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("context diagnostics require private, physical trial directories")
    # Opt-in diagnostics are private to this trial, never global or a retention
    # assertion. Include all IO/model-input costs when comparing this treatment.
    env["CODEX_ROLLOUT_TRACE_ROOT"] = str(traces)
    env["LOOPX_CODEX_CONTEXT_DIR"] = str(root)
    command = shlex.join([env["LOOPX_CLI"], "--format", "json", "quota", "context-hook",
                          "--codex-context-dir", str(root)])
    handler = {"type": "command", "command": command, "timeout": 10}
    content = json.dumps({"hooks": {event: [{"hooks": [handler]}]
                                  for event in ("SessionStart", "PreToolUse")}})
    path = home / "hooks.json"
    if path.is_symlink() or (path.exists() and path.read_text() != content):
        raise ValueError("native context hooks changed within a trial; use a new trial")
    if not path.exists():
        path.write_text(content)
        path.chmod(0o600)
    # The native host is the hash/key owner. Do not duplicate its hashing or
    # bypass trust for unrelated workspace hooks. Discovery launches no model.
    with (home / "context-hooks-stderr.log").open("a") as stderr:
        with StdioNativeGoalTransport.spawn(
            [env["CODEX_BIN"], "app-server", "--listen", "stdio://"],
            cwd=env["LOOPX_PROJECT"], env=env, stderr=stderr, response_timeout_sec=10,
        ) as native:
            native.request("initialize", {"clientInfo": {"name": "loopx_context_transport", "version": "0.1.0"},
                                          "capabilities": {"experimentalApi": True}})
            native.notify("initialized", {})
            listed = native.request("hooks/list", {"cwds": [env["LOOPX_PROJECT"]]})
    hooks = [hook for entry in listed["data"] for hook in entry["hooks"]
             if hook.get("sourcePath") == str(path.resolve())]
    if len(hooks) != 2 or path.read_text() != content:
        raise ValueError("native host did not discover the exact trial context hooks")
    entries = []
    for hook in hooks:
        key, digest = hook.get("key"), hook.get("currentHash")
        if not isinstance(key, str) or not key or not isinstance(digest, str) or not digest:
            raise ValueError("native host returned no context-hook trust identity")
        entries.append(f"{json.dumps(key)} = {{ trusted_hash = {json.dumps(digest)} }}")
    # CLI override keys are dot-separated; native keys contain paths/dots.
    # Carry the entire table as TOML so native keys remain literal strings.
    env["LOOPX_CODEX_CONTEXT_TRUST_ARGS"] = json.dumps(["-c", "hooks.state={" + ",".join(entries) + "}"])
