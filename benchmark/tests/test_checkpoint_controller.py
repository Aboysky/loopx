"""Actual native HTTP and typed artifact transport; grading is synthetic here."""
from __future__ import annotations

import copy
import io
import json
import os
import socket
import tarfile
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from benchmark.edgebench import checkpoint_controller as transport


@contextmanager
def server(app):
    import uvicorn
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    host = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                      log_level="error", access_log=False))
    thread = threading.Thread(target=host.run)
    thread.start()
    try:
        wait(lambda: host.started)
        yield f"http://127.0.0.1:{port}"
    finally:
        host.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def wait(predicate):
    until = time.monotonic() + 30
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(.01)
    raise AssertionError("Native synthetic HTTP journey did not settle")


@pytest.fixture
def controllers(tmp_path, monkeypatch):
    pytest.importorskip("sforge.harness.checkpoint", reason="Requires native checkpoint API source pin")
    from sforge.harness import judge_server as native
    from sforge.harness.config import SForgeConfig
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "BENCHMARK.yaml").write_text("name: transport-test\nbase_images: {python: {}}\n")
    (tasks / "fixture.json").write_text(json.dumps({
        "task_id": "fixture", "name": "Synthetic transport", "base_image": "python",
        "platform": "linux/arm64", "cwd": "/tmp", "internet": False,
        "submit_paths": ["candidate.json"], "submit_exclude": [],
        "work": {"image_tag": "fixture", "agent_query": "Synthetic fixture"},
        "judge": {"image_tag": "fixture", "eval_timeout": 15, "parser": "structured_json",
                  "selection": "score_first", "score_direction": "maximize", "eval_cmd": "true"},
    }))
    backend = Mock(backend_name="docker")
    backend.client.images.get.return_value.id = "sha256:synthetic-transport-image"
    monkeypatch.setattr(native, "create_backend_from_config", lambda config: backend)
    grades = []
    def grade(**kwargs):
        grades.append(kwargs["archive"])
        kwargs["log_dir"].mkdir(parents=True, exist_ok=True)
        (kwargs["log_dir"] / "submission.tar.gz").write_bytes(kwargs["archive"])
        return SimpleNamespace(to_dict=lambda: {"score": float(kwargs["archive"]),
            "valid": True, "pass_rate": 1.0, "passed": 1, "failed": 0, "total_tests": 1})
    monkeypatch.setattr(native, "judge_submission", grade)
    config = SForgeConfig(tasks_dir=tasks, log_dir=tmp_path / "source")
    source = native.create_app(config, checkpoints=True)
    destination = native.create_app(replace(config, log_dir=tmp_path / "branch"), checkpoints=True)
    try:
        with server(source) as first, server(destination) as second:
            files = []
            for name, app, url in (("source", source, first), ("branch", destination, second)):
                bank = app.state.judge.config.log_dir / "checkpoints"
                bank.mkdir(parents=True, mode=0o700)
                path = tmp_path / (name + "-controller.json")
                path.write_text(json.dumps({"url": url, "admin_secret": app.state.judge.admin_secret,
                                            "bank_root": str(bank)}))
                path.chmod(0o600)
                files.append(path)
            yield source, destination, first, second, files, grades
    finally:
        for app in (source, destination):
            app.state.judge._reaper_stop.set()
            app.state.judge._reaper_thread.join(timeout=1)


def register(app, url, **options):
    import requests
    response = requests.post(url + "/api/v1/register", json={"task_id": "fixture", "run_id": "source",
        "admin_secret": app.state.judge.admin_secret, **options}, timeout=5)
    response.raise_for_status()
    return response.json()["token"]


def submit(url, token, score):
    import requests
    response = requests.post(url + "/api/v1/submit", data={"token": token},
        files={"archive": ("candidate.tar.gz", str(score).encode())}, timeout=5)
    if response.status_code == 200:
        identifier = response.json()["submission_id"]
        wait(lambda: requests.get(url + "/api/v1/result/" + identifier, timeout=5).json()["status"] == "completed")
    return response


