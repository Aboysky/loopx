"""Inert checkpoint capture reuses the real settled-Turn source owner."""
from pathlib import Path
import json
import hashlib
import pytest
import time

import test_quota_settlement_cli as cli
from canonical_authority_fixture import isolate_sqlite_runtime

from benchmark.runtime.checkpoint import capture_after_wake, capture_before_replan
from loopx.control_plane.effect_runtime import effect_runtime_result


def test_feature_off_and_failed_wakes_do_not_read_request_or_settlement(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("feature-off/wake-failure must perform no IO")
    monkeypatch.setattr("benchmark.runtime.checkpoint.read_heartbeat_settlement", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({}, receipt)
    assert receipt == {"ok": True, "stage": "execute", "mode": "heartbeat"}
    assert capture_before_replan({}, receipt, "original body") == "original body"
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


@pytest.mark.parametrize("opportunity,corrupt", [(False, False), (True, False), (True, True)])
def test_real_cli_settlement_capture_verification_and_inert_materialization(tmp_path, monkeypatch, opportunity, corrupt):
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
    (wake / cli.TURN_ID).mkdir()
    observed = []
    incumbent_bytes = b"opaque older adopted candidate"
    opportunity_packet = {"meaning": "synthetic opportunity participant; no admission", "native_incumbent": {
        "round": "agent-1", "archive_sha256": hashlib.sha256(incumbent_bytes).hexdigest(), "archive_bytes": len(incumbent_bytes)}}
    def export(env, *, timeout, incumbent_path):
        assert 0 < timeout <= 30
        observed.append(True)
        incumbent_path.write_bytes(incumbent_bytes)
        return opportunity_packet
    monkeypatch.setattr("benchmark.runtime.sforge_checkpoint.capture_opportunity", export)
    if corrupt:
        def altered_probe(method, params, **kwargs):
            if params["action"] == "probe":
                next(wake.glob("*/checkpoint-incumbent.tar.gz")).write_bytes(b"altered after transport")
            return effect_runtime_result(method, params, **kwargs)
        monkeypatch.setattr("benchmark.runtime.checkpoint.effect_runtime_result", altered_probe)
    (project / "solution.py").write_text("retained_candidate = 7\n")
    request = tmp_path / "request.json"
    target = logs / "checkpoints" / "point"
    request.write_text(json.dumps({"destination": str(target), "components": [
        {"id": "code", "source_path": str(project / "solution.py")},
        {"id": "research", "source_path": str(project / f".codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md")},
    ], "point_metadata": {"meaning": "synthetic capture; no model/session or evaluator qualification"},
        **({"evaluation_opportunity": True} if opportunity else {})}))
    env = {"LOOPX_CHECKPOINT_REQUEST": str(request), "LOOPX_WAKE_LOG_DIR": str(wake),
        "LOOPX_RUNTIME_ROOT": str(runtime), "LOOPX_GOAL_ID": cli.GOAL_ID,
        "LOOPX_AGENT_ID": cli.AGENT_ID, "LOOPX_REGISTRY": str(registry)}
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat", "turn_id": cli.TURN_ID}
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "owned_turn_not_settled"
    assert not target.exists()
    assert observed == []
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
    if corrupt:
        assert receipt["checkpoint"]["captured"] is False and not target.exists()
        assert "differs" in receipt["checkpoint"]["error"]
        assert goal_state.read_bytes() == retained_goal
        return
    assert receipt["checkpoint"].get("captured") is True, receipt
    assert receipt["checkpoint"]["research_point_qualified"] is False
    assert goal_state.read_bytes() == retained_goal
    if opportunity:
        assert json.loads((target / "components/evaluation_opportunity").read_text()) == opportunity_packet
        assert (target / "components/evaluation_incumbent").read_bytes() == incumbent_bytes

    digest = receipt["checkpoint"]["sha256"]
    restored = effect_runtime_result("runtime.checkpoint_artifacts", {"action": "materialize", "root": str(target),
        "expected_sha256": digest, "destination": str(tmp_path / "inert")})
    assert restored["activation_performed"] is False
    assert (tmp_path / "inert/components/code").read_text() == "retained_candidate = 7\n"
    if opportunity:
        assert (tmp_path / "inert/components/evaluation_incumbent").read_bytes() == incumbent_bytes
    before = (target / "checkpoint.json").read_bytes()
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "destination_already_present_no_replay"
    assert (target / "checkpoint.json").read_bytes() == before
    assert goal_state.read_bytes() == retained_goal
    assert len(observed) == int(opportunity)


@pytest.mark.parametrize("capture_fails", [False, True])
def test_real_pre_replan_capture_is_before_decision_and_same_node_is_not_recaptured(tmp_path, monkeypatch, capture_fails):
    import os
    import sys

    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    binding = ("--agent-id", cli.AGENT_ID, "--todo-id", cli.TODO_ID, "--turn-instance-id", cli.TURN_ID)

    def run(*args):
        code, result = cli._run_cli(registry, runtime, *args)
        assert code == 0, result
        return result

    run("quota", "should-run", "--goal-id", cli.GOAL_ID, "--codex-app", *binding)
    vision = tmp_path / "vision.json"
    vision.write_text(json.dumps({"schema_version": "goal_vision_replan_contract_v0", "state": "vision_patch_proposed",
        "vision_patch": {"acceptance_summary": "Synthetic source fixture checked; capture work remains."},
        "path_delta": {"outcome": "continue", "prior_assumption": "Source fixture is available.",
            "observed_reality": "Isolated source fixture verified.", "retained": ["Capture qualification"],
            "evidence_refs": ["evidence:synthetic-pre-replan"]}}))
    run("refresh-state", "--goal-id", cli.GOAL_ID, *binding, "--classification", "pre_replan_fixture_verified",
        "--delivery-batch-scale", "multi_surface", "--delivery-outcome", "outcome_progress", "--agent-vision-json", str(vision))
    run("quota", "spend-slot", "--goal-id", cli.GOAL_ID, *binding, "--source", "heartbeat", "--execute")
    index = runtime / "goals" / cli.GOAL_ID / "runs/index.jsonl"
    original_settlement = index.read_bytes()
    cli._configure_autonomous_replan_fixture(project, runtime, registry)
    # This helper supplies synthetic repeated observations; retain the real
    # source settlement history instead of replacing its authoritative readback.
    index.write_bytes(original_settlement + index.read_bytes())
    logs = tmp_path / "logs"
    wakes = logs / "wakes"
    prior = wakes / "wake-100-prior"
    prior.mkdir(parents=True)
    prior_receipt = {"turn_id": cli.TURN_ID, "mode": "heartbeat", "stage": "execute", "ok": True}
    (prior / "receipt.json").write_text(json.dumps(prior_receipt))
    solution = project / "solution.py"
    solution.write_text("retained_candidate = 7\n")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"trigger": "fresh_replan", "destination": str(logs / "checkpoints"),
        "components": [{"id": "code", "source_path": str(solution)}],
        "point_metadata": {"purpose": "synthetic original settlement and replan ordering"}}))
    env = {**os.environ, "LOOPX_CLI": str(Path(sys.executable).parent / "loopx"),
        "LOOPX_PROJECT": str(project), "LOOPX_CHECKPOINT_REQUEST": str(request),
        "LOOPX_WAKE_LOG_DIR": str(wakes), "LOOPX_RUNTIME_ROOT": str(runtime),
        "LOOPX_GOAL_ID": cli.GOAL_ID, "LOOPX_AGENT_ID": cli.AGENT_ID, "LOOPX_REGISTRY": str(registry)}
    receipt = {"turn_id": "synthetic-replan-point", "mode": "heartbeat", "stage": "execute", "ok": False}
    (wakes / receipt["turn_id"]).mkdir()
    attempted = []
    if capture_fails:
        def fail_probe(method, params, **kwargs):
            if params["action"] == "probe":
                attempted.append(True)
                raise RuntimeError("synthetic capture failure")
            return effect_runtime_result(method, params, **kwargs)
        monkeypatch.setattr("benchmark.runtime.checkpoint.effect_runtime_result", fail_probe)
    body = capture_before_replan(env, receipt, "original instructions")
    if capture_fails:
        assert receipt["checkpoint"]["reason"] == "capture_failed", receipt
        solution.write_text("later_decision = 11\n")
        again = {"turn_id": receipt["turn_id"], "mode": "heartbeat", "stage": "execute", "ok": False}
        capture_before_replan(env, again, "original instructions")
        assert again["checkpoint"]["reason"] == "pre_decision_capture_already_attempted", again
        assert attempted == [True] and not list((logs / "checkpoints").glob("replan-*/checkpoint.json"))
        assert body.endswith("original instructions") and receipt["ok"] is False
        return
    assert receipt["checkpoint"]["captured"] is True, json.dumps(receipt)
    target = Path(receipt["checkpoint"]["destination"])
    captured = (target / "checkpoint.json").read_bytes()
    assert (target / "components/code").read_text() == "retained_candidate = 7\n"
    assert body.endswith("original instructions") and "original quota guard once" in body
    assert receipt["ok"] is False  # Capturing cannot declare the new work completed.
    assert (prior / "receipt.json").read_text() == json.dumps(prior_receipt)
    # The model's subsequent decision/work must not replace the pre-decision point.
    solution.write_text("new_route = 11\n")
    capture_after_wake(env, receipt)
    assert (target / "checkpoint.json").read_bytes() == captured
    # Reentry on the exact original guard reads back one point, even if code moved.
    again = {"turn_id": receipt["turn_id"], "mode": "heartbeat", "stage": "execute", "ok": False}
    capture_before_replan(env, again, "original instructions")
    assert again["checkpoint"]["reason"] == "replan_already_captured", json.dumps(again)
    assert (target / "checkpoint.json").read_bytes() == captured
