"""Codex session evidence must survive a host default encoding that is not UTF-8.

The shipped Turn driver reads the Codex CLI's UTF-8 JSONL event stream and
persists its checkpoint-refresh attempt record as UTF-8 JSON. Both go through
`Path.open()` / `os.fdopen()`, which the shipped file gate
(`tests/test_loopx_text_io_utf8.py`) does not inspect, so nothing stopped the
host locale codec from rewriting them.

Each case drives one real owner in a child interpreter whose default encoding is
ASCII, with a workspace whose path carries a non-ASCII component: the refresh
record keeps the observed stdout path and the binding's checkpoint root, so that
workspace shape is the ordinary case rather than a synthetic one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKSPACE_COMPONENT = "项目"

_CHILD = r'''
import json, locale, sys
from pathlib import Path
from types import SimpleNamespace

locale.setlocale(locale.LC_CTYPE, "C")
assert sys.flags.utf8_mode == 0
assert locale.getpreferredencoding(False).lower().replace("-", "") != "utf8"

from loopx.control_plane.turn_driver.codex_agent_session import CodexAgentSession
from loopx.control_plane.turn_driver.codex_sessions import (
    _store_codex_cli_session, load_codex_cli_session,
)

base, mode = Path(sys.argv[1]), sys.argv[2]
review = {"identity": {"effect_id": "current-review"}, "decision_sha256": "c" * 64}


def session(root):
    subject = CodexAgentSession.__new__(CodexAgentSession)
    subject.root = root
    subject.lineage = {"goal_id": "destination", "agent_id": "worker"}
    subject.goal_ref = {"goal_id": "destination", "instance_id": "current"}
    subject.digest = "b" * 64
    _store_codex_cli_session(root, lineage=subject.lineage, session_scope="agent",
        session_id="original", goal_ref=subject.goal_ref, session_profile_digest=subject.digest,
        checkpoint_artifact_sha256="a" * 64, checkpoint_artifact_root=str(root))
    subject.admission = SimpleNamespace(
        require_current=lambda: None, accept_result=lambda callback: callback())
    subject.binding = load_codex_cli_session(root, lineage=subject.lineage, session_scope="agent")
    subject.session_id = "original"
    subject.receipt = {"session": {"session_id": "original"}}
    subject.checkpoint_refresh = None
    return subject


def events(path, identity):
    # The Codex CLI writes its event stream as UTF-8 whatever the host codec is.
    path.write_bytes(b"".join([
        json.dumps({"type": "item.completed", "text": "任务已完成"},
                   ensure_ascii=False).encode("utf-8") + b"\n",
        json.dumps({"type": "thread.started", "thread_id": identity}).encode("utf-8") + b"\n",
    ]))


root = base / mode / "checkout"
root.mkdir(parents=True)
subject = session(root)

if mode == "observe":
    # The refresh is prepared first, then the CLI's own UTF-8 events are read.
    subject.prepare_checkpoint_refresh(review, root / "attempt.json", root / "stdout.jsonl")
    events(root / "stdout.jsonl", "fresh")
    subject.observe(root / "stdout.jsonl")
    payload = {"session_id": subject.session_id}
else:
    # The durable record carries the workspace and stdout paths; the shipped
    # recovery read is `json.loads(attempt.read_bytes())`.
    attempt, retry = root / "attempt.json", root / "retry.jsonl"
    subject.prepare_checkpoint_refresh(review, attempt, root / "stdout.jsonl")
    events(root / "stdout.jsonl", "resumed")
    subject.prepare_checkpoint_refresh(review, attempt, retry)
    payload = {"session_id": subject.session_id,
               "attempt_stdout": json.loads(attempt.read_bytes())["stdout"],
               "retry_launched": retry.exists()}

print(json.dumps({"encoding": locale.getpreferredencoding(False), **payload}, ensure_ascii=True))
'''


def _drive(base: Path, mode: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        **os.environ,
        "LC_ALL": "C",
        "PYTHONCOERCECLOCALE": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "0",
    }
    return subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", _CHILD, str(base), mode],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        timeout=180,
    )


def _payload(base: Path, mode: str) -> dict:
    result = _drive(base, mode)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    payload = json.loads(result.stdout.decode("utf-8"))
    # A vacuous pass would hide the codec this test exists to exercise.
    assert payload["encoding"].lower().replace("-", "") != "utf8"
    return payload


def test_codex_events_are_read_back_with_a_locale_codec(tmp_path: Path) -> None:
    base = tmp_path / WORKSPACE_COMPONENT
    payload = _payload(base, "observe")

    assert payload["session_id"] == "fresh"


def test_checkpoint_refresh_attempt_record_is_readable_again(tmp_path: Path) -> None:
    base = tmp_path / WORKSPACE_COMPONENT
    payload = _payload(base, "recover")

    assert payload["session_id"] == "resumed"
    assert payload["attempt_stdout"] == str(base / "recover" / "checkout" / "stdout.jsonl")
    assert payload["retry_launched"] is False