def test_native_controller_transport_preserves_original_point_and_fresh_authority(controllers, tmp_path, capsys):
    import requests
    source, destination, first, second, files, grades = controllers
    token = register(source, first, max_agent_submissions=3, submission_cooldown=0)
    assert submit(first, token, 7).status_code == 200
    assert submit(first, token, 3).status_code == 200
    # Retain a future cooldown without changing the original accepted clock.
    source.state.judge.tokens[token]["submission_cooldown"] = 3600
    before = copy.deepcopy((source.state.judge.tokens, source.state.judge.submissions, source.state.judge.run_history))
    token_file = tmp_path / "token"
    token_file.write_text(token)
    exported = tmp_path / "exported"
    transport.main(["--controller-file", str(files[0]), "capture", "--token-file", str(token_file),
                    "--capture-id", "a" * 32, "--destination", str(exported)])
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["research_point_qualified"] is False
    assert receipt["native_reference"]["incumbent"]["round"] == "agent-1"
    assert (exported / "components/native_judge/incumbent.tar.gz").read_bytes() == b"7"
    manifest = json.loads((exported / "components/native_judge/manifest.json").read_text())
    assert len(manifest["history"]) == 2 and manifest["opportunity"]["next_agent"] == 3
    assert 0 < manifest["opportunity"]["remaining_cooldown_seconds"] <= 3600
    for secret in (token, source.state.judge.admin_secret, destination.state.judge.admin_secret):
        assert secret not in json.dumps(receipt)
        assert all(secret.encode() not in p.read_bytes() for p in exported.rglob("*") if p.is_file())
    assert (source.state.judge.tokens, source.state.judge.submissions, source.state.judge.run_history) == before
    # Later source state cannot replace this first native capture identity.
    source.state.judge.tokens[token]["submission_cooldown"] = 0
    assert submit(first, token, 99).status_code == 200
    repeated = transport.capture(files[0], token=token, capture_id="a" * 32, destination=tmp_path / "same-point")
    assert repeated["native_reference"] == receipt["native_reference"]
    private_result = tmp_path / "fresh-result.json"
    transport.main(["--controller-file", str(files[1]), "restore", "--root", str(exported),
        "--expected-sha256", receipt["sha256"], "--run-id", "branch", "--result-file", str(private_result)])
    output = capsys.readouterr().out
    fresh = json.loads(private_result.read_text())["token"]
    assert fresh != token and fresh not in output
    assert private_result.stat().st_mode & 0o077 == 0 and len(grades) == 3
    history = requests.get(second + "/api/v1/history", params={"token": fresh}, timeout=5).json()
    assert history["best_score"] == 7 and history["best_round"] == "agent-1" and history["agent_submissions"] == 2
    assert submit(second, fresh, 1).status_code == 429
    assert source.state.judge.get_run_history("source", "fixture")["best_score"] == 99
    with pytest.raises(ValueError, match="HTTP 409"):
        transport.restore(files[1], root=exported, expected_sha256=receipt["sha256"], run_id="branch")
    assert len(grades) == 3


@pytest.mark.parametrize("fault", ["wrong_admin", "corrupt", "wrong_digest", "aliased", "existing_bank"])
def test_invalid_controller_import_never_registers_or_regrades(controllers, tmp_path, fault):
    source, destination, first, second, files, grades = controllers
    token = register(source, first)
    assert submit(first, token, 7).status_code == 200
    exported = tmp_path / "exported"
    point = transport.capture(files[0], token=token, capture_id="b" * 32, destination=exported)
    root, digest = exported, point["sha256"]
    if fault == "wrong_admin":
        config = json.loads(files[1].read_text())
        config["admin_secret"] = "not-current-admin"
        files[1].write_text(json.dumps(config))
    elif fault == "corrupt":
        (exported / "components/native_judge/incumbent.tar.gz").write_bytes(b"99")
    elif fault == "wrong_digest":
        digest = "0" * 64
    elif fault == "aliased":
        root = tmp_path / "alias"
        root.symlink_to(exported, target_is_directory=True)
    else:
        bank = destination.state.judge.config.log_dir / "checkpoints" / ("b" * 32)
        bank.mkdir()
        (bank / "foreign").write_text("keep")
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        transport.restore(files[1], root=root, expected_sha256=digest, run_id="branch")
    assert destination.state.judge.tokens == {} and len(grades) == 1
    if fault == "existing_bank":
        assert (bank / "foreign").read_text() == "keep"


