from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from loopx.cli_commands.dsh_launch import (
    handle_dsh_launch_command,
    resolve_dsh_launch,
)
from loopx.control_plane.operator_provider import write_operator_provider


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "dsh_bin": sys.executable,
        "dsh_home": str(tmp_path / "dsh-home"),
        "dsh_agents_home": str(tmp_path / "dsh-agents"),
        "runtime_root": str(tmp_path / "runtime"),
        "dsh_args": ["--", "web", "--port", "0"],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_dsh_launch_resolves_credential_into_child_environment_only(
    tmp_path: Path,
) -> None:
    secret = "synthetic-provider-key"
    write_operator_provider(
        runtime_root=tmp_path / "runtime",
        environ={},
        api_key=secret,
        base_url="https://provider.invalid/v1",
    )

    dsh_bin, dsh_args, environment = resolve_dsh_launch(
        _args(tmp_path),
        environ={},
    )

    assert dsh_bin == sys.executable
    assert dsh_args == ["web", "--port", "0"]
    assert environment["DEEPSEEK_API_KEY"] == secret
    assert environment["DEEPSEEK_BASE_URL"] == "https://provider.invalid/v1"
    assert environment["DSH_HOME"] == str(tmp_path / "dsh-home")
    assert environment["DSH_AGENTS_HOME"] == str(tmp_path / "dsh-agents")
    assert secret not in " ".join([dsh_bin, *dsh_args])


def test_dsh_launch_exec_preserves_arguments_and_defaults_to_web(
    tmp_path: Path,
) -> None:
    secret = "synthetic-provider-key"
    write_operator_provider(
        runtime_root=tmp_path / "runtime",
        environ={},
        api_key=secret,
    )
    calls: list[tuple[str, list[str], dict[str, str]]] = []

    def record(
        executable: str,
        argv: list[str],
        environment: dict[str, str],
    ) -> None:
        calls.append((executable, argv, environment))

    code = handle_dsh_launch_command(
        _args(tmp_path, dsh_args=[]),
        environ={},
        exec_environment=record,
    )

    assert code == 0
    assert calls[0][0] == sys.executable
    assert calls[0][1][1:] == ["web"]
    assert calls[0][2]["DEEPSEEK_API_KEY"] == secret
    assert secret not in " ".join(calls[0][1])


def test_dsh_launch_fails_closed_without_executable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = handle_dsh_launch_command(
        _args(tmp_path, dsh_bin=str(tmp_path / "missing-dsh")),
        environ={},
        exec_environment=lambda *_: None,
    )

    assert code == 2
    assert "DSH executable not found" in capsys.readouterr().err
