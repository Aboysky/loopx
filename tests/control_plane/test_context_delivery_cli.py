"""Real quota sources share an exact, effect-free full/delta presentation owner.

These tests qualify the CLI and RPC, not native Host retention observation.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from canonical_authority_fixture import initialize_canonical_authority, isolate_sqlite_runtime, read_fixture_todos
from loopx.control_plane.coordination.runtime_shadow import build_todo_runtime_shadow_projection
from loopx.control_plane.quota.turn_envelope import (
    build_turn_envelope, prepare_work_context_delivery, restore_work_context_delivery,
)
from test_quota_settlement_cli import (
    AGENT_ID, GOAL_ID, TODO_ID,
    _run_cli, _spend_run_count, _write_fixture,
)


@pytest.mark.parametrize("provider", ["file", "sqlite"])
@pytest.mark.parametrize("profile", ["codex_app", "generic_cli"])
def test_cli_capture_exact_delta_and_same_capture_recovery(tmp_path: Path, monkeypatch, provider, profile):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = _write_fixture(tmp_path)
    state = project / f".codex/goals/{GOAL_ID}/ACTIVE_GOAL_STATE.md"
    body = "Preserve every source row and cancellation condition. " * 500
    body += "FINAL CONDITION: stop before publication."
    todos = read_fixture_todos(state)
    todos[0].update(text=body, title=body)
    initialize_canonical_authority(runtime, GOAL_ID,
        build_todo_runtime_shadow_projection(goal_id=GOAL_ID, todos=todos, handoff_mode="soft_claim"),
        state_path=state, provider=provider)
    before_source = state.read_bytes()
    host = ["--codex-app"] if profile == "codex_app" else ["--runtime-profile", profile]
    rc, guard = _run_cli(registry, runtime, "quota", "should-run", *host,
        "--goal-id", GOAL_ID, "--agent-id", AGENT_ID, "--todo-id", TODO_ID,
        "--turn-instance-id", "context-presentation", cwd=project)
    assert rc == 0 and guard["should_run"] is True, guard
    context = guard["interaction_contract"]["agent_channel"]["work_context"]
    selected = next(s["content"]["todo"] for s in context["sources"] if s.get("source") == "selected_todo")
    assert selected["text"] == body
    assert selected.get("title") != body  # only the exact duplicate is elided
    turn_context = build_turn_envelope(guard)["work_context"]
    assert turn_context["sources"] == context["sources"]
    assert turn_context["instruction"] == context["instruction"]
    original = deepcopy(guard)
    scope = dict(goal_id=GOAL_ID, agent_id=AGENT_ID, session_id=profile, context_epoch="epoch-a")
    full = prepare_work_context_delivery(context, scope=scope, capture_id="capture-a")
    assert full["mode"] == "full" and full["context"] == context
    warm = prepare_work_context_delivery(context, scope=scope, capture_id="capture-b",
        baseline=full, retained={"complete": True, "target": full["target"]})
    assert warm["mode"] == "delta"
    assert len(json.dumps(warm).encode()) < len(json.dumps(full).encode()) / 2
    current = prepare_work_context_delivery(context, scope=scope, capture_id="capture-b")
    assert restore_work_context_delivery(warm, baseline=full, current=current)["context"] == context
    turn_full = prepare_work_context_delivery(turn_context, scope=scope, capture_id="turn-capture")
    turn_delta = prepare_work_context_delivery(turn_context, scope=scope, capture_id="turn-capture",
        baseline=full, retained={"complete": True, "target": full["target"]})
    assert turn_delta["mode"] == "delta"
    assert restore_work_context_delivery(turn_delta, baseline=full, current=turn_full)["context"] == turn_context
    for baseline, delivery in [(None, warm), (full, {**warm, "reused": []})]:
        recovered = restore_work_context_delivery(delivery, baseline=baseline, current=current)
        assert recovered["mode"] == "full" and recovered["context"] == context
        assert recovered["target"] == current["target"]
    reset = prepare_work_context_delivery(context, scope={**scope, "context_epoch": "epoch-b"},
        capture_id="capture-b", baseline=full, retained={"complete": True, "target": full["target"]})
    assert reset["mode"] == "full" and reset["context"] == context
    # Neither native source state, the signed decision nor settlement is changed
    # by presentation, warm reuse or recovery. A new capture is not an admission.
    assert state.read_bytes() == before_source
    assert guard == original
    assert _spend_run_count(runtime) == 0
    rc, readback = _run_cli(registry, runtime, "todo", "list", "--goal-id", GOAL_ID, "--todo-id", TODO_ID)
    assert rc == 0 and readback["todo"]["text"] == body, readback
    assert readback["todo"]["status"] == "open"
