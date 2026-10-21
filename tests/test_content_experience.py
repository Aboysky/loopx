"""Real CLI, TS owner, source revisions and loopback boundaries."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import pytest

from loopx.capabilities.content_ops.experience import ExperienceWorkspace
from loopx.capabilities.content_ops.media import MediaWorkspace
from loopx.chat_server import ChatHTTPServer, ChatRequestHandler

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for key in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    project = tmp_path / "project"
    project.mkdir()
    runtime, registry = tmp_path / "runtime", tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema_version": "0.1", "common_runtime_root": str(runtime),
        "goals": [{"id": "experience-demo", "repo": str(project), "status": "active"}]}))
    media = MediaWorkspace(registry_path=registry, goal_id="experience-demo", runtime_root=runtime)
    return ExperienceWorkspace(media), media, registry


def plan():
    return json.loads((ROOT / "examples/content-ops-experience/evidence-return.json").read_text())


def test_cli_prepares_and_replays_two_real_briefs_without_a_renderer(workspace):
    work, media, registry = workspace

    def cli(*args, ok=True):
        child = subprocess.run([sys.executable, "-m", "loopx.cli", "--format", "json", "--registry", str(registry),
            "--runtime-root", str(media.runtime_root), "content-ops", "experience", *args,
            "--goal-id", "experience-demo"], capture_output=True, text=True, timeout=60)
        assert (child.returncode == 0) == ok, (child.stdout, child.stderr)
        return json.loads(child.stdout)

    prepared = []
    for name in ["evidence-return", "service-diagnosis"]:
        args = ["prepare", "--plan-json", str(ROOT / f"examples/content-ops-experience/{name}.json")]
        first = cli(*args)
        assert cli(*args) == first, "lost-response retries reuse the source identity"
        assert first["publish_authorized"] is False and first["learning_effect"] == "not_tested"
        prepared.append(first)
    assert len(cli("list")["experiences"]) == 2
    item = prepared[0]
    run_file = media.project / "run.json"
    run_file.write_text(json.dumps({"scenario_id": "complete", "policy_id": "evidence_first"}))
    result = cli("run", "--experience-id", item["experience_id"], "--expected-revision", "1", "--run-json", str(run_file))
    assert result["status"] == "goal_reached" and result["remaining_budget"] == 1
    assert result["plan_digest"] == item["plan_digest"]
    cli("run", "--experience-id", item["experience_id"], "--expected-revision", "0", ok=False)
    assert not (media.runtime_root / "extensions").exists()


def test_revision_binding_damage_and_scope_fail_closed(workspace):
    work, media, _ = workspace
    first = work.prepare(plan())
    ident = first["experience_id"]
    original = (work._bundle(ident) / "record.json").read_bytes()
    invalid = deepcopy(plan())
    invalid["transitions"][0]["to"] = "unknown"
    with pytest.raises((ValueError, RuntimeError)):
        work.prepare(invalid, experience_id=ident, expected_revision=1)
    assert (work._bundle(ident) / "record.json").read_bytes() == original
    revised = {**plan(), "title": "A revised learning brief"}
    second = work.prepare(revised, experience_id=ident, expected_revision=1)
    assert second["revision"] == 2
    with pytest.raises(ValueError, match="revision"):
        work.run(ident, expected_revision=1, request={})
    with pytest.raises(ValueError, match="revision"):
        work.prepare(revised, experience_id=ident, expected_revision=1)
    for bad in ["../outside", "media_" + "a" * 24, "experience_" + "../" * 8]:
        with pytest.raises(ValueError):
            work.inspect(bad)
    other = work.prepare({**plan(), "title": "An independent artifact"})
    record = work._bundle(ident) / "record.json"
    data = json.loads(record.read_text())
    data["plan"]["budget"] = 100
    record.write_text(json.dumps(data))
    assert {item["status"] for item in work.list()["experiences"]} == {"ready", "damaged"}
    assert work.inspect(other["experience_id"])["revision"] == 1
    with pytest.raises(ValueError, match="known current revision"):
        work.prepare(plan(), experience_id=ident)
    with pytest.raises(ValueError, match="revision changed"):
        work.prepare(plan(), experience_id=ident, expected_revision=1)
    repaired = work.prepare(plan(), experience_id=ident, expected_revision=2)
    assert repaired["revision"] == 3 and repaired["plan_digest"] == first["plan_digest"]
    assert {item["status"] for item in work.list()["experiences"]} == {"ready"}
    record.unlink()
    target = media.project / "outside.json"
    target.write_bytes(original)
    record.symlink_to(target)
    with pytest.raises(ValueError, match="Symlink"):
        work.inspect(ident)
    assert target.read_bytes() == original


def test_real_loopback_uses_the_same_model_and_rejects_other_goal_or_author_code(workspace):
    work, media, registry = workspace
    item = work.prepare(plan())
    server = ChatHTTPServer(("127.0.0.1", 0), ChatRequestHandler)
    server.registry_path, server.runtime_root = registry, media.runtime_root
    server.selected_goal_id, server.verbose = "experience-demo", False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(body, origin=None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=20)
        connection.request("POST", "/api/chat/content-experience", json.dumps(body),
            {"Content-Type": "application/json", "Origin": origin or f"http://127.0.0.1:{server.server_address[1]}"})
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        return status, json.loads(data)

    try:
        base = {"goal_id": "experience-demo"}
        assert call({**base, "action": "list"})[1]["experiences"][0]["status"] == "ready"
        inspect = {**base, "action": "inspect", "experience_id": item["experience_id"]}
        assert call(inspect)[1]["plan_digest"] == item["plan_digest"]
        request = {"scenario_id": "complete", "policy_id": "evidence_first"}
        run = {**base, "action": "run", "experience_id": item["experience_id"], "expected_revision": 1, "run": request}
        status, result = call(run)
        assert status == 200 and result == work.run(item["experience_id"], expected_revision=1, request=request)
        for body in [{**inspect, "goal_id": "other"}, {**run, "expected_revision": True},
                     {**run, "run": {"script": "arbitrary author code"}}, {**run, "expected_revision": 0},
                     {**inspect, "experience_id": "../outside"}, {**base, "action": "prepare", "plan": plan()}]:
            assert call(body)[0] == 400
        assert call(inspect, "https://outside.invalid")[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
