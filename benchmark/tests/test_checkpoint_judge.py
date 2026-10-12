"""Native owner semantics; real grading/transport is qualified by the Docker smoke."""
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def native_config(tmp_path, monkeypatch):
    pytest.importorskip("sforge")
    from sforge.harness import judge_server
    from sforge.harness.config import SForgeConfig
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "BENCHMARK.yaml").write_text("name: fixture\nbase_images: {python: {}}\n")
    (tasks / "fixture.json").write_text(json.dumps({
        "task_id": "fixture", "name": "Synthetic checkpoint", "base_image": "python",
        "platform": "linux/arm64", "cwd": "/tmp", "internet": False,
        "submit_paths": ["solver.py"], "submit_exclude": [],
        "work": {"image_tag": "fixture", "agent_query": "Synthetic fixture"},
        "judge": {"image_tag": "fixture", "eval_timeout": 15, "parser": "structured_json",
                  "selection": "score_first", "score_direction": "maximize", "eval_cmd": "true"},
    }))
    monkeypatch.setattr(judge_server, "create_backend_from_config", lambda config: SimpleNamespace())
    return SForgeConfig(tasks_dir=tasks, log_dir=tmp_path)


def test_disabled_extension_preserves_the_native_route_surface(native_config):
    from benchmark.edgebench.checkpoint_judge import create_app
    from sforge.harness.judge_server import create_app as native_app
    first, second = native_app(native_config), create_app(native_config)
    try:
        assert [(r.path, r.methods) for r in first.routes] == [(r.path, r.methods) for r in second.routes]
    finally:
        first.state.judge.close()
        second.state.judge.close()


def test_capture_retains_consumed_round_history_and_cooldown_without_mutation(native_config):
    from fastapi.testclient import TestClient
    from benchmark.edgebench.checkpoint_judge import create_app, ROUTE
    app = create_app(native_config, checkpoint_capture=True)
    state = app.state.judge
    with TestClient(app) as client:
        token = state.register_session("fixture", "source", max_agent_submissions=12, submission_cooldown=3600)
        state.consume_round(token)
        state._record_submission("source", "accepted-error", "fixture", "agent-1", None,
                                 "synthetic evaluation failure", status="error")
        state.submissions["accepted-error"] = {"run_id": "source", "task_id": "fixture", "round": "agent-1",
            "status": "error", "report": None, "error": "synthetic evaluation failure"}
        before = state.resolve_token(token)
        result = client.post(ROUTE, json={"token": token})
        assert result.status_code == 200
        point = result.json()
        assert point["next_agent_round"] == 2 and point["next_auto_round"] == 1
        assert point["max_agent_submissions"] == 12
        assert 0 < point["remaining_cooldown_seconds"] <= 3600
        assert point["last_agent_submit_at_epoch"] == before["last_agent_submit_at"]
        assert point["released_history"] == state.get_run_history("source", "fixture")["entries"]
        assert point["released_history"][0]["status"] == "error"
        assert point["released_results"]["accepted-error"]["error"] == "synthetic evaluation failure"
        assert point["execution_authority_granted"] is False
        assert token not in json.dumps(point) and "admin_secret" not in json.dumps(point)
        assert state.resolve_token(token) == before
        assert client.post(ROUTE, json={"token": token}).json()["judge_epoch"] == point["judge_epoch"]


@pytest.mark.parametrize("gap", ["pending", "unreconciled", "automatic", "closed"])
def test_incomplete_opportunity_state_cannot_be_a_checkpoint(native_config, gap):
    from fastapi.testclient import TestClient
    from benchmark.edgebench.checkpoint_judge import create_app, ROUTE
    app = create_app(native_config, checkpoint_capture=True)
    state = app.state.judge
    with TestClient(app) as client:
        token = state.register_session("fixture", "source", submission_cooldown=3600)
        if gap == "pending":
            state._outstanding_by_run[("source", "fixture")] = 1
        elif gap == "unreconciled":
            state.consume_round(token)
        elif gap == "automatic":
            state.consume_round(token, "auto")
        else:
            state._closed = True
        assert client.post(ROUTE, json={"token": token}).status_code == 409
        assert client.post(ROUTE, json={"token": "unregistered"}).status_code == 403
        assert client.post(ROUTE, json={"token": token, "restore": True}).status_code == 422
