"""Inert checkpoint capture reuses the real settled-Turn source owner."""
from pathlib import Path
import json
import time

import test_quota_settlement_cli as cli
from canonical_authority_fixture import isolate_sqlite_runtime

from benchmark.runtime.checkpoint import capture_after_wake
from loopx.control_plane.effect_runtime import effect_runtime_result


def test_feature_off_and_failed_wakes_do_not_read_request_or_settlement(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("feature-off/wake-failure must perform no IO")
    monkeypatch.setattr("benchmark.runtime.checkpoint.read_heartbeat_settlement", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({}, receipt)
    assert receipt == {"ok": True, "stage": "execute", "mode": "heartbeat"}
    failed = {"ok": False, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable"}, failed)
    assert failed["ok"] is False
    assert failed["checkpoint"]["captured"] is False


def test_closed_budget_never_reads_the_request_or_replays_work(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("closed budget must not read sources")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable",
                        "LOOPX_PHASE_DEADLINE_EPOCH": str(time.time() - 1)}, receipt)
    assert receipt["ok"] is True
    assert receipt["checkpoint"]["reason"] == "capture_window_closed"
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable",
                        "LOOPX_PHASE_DEADLINE_EPOCH": "nan"}, receipt)
    assert receipt["ok"] is True
    assert receipt["checkpoint"]["reason"] == "capture_failed"


def test_real_cli_settlement_capture_verification_and_inert_materialization(tmp_path, monkeypatch):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    binding = ("--agent-id", cli.AGENT_ID, "--todo-id", cli.TODO_ID, "--turn-instance-id", cli.TURN_ID)
    def run(*args):
        code, result = cli._run_cli(registry, runtime, *args)
        assert code == 0, result
        return result
    run("quota", "should-run", "--goal-id", cli.GOAL_ID, "--codex-app", *binding)
    logs = tmp_path / "logs"
    wake = logs / "wakes"
    wake.mkdir(parents=True)
    (project / "solution.py").write_text("retained_candidate = 7\n")
    request = tmp_path / "request.json"
    target = logs / "checkpoints" / "point"
    request.write_text(json.dumps({"destination": str(target), "components": [
        {"id": "code", "source_path": str(project / "solution.py")},
        {"id": "research", "source_path": str(project / f".codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md")},
    ], "point_metadata": {"meaning": "synthetic capture; no model/session or evaluator qualification"}}))
    env = {"LOOPX_CHECKPOINT_REQUEST": str(request), "LOOPX_WAKE_LOG_DIR": str(wake),
        "LOOPX_RUNTIME_ROOT": str(runtime), "LOOPX_GOAL_ID": cli.GOAL_ID,
        "LOOPX_AGENT_ID": cli.AGENT_ID, "LOOPX_REGISTRY": str(registry)}
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat", "turn_id": cli.TURN_ID}
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "owned_turn_not_settled"
    assert not target.exists()
    vision = tmp_path / "vision.json"
    vision.write_text(json.dumps({"schema_version": "goal_vision_replan_contract_v0", "state": "vision_patch_proposed",
        "vision_patch": {"acceptance_summary": "Synthetic source fixture checked; checkpoint work remains."},
        "path_delta": {"outcome": "continue", "prior_assumption": "Fixture source is available.",
            "observed_reality": "The isolated source fixture was verified.", "retained": ["Inert checkpoint qualification"],
            "evidence_refs": ["evidence:synthetic-capture"]}}))
    run("refresh-state", "--goal-id", cli.GOAL_ID, *binding, "--classification", "checkpoint_fixture_verified",
        "--delivery-batch-scale", "multi_surface", "--delivery-outcome", "outcome_progress", "--agent-vision-json", str(vision))
    run("quota", "spend-slot", "--goal-id", cli.GOAL_ID, *binding, "--source", "heartbeat", "--execute")
    goal_state = project / f".codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md"
    retained_goal = goal_state.read_bytes()
    capture_after_wake(env, receipt)
    assert receipt["ok"] is True
    assert receipt["checkpoint"].get("captured") is True, receipt
    assert receipt["checkpoint"]["research_point_qualified"] is False
    assert goal_state.read_bytes() == retained_goal
    digest = receipt["checkpoint"]["sha256"]
    restored = effect_runtime_result("runtime.checkpoint_artifacts", {"action": "materialize", "root": str(target),
        "expected_sha256": digest, "destination": str(tmp_path / "inert")})
    assert restored["activation_performed"] is False
    assert (tmp_path / "inert/components/code").read_text() == "retained_candidate = 7\n"
    before = (target / "checkpoint.json").read_bytes()
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "destination_already_present_no_replay"
    assert (target / "checkpoint.json").read_bytes() == before
    assert goal_state.read_bytes() == retained_goal
