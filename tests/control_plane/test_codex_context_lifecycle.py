"""Native lifecycle references cannot stand in for retained model input."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from loopx.control_plane.turn_driver import codex_context as context


def setup(root, monkeypatch):
    root.chmod(0o700)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CODEX_THREAD_ID", "session")
    monkeypatch.delenv("CODEX_ROLLOUT_TRACE_ROOT", raising=False)
    event = dict(session_id="session", cwd=str(root), hook_event_name="SessionStart", source="startup")
    assert context.codex_context_hook(str(root), event) == {}
    return event


def project(root, capture_id="one", *, payload=None):
    directory = root / capture_id
    directory.mkdir(mode=0o700)
    if payload is None:
        payload = {"ok": True, "goal_id": "fixture", "requirements": "Preserve final stop condition."}
    result = context.project_codex_context(payload, directory=str(root), capture_directory=directory,
        goal_id="fixture", agent_id="agent", surface="quota_packet", capture_id=capture_id)
    return payload, result


@pytest.mark.parametrize("event_name,source", [("SessionStart", "compact"),
    ("SessionStart", "startup"), ("PreCompact", None)])
def test_lifecycle_invalidates_and_recovers_current_capture_without_bodies(tmp_path, monkeypatch, event_name, source):
    event = setup(tmp_path, monkeypatch)
    payload, first = project(tmp_path)
    assert first["mode"] == "full" and first["context"] == payload
    before = context._state(tmp_path)
    result = context.codex_context_hook(str(tmp_path), {**event, "hook_event_name": event_name, "source": source})
    after = context._state(tmp_path)
    assert before["context_epoch"] != after["context_epoch"] and "candidate" not in after
    assert after["recovery"] == before["recovery"]
    if event_name == "SessionStart":
        body = result["hookSpecificOutput"]["additionalContext"]
        assert first["recovery"]["sha256"] in body and "quota context-read" in body
        assert payload["requirements"] not in body and len(body) < 2000
    else:
        assert result == {}
    _, second = project(tmp_path, "two")
    assert second["mode"] == "full" and second["target"]["context_epoch"] == after["context_epoch"]


def test_resume_keeps_only_an_unconfirmed_candidate_and_never_borrows_old_call(tmp_path, monkeypatch):
    event = setup(tmp_path, monkeypatch)
    _, first = project(tmp_path)
    context.codex_context_hook(str(tmp_path), {**event, "hook_event_name": "PreToolUse", "tool_use_id": "old"})
    before = context._state(tmp_path)
    result = context.codex_context_hook(str(tmp_path), {**event, "source": "resume"})
    after = context._state(tmp_path)
    assert after["candidate"] == before["candidate"] and after["context_epoch"] == before["context_epoch"]
    assert after["active_call"] is None
    assert first["recovery"]["command"] in result["hookSpecificOutput"]["additionalContext"]
    assert "unconfirmed" in result["hookSpecificOutput"]["additionalContext"]
    # No current-input proof: even a complete private candidate remains full.
    _, second = project(tmp_path, "two")
    assert second["mode"] == "full"


@pytest.mark.parametrize("case", ["closed_old", "duplicate_live", "abandoned_old", "missing_input", "discovery_overflow"])
def test_resumed_bundle_needs_unique_current_input_not_latest_file(tmp_path, monkeypatch, case):
    from test_codex_input_retention import fixture

    event = setup(tmp_path, monkeypatch)
    requirements = "Preserve the whole source and final stop condition. " * 1000
    payload = {"ok": True, "goal_id": "fixture", "plan_summary": {"requirements": requirements}}
    _, first = project(tmp_path, payload=payload)
    traces = tmp_path / "traces"
    traces.mkdir()
    for number in (1, 2):
        parent = tmp_path / str(number)
        parent.mkdir()
        observation, _, _, rows = fixture(parent)
        bundle = Path(observation["trace_bundle"])
        if number == 1 and case not in {"duplicate_live", "abandoned_old"}:
            rows.append({**rows[-1], "seq": 3, "payload": {"type": "tool_call_ended", "tool_call_id": "guard"}})
        (bundle / "trace.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        missing = case == "missing_input" or (case == "abandoned_old" and number == 2)
        (bundle / "payloads/input.json").write_text(json.dumps({"input": [] if missing else [
            {"type": "function_call_output", "output": json.dumps(first)}]}))
        bundle.rename(traces / f"trace-{number}")
    if case == "discovery_overflow":
        for number in range(3, 130):
            (traces / f"trace-{number}").mkdir()
    monkeypatch.setenv("CODEX_ROLLOUT_TRACE_ROOT", str(traces))
    context.codex_context_hook(str(tmp_path), {**event, "source": "resume"})
    context.codex_context_hook(str(tmp_path), {**event, "hook_event_name": "PreToolUse", "tool_use_id": "guard"})
    _, second = project(tmp_path, "two", payload=payload)
    assert second["mode"] == ("delta" if case == "closed_old" else "full")


def test_missing_observer_or_hook_never_reuses_candidate_and_other_sessions_do_not_borrow(tmp_path, monkeypatch):
    event = setup(tmp_path, monkeypatch)
    _, first = project(tmp_path)
    context.codex_context_hook(str(tmp_path), {**event, "hook_event_name": "PreToolUse", "tool_use_id": "current"})
    _, second = project(tmp_path, "two")
    assert second["mode"] == "full"  # a present file plus a hook is not proof
    assert second["target"]["capture_id"] != first["target"]["capture_id"]
    monkeypatch.setenv("CODEX_THREAD_ID", "another-session")
    payload, rejected = project(tmp_path, "other")
    assert rejected == payload
    assert context.codex_context_hook(str(tmp_path), {**event, "session_id": "another-session", "source": "fork"}) == {}
    assert "recovery" not in context._state(tmp_path) and "candidate" not in context._state(tmp_path)


def test_primary_write_failure_preserves_small_recovery_and_does_not_create_ack(tmp_path, monkeypatch):
    event = setup(tmp_path, monkeypatch)
    _, wire = project(tmp_path)
    before = (tmp_path / "session.json").read_bytes()
    def unavailable(*args, **kwargs):
        raise OSError("synthetic journal unavailable")
    monkeypatch.setattr(context, "_save", unavailable)
    result = context.codex_context_hook(str(tmp_path), {**event, "source": "compact"})
    assert wire["recovery"]["sha256"] in result["hookSpecificOutput"]["additionalContext"]
    assert (tmp_path / "session.json").read_bytes() == before
    # A primary store failure during publication returns the whole admitted
    # payload. It cannot leak an untracked candidate delta.
    payload, full = project(tmp_path, "two")
    assert full == payload


@pytest.mark.parametrize("damage", ["missing", "corrupt", "symlink", "public", "other_workspace"])
def test_invalid_journal_falls_back_to_original_full(tmp_path, monkeypatch, damage):
    setup(tmp_path, monkeypatch)
    path = tmp_path / "session.json"
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_text("{partial")
    elif damage == "symlink":
        other = tmp_path / "other.json"
        path.rename(other)
        path.symlink_to(other)
    elif damage == "public":
        path.chmod(0o644)
    elif damage == "other_workspace":
        state = context._state(tmp_path)
        state["cwd"] = str(tmp_path.parent)
        context._save(tmp_path, state)
    payload, full = project(tmp_path)
    assert full == payload


def test_real_hook_cli_is_transport_only_without_registry_or_installation(tmp_path):
    directory = tmp_path / "native"
    directory.mkdir(mode=0o700)
    registry, runtime = tmp_path / "absent-registry.json", tmp_path / "absent-runtime"
    cmd = [sys.executable, "-m", "loopx.entrypoint", "--registry", str(registry), "--runtime-root", str(runtime),
        "quota", "context-hook", "--codex-context-dir", str(directory)]
    event = dict(session_id="session", cwd=str(tmp_path), hook_event_name="SessionStart", source="startup")
    result = subprocess.run(cmd, input=json.dumps(event), capture_output=True, text=True, timeout=20,
        cwd=Path(__file__).resolve().parents[2])
    assert result.returncode == 0 and json.loads(result.stdout) == {}, result.stderr
    assert context._state(directory)["session_id"] == "session"
    assert not registry.exists() and not runtime.exists()
