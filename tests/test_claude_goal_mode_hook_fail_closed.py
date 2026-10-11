"""The Claude Code goal-mode gate must refuse an event it cannot read.

``hooks/goal_policy.py`` documents itself as fail-closed around the
deterministic ``should_run`` probe: when the probe cannot be reached, a
non-read-only tool is denied so the gate never silently disappears. The event
read was the one boundary outside that rule. With the strict stdin pin
(``test_claude_goal_mode_stdio_utf8.py``) an undecodable byte raises
``UnicodeDecodeError`` at the read, and a decodable-but-malformed payload raised
inside ``active_context``: the hook exited ``rc=1`` with a traceback and printed
no decision. Claude Code treats a hook that fails that way as a non-blocking
error and continues the tool call, so the gate vanished exactly when the hook
could not verify anything. #6166 named this as its deliberately deferred
successor.

These cases run the shipped script the way Claude Code invokes it - own process,
event on stdin, answer read back as JSON - and assert the rc/decision contract,
so the regression fails on the real entry point rather than on an in-process
approximation. The unarmed case pins the other direction: the refusal must not
widen the gate onto projects where goal-mode is off.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "loopx/claude_goal_mode/hooks/goal_policy.py"

GOAL_ID = "hook-fail-closed-goal"


def _project(root: Path, *, armed: bool) -> Path:
    """A project with one registry goal; armed also carries `.claude/loop.md`."""

    registry = root / ".loopx" / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "goals": [
                    {
                        "id": GOAL_ID,
                        "repo": str(root),
                        "coordination": {"registered_agents": ["cc"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    if armed:
        (root / ".claude").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "loop.md").write_text("# loop\n", encoding="utf-8")
    return root


def _run(
    project: Path, payload: bytes, *, force_armed: bool
) -> subprocess.CompletedProcess[bytes]:
    environment = {**os.environ}
    if force_armed:
        environment["LOOPX_GOAL_FORCE"] = "1"
    else:
        environment.pop("LOOPX_GOAL_FORCE", None)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=project,
        env=environment,
        input=payload,
        capture_output=True,
        timeout=120,
    )


UNREADABLE_EVENT_PAYLOADS = [
    pytest.param(b"\xff\xfe{", id="undecodable-stdin"),
    pytest.param(b"{not json", id="malformed-json"),
    pytest.param(b"[]", id="json-not-an-object"),
    pytest.param(b"", id="empty-stdin"),
    pytest.param(
        json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}).encode(
            "utf-8"
        ),
        id="object-without-cwd",
    ),
    pytest.param(
        json.dumps({"tool_name": "Bash", "workspace": "not-an-object"}).encode("utf-8"),
        id="non-object-workspace",
    ),
]


@pytest.mark.parametrize("payload", UNREADABLE_EVENT_PAYLOADS)
def test_unreadable_event_is_refused_with_an_explicit_deny(
    tmp_path: Path, payload: bytes
) -> None:
    project = _project(tmp_path / "armed", armed=True)

    result = _run(project, payload, force_armed=True)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in result.stderr, result.stderr.decode("utf-8", "replace")
    decision = json.loads(result.stdout.decode("utf-8"))
    output = decision["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert output["permissionDecisionReason"]


def test_non_object_tool_input_for_a_gated_tool_is_refused(tmp_path: Path) -> None:
    """A truthy non-object `tool_input` is an unreadable event, not a crash.

    ``decide`` reads the tool input with ``ti.get`` for the gated tools, so on
    the pre-fix hook a Bash event carrying a non-object input died with a
    traceback (rc=1, no decision) as soon as ``should_run`` returned true. The
    reason substring pins the refusal to the unreadable-input rule: a deny from
    the probe path carries a different reason, so the regression fails against
    the old hook whichever branch the probe takes.
    """

    project = _project(tmp_path / "armed", armed=True)
    event = json.dumps(
        {
            "tool_name": "Bash",
            "cwd": str(project),
            "tool_input": "not-an-object",
        }
    ).encode("utf-8")

    result = _run(project, event, force_armed=True)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in result.stderr, result.stderr.decode("utf-8", "replace")
    output = json.loads(result.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "tool_input" in output["permissionDecisionReason"]

    # Read-only tools keep their unconditional allow even then: the refusal
    # must not widen the gate past the tools it was meant to gate.
    read_event = json.dumps(
        {
            "tool_name": "Read",
            "cwd": str(project),
            "tool_input": "not-an-object",
        }
    ).encode("utf-8")
    read_result = _run(project, read_event, force_armed=True)
    assert read_result.returncode == 0, read_result.stderr.decode("utf-8", "replace")
    read_output = json.loads(read_result.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert read_output["permissionDecision"] == "allow"


def test_unarmed_project_still_defers_to_the_normal_flow(tmp_path: Path) -> None:
    project = _project(tmp_path / "unarmed", armed=False)

    # A valid event in a project with a registry goal but no `.claude/loop.md`
    # (goal-mode off): its write tool must still defer to Claude Code's normal
    # permission flow, not be captured by the new refusal.
    event = json.dumps(
        {
            "tool_name": "Edit",
            "cwd": str(project),
            "tool_input": {"file_path": str(project / "notes.txt")},
        }
    ).encode("utf-8")
    result = _run(project, event, force_armed=False)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    # `{}` is Claude Code's "defer to the normal permission flow".
    assert result.stdout == b"{}"
