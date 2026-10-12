"""Native checkpoint history must be complete and cannot become execution authority."""
import hashlib
import json

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
                return {"thread": {"id": "fixture-session"}}
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
