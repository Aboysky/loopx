"""In-process transport to the existing native command owners.

No stdout redirection or subprocess: original Chat workers can run concurrently.
Arguments are constructed by the host, never accepted from a model or HTTP body.
"""
from __future__ import annotations

from typing import Any


class NativeStewardCommandError(ValueError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__("the native steward operation was not committed: " + str(
            payload.get("error_code") or "unavailable") + ": " + str(
            payload.get("error") or payload.get("reason") or payload.get("message") or "inspect the native receipt"))


def native_command(controller: Any, argv: list[str]) -> dict[str, Any]:
    from ...cli import build_parser
    from ...cli_rollout import append_cli_rollout_event
    from ...cli_commands.quota import handle_quota_command
    from ...cli_commands.todo import handle_todo_command
    from ...cli_commands.task_lease import handle_task_lease_command

    args = build_parser().parse_args(["--format", "json", *argv])
    result: dict[str, Any] = {}
    kwargs = {"registry_path": controller.registry_path,
        "runtime_root_arg": str(controller.coordination_runtime_root),
        "print_payload": lambda payload, *_args: result.update(payload)}
    if args.command == "todo":
        code = handle_todo_command(args, **kwargs, format_name="json",
            append_cli_rollout_event=append_cli_rollout_event)
    elif args.command == "quota":
        code = handle_quota_command(args, **kwargs,
            append_cli_rollout_event=append_cli_rollout_event)
    elif args.command == "task-lease":
        code = handle_task_lease_command(args, **kwargs, output_format=lambda *_a, **_kw: "json")
    else:
        raise ValueError("unsupported native steward operation")
    if code or result.get("ok") is not True:
        raise NativeStewardCommandError(result)
    return result