def test_redirect_never_forwards_controller_authority(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse
    first, second = FastAPI(), FastAPI()
    received = []
    @second.post("/steal")
    def steal():
        received.append(True)
        return {}
    with server(second) as target:
        @first.post("/api/v1/checkpoint/capture")
        def redirect():
            return RedirectResponse(target + "/steal", status_code=307)
        with server(first) as origin:
            config = {"url": origin, "admin_secret": "synthetic-credential"}
            with pytest.raises(ValueError, match="HTTP 307"):
                transport._post(config, "/api/v1/checkpoint/capture", {"token": "source"}, 5)
    assert received == []


@pytest.mark.skipif(os.environ.get("LOOPX_EDGEBENCH_DOCKER_SMOKE") != "1",
                    reason="Requires explicit isolated native Docker qualification")
def test_real_docker_controller_export_import_and_next_grade(tmp_path, monkeypatch):
    import uuid
    import docker
    import requests
    from sforge.harness import checkpoint, judge_server as native
    from sforge.harness.config import SForgeConfig

    name = "loopx-controller-" + uuid.uuid4().hex[:10]
    client = docker.from_env()
    image = client.images.get("python:3.12-slim")
    image.tag(name + ".judge.fixture", tag="fixture")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "BENCHMARK.yaml").write_text(f"name: {name}\nbase_images: {{python: {{}}}}\n")
    (tasks / "fixture.json").write_text(json.dumps({
        "task_id": "fixture", "name": "Synthetic real grade", "base_image": "python",
        "platform": "linux/arm64", "cwd": "/tmp", "internet": False,
        "submit_paths": ["candidate.json"], "submit_exclude": [],
        "work": {"image_tag": "fixture", "agent_query": "Synthetic fixture"},
        "judge": {"image_tag": "fixture", "eval_timeout": 20, "parser": "structured_json",
            "selection": "score_first", "score_direction": "maximize",
            "eval_cmd": "python3 -c 'import json; print(json.dumps(dict(score=json.load(open(\"candidate.json\"))[\"score\"], valid=True)))'"},
    }))
    config = SForgeConfig(tasks_dir=tasks, log_dir=tmp_path / "source", judge_cpu_limit=1, judge_mem_limit="256m")
    source = native.create_app(config, checkpoints=True)
    destination = native.create_app(replace(config, log_dir=tmp_path / "branch"), checkpoints=True)
    grades = []
    original = native.judge_submission
    def actual_grade(**kwargs):
        grades.append(kwargs["archive"])
        return original(**kwargs)
    monkeypatch.setattr(native, "judge_submission", actual_grade)
    def grade(url, token, score):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            body = json.dumps({"score": score}).encode()
            member = tarfile.TarInfo("candidate.json")
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
        response = requests.post(url + "/api/v1/submit", data={"token": token},
            files={"archive": ("candidate.tar.gz", raw.getvalue())}, timeout=10)
        if response.status_code == 200:
            sid = response.json()["submission_id"]
            report = wait(lambda: (packet if (packet := requests.get(url + "/api/v1/result/" + sid,
                timeout=10).json())["status"] in {"completed", "error"} else None))
            assert report["status"] == "completed" and report["report"]["score"] == score
        return response
    try:
        with server(source) as first, server(destination) as second:
            files = []
            for label, app, url in (("source", source, first), ("branch", destination, second)):
                bank = app.state.judge.config.log_dir / "checkpoints"
                bank.mkdir(parents=True, mode=0o700)
                path = tmp_path / (label + "-admin.json")
                path.write_text(json.dumps({"url": url, "admin_secret": app.state.judge.admin_secret,
                                            "bank_root": str(bank)}))
                path.chmod(0o600)
                files.append(path)
            token = register(source, first, max_agent_submissions=2, submission_cooldown=3600)
            assert grade(first, token, 7).status_code == 200
            before = copy.deepcopy((source.state.judge.tokens, source.state.judge.submissions, source.state.judge.run_history))
            exported = tmp_path / "capsule"
            point = transport.capture(files[0], token=token, capture_id="c" * 32, destination=exported)
            # Admission clock only: HTTP, transport/fsync, Docker and native
            # grading remain real. Offline/import IO must not spend cooldown.
            now = [time.time() + 7200]
            clock = SimpleNamespace(time=lambda: now[0])
            monkeypatch.setattr(native, "time", clock)
            monkeypatch.setattr(checkpoint, "time", clock)
            fresh = transport.restore(files[1], root=exported, expected_sha256=point["sha256"], run_id="branch")["token"]
            assert fresh != token and len(grades) == 1
            assert grade(second, fresh, 3).status_code == 429
            now[0] += 3601
            assert grade(second, fresh, 3).json()["round_id"] == "agent-2"
            history = requests.get(second + "/api/v1/history", params={"token": fresh}, timeout=5).json()
            assert history["best_score"] == 7 and history["best_round"] == "agent-1"
            assert grade(second, fresh, 99).status_code == 429 and len(grades) == 2
            assert (source.state.judge.tokens, source.state.judge.submissions, source.state.judge.run_history) == before
            with pytest.raises(ValueError, match="HTTP 409"):
                transport.restore(files[1], root=exported, expected_sha256=point["sha256"], run_id="branch")
    finally:
        for app in (source, destination):
            app.state.judge._reaper_stop.set()
            app.state.judge._reaper_thread.join(timeout=1)
        client.images.remove(name + ".judge.fixture:fixture")
