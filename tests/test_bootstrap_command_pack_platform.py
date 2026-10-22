"""Generated guided-connect commands must run on their documented host shells."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import loopx.project_prompt as project_prompt
from loopx.bootstrap_command_pack import build_start_goal_guided_packet


PWSH = shutil.which("pwsh")
GOAL_ID = "windows-guided-connect"
GOAL_TEXT = "Verify native PowerShell guided connection"


def guided_packet(
    project: Path, *, fine_grained: bool = False, goal_text: str = GOAL_TEXT
) -> dict[str, object]:
    return build_start_goal_guided_packet(
        project=project,
        goal_id=GOAL_ID,
        agent_id=None,
        cli_bin="loopx",
        host_surface="shell",
        goal_text=goal_text,
        fine_grained=fine_grained,
        include_command_pack_detail=True,
    )


def connect_command(packet: dict[str, object]) -> str:
    guided_transaction = packet["guided_transaction"]
    assert isinstance(guided_transaction, dict)
    steps = guided_transaction["ordered_steps"]
    assert isinstance(steps, list)
    connect = next(step for step in steps if step["id"] == "connect_if_needed")
    assert isinstance(connect, dict)
    return str(connect["command"])


def test_guided_bootstrap_commands_do_not_require_posix_continuations(
    tmp_path: Path,
) -> None:
    packet = guided_packet(tmp_path / "project")
    command = connect_command(packet)

    assert "\\\n" not in command
    lines = command.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("cd ")
    assert lines[1].startswith("loopx bootstrap --project .")

    recommended = packet["recommended_next_step"]
    assert isinstance(recommended, dict)
    identity_gate = recommended["identity_selection_gate"]
    assert isinstance(identity_gate, dict)
    fresh_registration = identity_gate["fresh_agent_registration"]
    assert isinstance(fresh_registration, dict)
    assert fresh_registration["connect_if_needed_command"] == command

    command_pack = packet["command_pack"]
    assert isinstance(command_pack, dict)
    commands = command_pack["commands"]
    assert isinstance(commands, dict)
    for key in (
        "bootstrap_dry_run_preview",
        "bootstrap_after_user_confirmation",
        "goal_start_connect_if_needed",
    ):
        assert "\\\n" not in str(commands[key]), key

    tokens = shlex.split(lines[1])
    assert tokens == [
        "loopx",
        "bootstrap",
        "--project",
        ".",
        "--goal-id",
        GOAL_ID,
        "--objective",
        GOAL_TEXT,
        "--adapter-kind",
        "read_only_project_map_v0",
        "--adapter-status",
        "connected-read-only",
    ]


def test_host_shell_arg_escapes_powershell_apostrophes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_prompt, "_is_windows_host", lambda: True)

    assert project_prompt.shell_arg_for_host("read_only_project_map_v0") == (
        "read_only_project_map_v0"
    )
    assert project_prompt.shell_arg_for_host("Fix user's login") == (
        "'Fix user''s login'"
    )


def test_generated_guided_connect_command_runs_in_powershell(tmp_path: Path) -> None:
    if os.name != "nt" or PWSH is None:
        pytest.skip("requires native Windows and PowerShell 7")
    pwsh = PWSH
    assert pwsh is not None
    project = tmp_path / "project's"
    project.mkdir()
    goal_text = "Verify user's native PowerShell guided connection"
    packet = guided_packet(project, fine_grained=True, goal_text=goal_text)
    command = connect_command(packet)
    assert "--fine-grained" in command

    script = tmp_path / "connect.ps1"
    script.write_text(command, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    environment = os.environ.copy()
    environment["PATH"] = (
        f"{Path(sys.executable).parent}{os.pathsep}{environment.get('PATH', '')}"
    )
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    completed = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    registry = project / ".loopx" / "registry.json"
    state = project / ".loopx" / "goals" / GOAL_ID / "ACTIVE_GOAL_STATE.md"
    assert registry.is_file()
    assert state.is_file()
