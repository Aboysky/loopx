"""One machine opt-in reaches existing native callers without new authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest

from loopx.control_plane.turn_driver.context_machine import CONTEXT_DELIVERY_MACHINE_SCHEMA
from tests.control_plane.canonical_authority_fixture import isolate_sqlite_runtime
from tests.control_plane.test_quota_settlement_cli import (
    AGENT_ID, GOAL_ID, TODO_ID, _heartbeat_receipt_count, _initialize_fixture_authority,
    _run_cli, _spend_run_count, _write_fixture,
)


def configure(registry, runtime, root, mode):
    config = root / "context-setting.json"
    config.write_text(json.dumps({"schema_version": CONTEXT_DELIVERY_MACHINE_SCHEMA, "mode": mode}))
    args = ["--namespace", "context_delivery", "--config-json", str(config)]
    code, preview = _run_cli(registry, runtime, "machine-config", "preview", *args)
    if code:
        return code, preview
    return _run_cli(registry, runtime, "machine-config", "apply", *args,
        "--expected-plan-revision", preview["plan_revision"], "--execute")


@pytest.mark.parametrize("invalid", [True, False, None, 1, "auto", "codex_app_heartbeat"])
def test_invalid_machine_mode_never_writes(tmp_path, invalid):
    registry, runtime = tmp_path / "absent.json", tmp_path / "runtime"
    code, result = configure(registry, runtime, tmp_path, invalid)
    assert code != 0 and not result["ok"]
    assert not registry.exists() and not (runtime / "machine/configuration.json").exists()


def test_machine_on_preserves_existing_worker_environment_off(tmp_path, monkeypatch):
    registry, runtime = tmp_path / "absent.json", tmp_path / "runtime"
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    monkeypatch.setenv("LOOPX_CONTEXT_DELIVERY", "off")
    monkeypatch.setenv("LOOPX_EXECUTION_MODE", "heartbeat")
    code, result = _run_cli(registry, runtime, "quota", "context-config",
        "--runtime-profile", "generic_cli", "--goal-id", "fixture", "--agent-id", "worker")
    assert code == 0 and result["context_delivery"]["enabled"] is False, result
    assert not (runtime / "context-delivery").exists() and not registry.exists()


@pytest.mark.parametrize("host", [[], ["--runtime-profile", "codex_cli"],
    ["--codex-app", "--runtime-profile", "codex_app_heartbeat"],
    ["--host-surface", "codex_app"], ["--runtime-profile", "generic_cli"]])
def test_inherited_on_rejects_unknown_or_unsupported_before_admission(tmp_path, monkeypatch, host):
    monkeypatch.delenv("LOOPX_CONTEXT_DELIVERY", raising=False)
    monkeypatch.delenv("LOOPX_EXECUTION_MODE", raising=False)
    registry, runtime = tmp_path / "absent.json", tmp_path / "runtime"
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    code, result = _run_cli(registry, runtime, "quota", "context-config", *host,
        "--goal-id", "fixture", "--agent-id", "worker")
    assert code != 0 and not result["ok"], result
    assert not (runtime / "context-delivery").exists() and not registry.exists()
    assert _spend_run_count(runtime) == 0


@pytest.mark.parametrize("profile", ["codex_app", "benchmark"])
@pytest.mark.skipif(os.name != "posix", reason="Native continuity uses POSIX private directories and locks")
def test_native_configuration_inherits_only_the_two_declared_scenarios_and_later_off(tmp_path, monkeypatch, profile):
    registry, runtime = tmp_path / "absent.json", tmp_path / "runtime"
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    if profile == "benchmark":
        monkeypatch.setenv("LOOPX_CONTEXT_DELIVERY", "on")
        monkeypatch.setenv("LOOPX_EXECUTION_MODE", "heartbeat")
    host = ["--codex-app"] if profile == "codex_app" else ["--runtime-profile", "generic_cli"]
    code, result = _run_cli(registry, runtime, "quota", "context-config", *host,
        "--goal-id", "fixture", "--agent-id", "worker")
    assert code == 0 and result["context_delivery"]["enabled"], result
    expected = "codex_app_heartbeat" if profile == "codex_app" else "codex_benchmark_heartbeat"
    assert result["context_delivery"]["scenario"] == expected
    root = runtime / "context-delivery"
    assert root.stat().st_mode & 0o077 == 0
    handler = result["native_config"]["hooks"]["SessionStart"][0]["hooks"][0]
    argv = shlex.split(handler["command"])
    assert "--context-delivery" not in argv and argv[argv.index("--runtime-root") + 1] == str(runtime)
    assert not registry.exists()
    assert configure(registry, runtime, tmp_path, "off")[0] == 0
    before = list(root.iterdir())
    event = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "session", "cwd": str(tmp_path)}
    completed = subprocess.run(argv, input=json.dumps(event), text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == {} and list(root.iterdir()) == before


@pytest.mark.parametrize("provider", ["file", "sqlite"])
@pytest.mark.skipif(os.name != "posix", reason="Native continuity uses POSIX private directories and locks")
def test_machine_on_reaches_real_guard_and_same_capture_readback_without_readmission(tmp_path, monkeypatch, provider):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "machine-context-session")
    monkeypatch.delenv("CODEX_ROLLOUT_TRACE_ROOT", raising=False)
    project, runtime, registry = _write_fixture(tmp_path)
    _initialize_fixture_authority(project, runtime, provider=provider)
    state = project / f".codex/goals/{GOAL_ID}/ACTIVE_GOAL_STATE.md"
    original_state = state.read_bytes()
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    code, setup = _run_cli(registry, runtime, "quota", "context-config", "--codex-app",
        "--goal-id", GOAL_ID, "--agent-id", AGENT_ID, cwd=project)
    assert code == 0, setup
    hook = setup["native_config"]["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    event = {"session_id": "machine-context-session", "cwd": str(project), "hook_event_name": "SessionStart", "source": "startup"}
    subprocess.run(shlex.split(hook), input=json.dumps(event), text=True, cwd=project,
        capture_output=True, check=True)
    args = ["quota", "should-run", "--codex-app", "--goal-id", GOAL_ID,
        "--agent-id", AGENT_ID, "--todo-id", TODO_ID, "--turn-instance-id", "machine-original-turn"]
    code, wire = _run_cli(registry, runtime, *args, cwd=project)
    assert code == 0 and wire["mode"] == "full", wire
    recovery = wire["recovery"]
    raw = Path(recovery["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == recovery["sha256"]
    assert json.loads(raw) == wire["context"]
    code, page = _run_cli(registry, runtime, "quota", "context-read", "--goal-id", GOAL_ID,
        "--agent-id", AGENT_ID, cwd=project)
    assert code == 0 and page["sha256"] == recovery["sha256"], page
    assert page["content"].encode() == raw[:page.get("next_offset") or len(raw)]
    assert _heartbeat_receipt_count(runtime, "machine-original-turn") == 1
    assert _spend_run_count(runtime) == 0 and state.read_bytes() == original_state
    # Explicit off wins over machine on, including old ordinary full output.
    code, full = _run_cli(registry, runtime, *args, "--context-delivery", "off", cwd=project)
    assert code == 0 and full["ok"] and full.get("schema_version") != "context_delivery_v1"
    assert _heartbeat_receipt_count(runtime, "machine-original-turn") == 1
    # Digest-bound recovery remains usable even with broken device configuration.
    (runtime / "machine/configuration.json").write_text("{broken")
    code, page = _run_cli(registry, runtime, "quota", "context-read", "--capture-file", recovery["path"],
        "--capture-sha256", recovery["sha256"], cwd=project)
    assert code == 0 and page["sha256"] == recovery["sha256"]
    code, full = _run_cli(registry, runtime, *args, "--context-delivery", "off", cwd=project)
    # Off bypasses this transport setting, not other owners' validation of a
    # broken whole-machine document. Recovery remains independent above.
    assert code != 0 and not full["ok"], full


@pytest.mark.skipif(os.name != "posix", reason="Native continuity uses POSIX private directories and locks")
def test_bootstrap_reloads_machine_setting_and_preserves_explicit_off(tmp_path, monkeypatch):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = _write_fixture(tmp_path)
    _initialize_fixture_authority(project, runtime)
    original_registry = registry.read_bytes()
    args = ["heartbeat-prompt", "--thin", "--codex-app", "--goal-id", GOAL_ID, "--agent-id", AGENT_ID]
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    code, enabled = _run_cli(registry, runtime, *args)
    assert code == 0 and "--context-delivery on" in enabled["task_body"], enabled
    code, bootstrap = _run_cli(registry, runtime, *args, "--bootstrap")
    assert code == 0, bootstrap
    assert "--context-delivery" not in bootstrap["task_body"]
    assert str(runtime / "context-delivery") not in bootstrap["task_body"]
    code, pinned = _run_cli(registry, runtime, *args, "--bootstrap", "--context-delivery", "off")
    assert code == 0 and "--context-delivery off" in pinned["task_body"], pinned
    assert configure(registry, runtime, tmp_path, "off")[0] == 0
    code, disabled = _run_cli(registry, runtime, *args)
    assert code == 0 and "--context-delivery on" not in disabled["task_body"], disabled
    assert registry.read_bytes() == original_registry and _spend_run_count(runtime) == 0


@pytest.mark.parametrize("kind", ["symlink", "public"])
@pytest.mark.skipif(os.name != "posix", reason="Native continuity uses POSIX private directories and locks")
def test_machine_default_never_follows_or_chmods_an_unsafe_transport_root(tmp_path, kind):
    registry, runtime = tmp_path / "absent.json", tmp_path / "runtime"
    assert configure(registry, runtime, tmp_path, "on")[0] == 0
    root = runtime / "context-delivery"
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    if kind == "symlink":
        root.symlink_to(target, target_is_directory=True)
    else:
        root.mkdir(mode=0o755)
        root.chmod(0o755)
    before = (target if kind == "symlink" else root).stat().st_mode
    code, result = _run_cli(registry, runtime, "quota", "context-config", "--codex-app",
        "--goal-id", "fixture", "--agent-id", "worker")
    assert code != 0 and not result["ok"], result
    assert (target if kind == "symlink" else root).stat().st_mode == before
    assert not list(target.iterdir()) and not registry.exists()
