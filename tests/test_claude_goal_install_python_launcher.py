r"""The Claude adapter installer must bake a launcher that actually runs Python.

`install.py --harden` writes a PreToolUse hook command and a statusline command
into `settings.json`, and `command_md()` writes the `/loopx` command with the
same interpreter. All of them bake one PATH lookup of `python3` - the first
interpreter name found, without ever running it.

On Windows, `shutil.which("python3")` can resolve to the 0-byte `WindowsApps`
App Execution Alias (`%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe`). That
file exists and passes `shutil.which`, but it never starts Python - on some
hosts executing it exits non-zero (9009), on others launching it raises OSError,
and it writes nothing either way. An installer that bakes that path writes hook /
statusline / `/loopx` commands that silently do nothing:
the `--harden` should_run gate fails OPEN (Claude Code treats the non-zero,
decision-less hook exit as a non-blocking error and runs the tool anyway), the
statusline renders nothing, and `/loopx` never runs.

The installer must only bake an interpreter it has confirmed can launch Python.
PR #6166 named this residual as its out-of-scope successor.

The same baked strings interpolate that interpreter unquoted, so a confirmed
runnable interpreter under a path that contains a space - the python.org
all-users install (`C:\Program Files\Python312`), or any profile directory with
a space - produces a command the shell splits at the first space. PR #6229
named that residual; PR #6250 keeps every baked token literal in the shell that
actually runs it (cmd.exe on Windows, `/bin/sh` elsewhere), where double quotes
alone still expand `$NAME` and dequote an inner `"`. These tests read the
generated commands back out of the installed files and execute them through the
host shell.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loopx.claude_goal_mode.scripts import install as claude_install


def _dead_python3_alias(tmp_path: Path) -> Path:
    """A stand-in for the 0-byte `WindowsApps` App Execution Alias.

    Executing it raises OSError - WinError 193 ("not a valid Win32 application")
    on Windows, "Permission denied" on POSIX - so it has the same
    `shutil.which`-passes / cannot-run shape as the real alias, on any host.
    """
    alias = tmp_path / "WindowsApps" / "python3.EXE"
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.write_bytes(b"")
    return alias


@pytest.fixture()
def alias_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A PATH where `python3` is the dead alias and `python` is a real interpreter."""
    alias = _dead_python3_alias(tmp_path)

    def which(name: str) -> str | None:
        if name == "python3":
            return str(alias)
        if name == "python":
            return sys.executable
        return None

    monkeypatch.setattr(claude_install.shutil, "which", which)
    return alias


def test_python_cmd_skips_a_python3_alias_that_cannot_run(alias_host: Path) -> None:
    assert claude_install._python_cmd() == sys.executable


def test_python_cmd_falls_back_to_sys_executable_when_no_candidate_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alias = _dead_python3_alias(tmp_path)
    monkeypatch.setattr(claude_install.shutil, "which", lambda name: str(alias))
    assert claude_install._python_cmd() == sys.executable


