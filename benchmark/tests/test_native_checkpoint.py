"""Native checkpoint history must be complete and cannot become execution authority."""
import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from benchmark.runtime.native_checkpoint import native_session_checkpoint


def fixture(tmp_path, monkeypatch, pages):
    home = tmp_path / "native"
    home.mkdir()
    for name in ("state_5.sqlite", "thread_history_1.sqlite", "config.toml", "auth.json", "logs_1.sqlite"):
        (home / name).write_text("synthetic private fixture")
    (home / "sessions").mkdir()
    (home / "skills").symlink_to(home / "sessions", target_is_directory=True)
    calls = []

    class Native:
        response_timeout_sec = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def notify(self, method, params):
            calls.append(method)

        def request(self, method, params):
            calls.append(method)
            if method == "initialize":
                return {}
            if method == "thread/read":
                return {"thread": {"id": "fixture-session", "cwd": str(tmp_path)}}
            assert method == "thread/turns/list"  # No model or fork is requested.
            return pages.pop(0)

    monkeypatch.setattr("benchmark.runtime.native_checkpoint.StdioNativeGoalTransport.spawn", lambda *a, **k: Native())
    monkeypatch.setattr("benchmark.runtime.native_checkpoint.subprocess.check_output", lambda *a, **k: "codex-cli fixture")
    return {"CODEX_HOME": str(home), "CODEX_BIN": "/fixture/codex", "LOOPX_PROJECT": str(tmp_path)}, calls


def test_all_native_pages_and_stores_are_retained_without_credentials(tmp_path, monkeypatch):
    turns = [{"id": "before-compaction", "status": "completed", "items": [{"type": "compaction"}]},
             {"id": "after-compaction", "status": "completed", "items": []}]
    env, calls = fixture(tmp_path, monkeypatch, [{"data": turns[:1], "nextCursor": "next"},
                                               {"data": turns[1:], "nextCursor": None}])
    result = native_session_checkpoint(env, "fixture-session", timeout=10)
    metadata = result["metadata"]
    assert metadata["turn_ids"] == [t["id"] for t in turns]
    assert metadata["completed_turn_id"] == "after-compaction"
    assert metadata["visible_history_sha256"] == hashlib.sha256(
        json.dumps(turns, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert metadata["execution_authority_granted"] is False
    assert {c["id"] for c in result["components"]} == {
        "native_sessions", "native_state_5_sqlite", "native_thread_history_1_sqlite"}
    assert calls == ["initialize", "initialized", "thread/read", "thread/turns/list", "thread/turns/list"]


@pytest.mark.parametrize("pages,reason", [
    ([{"data": [], "nextCursor": None}], "complete retained"),
    ([{"data": [{"id": "active", "status": "inProgress"}], "nextCursor": None}], "complete retained"),
    ([{"data": [{"id": "failed", "status": "failed"}], "nextCursor": None}], "completed final"),
    ([{"data": [], "nextCursor": "same"}, {"data": [], "nextCursor": "same"}], "repeated history"),
    ([{"data": [{"id": "same", "status": "completed"}] * 2, "nextCursor": None}], "duplicate turns"),
])
def test_incomplete_or_ambiguous_native_history_is_not_a_checkpoint(tmp_path, monkeypatch, pages, reason):
    env, _ = fixture(tmp_path, monkeypatch, pages)
    with pytest.raises(ValueError, match=reason):
        native_session_checkpoint(env, "fixture-session", timeout=10)


def test_foreign_native_session_is_rejected_before_history(tmp_path, monkeypatch):
    env, calls = fixture(tmp_path, monkeypatch, [])
    with pytest.raises(ValueError, match="identity mismatch"):
        native_session_checkpoint(env, "foreign-session", timeout=10)
    assert "thread/turns/list" not in calls


@contextmanager
def real_native_source(root, binary, workspace):
    """Real native writer/readback; a local static stream replaces only the model.

    No paid model, tool invocation, user credential or benchmark cell. Fixtures
    become completed Turns through the native protocol, not copied fake receipts.
    """
    from loopx.capabilities.benchmark_toolkit.native_codex_goal import (
        NativeGoalProtocolError, StdioNativeGoalTransport,
    )
    home = root / "home"
    home.mkdir(parents=True)
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append(self.path)
            message = {"type": "message", "id": "msg_" + uuid.uuid4().hex, "role": "assistant",
                       "content": [{"type": "output_text", "text": "Synthetic source result."}]}
            result = {"id": "resp_" + uuid.uuid4().hex, "status": "completed", "output": [message],
                      "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
            events = [{"type": "response.created", "response": {**result, "status": "in_progress", "output": []}},
                      {"type": "response.output_item.done", "output_index": 0, "item": message},
                      {"type": "response.completed", "response": result}]
            raw = "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n"
                          for event in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    (home / "config.toml").write_text(
        'model="fixture"\nmodel_provider="fixture"\napproval_policy="never"\nsandbox_mode="read-only"\n'
        '[features]\ngoals=false\nresponses_websockets_v2=false\n'
        '[model_providers.fixture]\nname="Synthetic local"\n'
        f'base_url="http://127.0.0.1:{server.server_port}/v1"\nwire_api="responses"\n'
        'env_key="SYNTHETIC_PROVIDER_KEY"\n')
    env = {key: value for key, value in os.environ.items()
           if key not in {"OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"}}
    env.update(CODEX_HOME=str(home), CODEX_BIN=binary, LOOPX_PROJECT=str(workspace),
               SYNTHETIC_PROVIDER_KEY="synthetic-local-only", LOOPX_USAGE_PING="0")
    try:
        with (root / "stderr.txt").open("w") as stderr, StdioNativeGoalTransport.spawn(
            [binary, "-c", "features.goals=false", "app-server", "--listen", "stdio://"],
            cwd=str(workspace), env=env, stderr=stderr, response_timeout_sec=20,
        ) as native:
            native.request("initialize", {"clientInfo": {"name": "checkpoint_qualification", "version": "0.1.0"},
                                          "capabilities": {"experimentalApi": True}})
            native.notify("initialized", {})
            source = native.request("thread/start", {"cwd": str(workspace), "sandbox": "read-only",
                "approvalPolicy": "never", "persistExtendedHistory": True})["thread"]["id"]
            def complete_turn():
                expected_turn = native.request("turn/start", {"threadId": source,
                    "input": [{"type": "text", "text": "Synthetic storage fixture. Return its source result."}]})["turn"]["id"]
                stop = time.monotonic() + 30
                while time.monotonic() < stop:
                    try:
                        page = native.request("thread/turns/list", {"threadId": source,
                            "sortDirection": "asc", "itemsView": "full", "limit": 100})
                    except NativeGoalProtocolError:
                        # A first live Turn may not have a persisted page yet.
                        time.sleep(.05)
                        continue
                    if (page.get("data") and page["data"][-1].get("id") == expected_turn and
                            page["data"][-1].get("status") == "completed"):
                        return page["data"][-1]["id"]
                    time.sleep(.05)
                raise AssertionError("Real native fixture did not complete its source Turn")
            complete_turn()
            yield env, source, complete_turn, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(not os.environ.get("LOOPX_NATIVE_CHECKPOINT_BIN"),
                    reason="Requires an explicit real native Host binary; no model service used")
def test_real_native_workspace_readback_rejects_foreign_code_basis(tmp_path):
    from pathlib import Path
    workspace = tmp_path / "source-workspace"
    workspace.mkdir()
    with real_native_source(tmp_path / "native", os.environ["LOOPX_NATIVE_CHECKPOINT_BIN"], workspace) as (env, source, _, calls):
        valid = native_session_checkpoint(env, source, timeout=20)
        assert valid["metadata"]["guest_workspace"] == str(workspace)
        assert len(valid["metadata"]["turn_ids"]) == 1 and calls == ["/v1/responses"]
        foreign = Path(env["LOOPX_PROJECT"]).with_name("foreign-workspace")
        foreign.mkdir()
        with pytest.raises(ValueError, match="workspace"):
            native_session_checkpoint({**env, "LOOPX_PROJECT": str(foreign)}, source, timeout=20)