def test_baked_commands_do_not_carry_the_dead_alias(alias_host: Path) -> None:
    alias = str(alias_host)
    hardening = claude_install.hardening_block()
    hook_cmd = hardening["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    status_cmd = hardening["statusLine"]["command"]
    command = claude_install.command_md()

    assert sys.executable in hook_cmd and alias not in hook_cmd
    assert sys.executable in status_cmd and alias not in status_cmd
    assert f"allowed-tools: Bash({claude_install._shell_path(sys.executable)}:*)" in command
    assert alias not in command


def test_installed_gate_command_actually_runs_python(alias_host: Path, tmp_path: Path) -> None:
    """Run exactly the hook command `--harden` installs, the way Claude Code does.

    Claude Code executes the command through a shell with the event JSON on
    stdin. With the dead alias baked in, the shell finds a file that exits 9009
    and prints nothing; the event never reaches the gate.
    """
    settings = tmp_path / "claude" / "settings.json"
    claude_install.add_hardening(dry=False, settings_path=settings)
    hook_cmd, _ = _installed_commands(settings)

    project = tmp_path / "project"
    project.mkdir()
    event = json.dumps({"cwd": str(project), "tool_name": "Read", "tool_input": {}})
    result = _host_shell_run(hook_cmd, event, cwd=project)

    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert json.loads(result.stdout.decode("utf-8")) == {}


def test_python_cmd_keeps_the_python3_preference_when_it_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    tried: list[str] = []

    def launches(py: str) -> bool:
        tried.append(py)
        return True

    monkeypatch.setattr(claude_install.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(claude_install, "_launches_python", launches)
    assert claude_install._python_cmd() == "/fake/python3"
    assert tried == ["/fake/python3"]


def test_python_cmd_falls_through_python3_to_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_install.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(claude_install, "_launches_python", lambda py: py.endswith("python"))
    assert claude_install._python_cmd() == "/fake/python"


def test_launches_python_rejects_a_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 9009

    monkeypatch.setattr(claude_install.subprocess, "run", lambda *args, **kwargs: Result())
    assert claude_install._launches_python("python3") is False


def test_launches_python_accepts_a_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0

    monkeypatch.setattr(claude_install.subprocess, "run", lambda *args, **kwargs: Result())
    assert claude_install._launches_python("python3") is True


def _literal_interpreter(tmp_path: Path, dirname: str) -> Path:
    """A real launcher for `sys.executable` that lives under `tmp_path / dirname`."""
    home = tmp_path / dirname
    home.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        launcher = home / "python.bat"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" %*\r\n', encoding="ascii")
    else:
        launcher = home / "python3"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


# Directory names `_launches_python` accepts but the host shell would not read
# as one literal token: spaces split, `$` expands, and an inner `"` closes the
# token under `/bin/sh`. A Windows file name cannot contain `"`.
_LITERAL_DIRNAMES = [
    "Program Files",
    "User $LABEL Home",
    pytest.param(
        'User "quoted" Home',
        marks=pytest.mark.skipif(
            sys.platform == "win32", reason='a Windows file name cannot contain "'
        ),
    ),
]


@pytest.fixture()
def literal_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Select a literal launcher as PATH's `python3` for one directory name."""

    def make(dirname: str) -> Path:
        launcher = _literal_interpreter(tmp_path, dirname)
        monkeypatch.setattr(
            claude_install.shutil,
            "which",
            lambda name: str(launcher) if name == "python3" else None,
        )
        return launcher

    return make


def _host_shell_run(command: str, stdin: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """Run one baked command string through the shell Claude Code uses.

    Hook / statusline / command strings go through cmd.exe on Windows and
    `/bin/sh` elsewhere, with the session or event JSON on stdin.
    """
    data = stdin.encode("utf-8")
    if sys.platform == "win32":
        return subprocess.run(command, shell=True, input=data, capture_output=True, cwd=cwd)
    return subprocess.run(["/bin/sh", "-c", command], input=data, capture_output=True, cwd=cwd)


def _installed_commands(settings_path: Path) -> tuple[str, str]:
    """The hook and statusline command strings read back from settings.json."""
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    status = settings["statusLine"]["command"]
    return hook, status


def _expected_interpreter_token(launcher: str, *, plain: bool) -> str:
    """The token `_shell_path` must bake on this host for `launcher`."""
    if plain:
        return launcher
    if sys.platform == "win32":
        return f'"{launcher}"'
    return f"'{launcher}'"


def test_shell_path_encodes_for_posix_sh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under `/bin/sh` the token must keep `$`, `"` and `\\` as data, not syntax."""
    monkeypatch.setattr(claude_install, "_is_windows_shell", lambda: False)
    assert claude_install._shell_path("/usr/bin/python3") == "/usr/bin/python3"
    assert claude_install._shell_path("/opt/my python/bin/python3") == "'/opt/my python/bin/python3'"
    assert (
        claude_install._shell_path("/home/User $LABEL Home/python3")
        == "'/home/User $LABEL Home/python3'"
    )
    assert (
        claude_install._shell_path('/home/User "quoted" Home/python3')
        == '\'/home/User "quoted" Home/python3\''
    )
    assert claude_install._shell_path(r"C:\Users\me\python.exe") == r"'C:\Users\me\python.exe'"


def test_shell_path_encodes_for_cmd_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    """cmd.exe groups spaces with double quotes and reads `$` and `\\` literally.

    A plain Windows path keeps the installer's previous unquoted rendering.
    """
    monkeypatch.setattr(claude_install, "_is_windows_shell", lambda: True)
    assert (
        claude_install._shell_path(r"C:\Users\me\Python311\python.exe")
        == r"C:\Users\me\Python311\python.exe"
    )
    assert claude_install._shell_path(r"C:\Program Files (x86)\Python311\python.exe") == (
        r'"C:\Program Files (x86)\Python311\python.exe"'
    )
    assert claude_install._shell_path(r"C:\Users\User $LABEL Home\python.bat") == (
        r'"C:\Users\User $LABEL Home\python.bat"'
    )


@pytest.mark.skipif(sys.platform == "win32", reason="runs the rendering through /bin/sh")
@pytest.mark.parametrize(
    "path",
    [
        "/usr/bin/python3",
        "/opt/my python/bin/python3",
        "/home/User $LABEL Home/python3",
        '/home/User "quoted" Home/python3',
        "/home/it's/python3",
        "/home/back\\slash/python3",
    ],
)
def test_posix_rendering_round_trips_through_sh(path: str) -> None:
    """`/bin/sh` must expand the encoded token back to exactly the original path."""
    rendered = claude_install._shell_path(path)
    result = subprocess.run(["/bin/sh", "-c", f"printf %s {rendered}"], capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8") == path


@pytest.mark.parametrize("dirname", _LITERAL_DIRNAMES)
def test_baked_surfaces_keep_the_interpreter_token_literal(literal_host, dirname: str) -> None:
    launcher = str(literal_host(dirname))
    token = _expected_interpreter_token(launcher, plain=False)

    hardening = claude_install.hardening_block()
    assert hardening["hooks"]["PreToolUse"][0]["hooks"][0]["command"].startswith(f"{token} ")
    assert hardening["statusLine"]["command"].startswith(f"{token} ")

    command = claude_install.command_md()
    # The /loopx permission rule must carry the same token the command runs.
    assert f"allowed-tools: Bash({token}:*)" in command
    body = next(line for line in command.splitlines() if line.startswith("!`"))
    assert body.startswith(f"!`{token} ")


def test_a_plain_interpreter_path_keeps_its_previous_rendering(literal_host) -> None:
    launcher = str(literal_host("PlainPython311"))
    assert _expected_interpreter_token(launcher, plain=True) == launcher

    hardening = claude_install.hardening_block()
    assert hardening["hooks"]["PreToolUse"][0]["hooks"][0]["command"].startswith(f"{launcher} ")
    assert hardening["statusLine"]["command"].startswith(f"{launcher} ")
    assert f"allowed-tools: Bash({launcher}:*)" in claude_install.command_md()


@pytest.mark.parametrize("dirname", _LITERAL_DIRNAMES)
def test_installed_gate_command_runs_through_a_literal_interpreter(
    literal_host, dirname: str, tmp_path: Path
) -> None:
    """Execute the hook command exactly as `--harden` installed it.

    A token the shell splits, expands or dequotes never reaches Python: the
    gate exits non-zero with empty stdout (rc 127 under `/bin/sh`), which
    Claude Code treats as a non-blocking hook error - the tool call proceeds
    ungated.
    """
    literal_host(dirname)
    settings = tmp_path / "claude" / "settings.json"
    claude_install.add_hardening(dry=False, settings_path=settings)
    hook_cmd, _ = _installed_commands(settings)

    project = tmp_path / "project"
    project.mkdir()
    event = json.dumps({"cwd": str(project), "tool_name": "Read", "tool_input": {}})
    result = _host_shell_run(hook_cmd, event, cwd=project)

    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert json.loads(result.stdout.decode("utf-8")) == {}


@pytest.mark.parametrize("dirname", _LITERAL_DIRNAMES)
def test_installed_statusline_command_renders_through_a_literal_interpreter(
    literal_host, dirname: str, tmp_path: Path
) -> None:
    """Execute the statusline command read back from settings.json.

    Claude Code feeds the session JSON on stdin; with no goal here the
    statusline must render nothing - but only after the interpreter starts.
    """
    literal_host(dirname)
    settings = tmp_path / "claude" / "settings.json"
    claude_install.add_hardening(dry=False, settings_path=settings)
    _, status_cmd = _installed_commands(settings)

    project = tmp_path / "project"
    project.mkdir()
    result = _host_shell_run(status_cmd, json.dumps({"cwd": str(project)}), cwd=project)

    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stdout.decode("utf-8").strip() == ""


@pytest.mark.parametrize("dirname", _LITERAL_DIRNAMES)
def test_installed_slash_command_runs_through_a_literal_interpreter(
    literal_host, dirname: str, tmp_path: Path
) -> None:
    """Execute the `/loopx` body line from the installed command file.

    Claude Code substitutes `$ARGUMENTS` textually and runs the line through
    the host shell; `status` is the cheapest real argument, and with no goal
    here the helper says so and exits 0.
    """
    literal_host(dirname)
    cmd_dir = tmp_path / "claude" / "commands"
    claude_install.install_command(dry=False, cmd_dir=cmd_dir)
    text = (cmd_dir / "loopx.md").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("!`") and line.endswith("`"))
    command = line[2:-1].replace("$ARGUMENTS", "status")

    project = tmp_path / "project"
    project.mkdir()
    result = _host_shell_run(command, "", cwd=project)

    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert "no goal in this project yet" in result.stdout.decode("utf-8")
