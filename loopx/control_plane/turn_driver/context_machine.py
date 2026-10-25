"""Machine defaults for the existing opt-in Codex transport, not Goal authority.

The machine-configuration transaction owns persistence. This native IO adapter
only supplies omitted CLI options; packet semantics remain in context_delivery.ts.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path
import stat
from typing import Any

from ...capabilities.machine_configuration.contract import MachineConfigurationNamespace
from .codex_context import CONTEXT_DELIVERY_SETTINGS, context_delivery_for_arguments


CONTEXT_DELIVERY_MACHINE_SCHEMA = "context_delivery_machine_defaults_v0"


def normalize_context_delivery_machine_defaults(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != {"schema_version", "mode"} or raw.get("schema_version") != CONTEXT_DELIVERY_MACHINE_SCHEMA:
        raise ValueError("context_delivery requires its schema_version and mode")
    if raw["mode"] not in CONTEXT_DELIVERY_SETTINGS:
        raise ValueError("context_delivery mode must be off or on")
    return {"schema_version": CONTEXT_DELIVERY_MACHINE_SCHEMA, "mode": raw["mode"]}


def context_delivery_machine_configuration_namespace() -> MachineConfigurationNamespace:
    return MachineConfigurationNamespace(
        namespace="context_delivery",
        schema_versions=frozenset({CONTEXT_DELIVERY_MACHINE_SCHEMA}),
        normalize=normalize_context_delivery_machine_defaults,
        project_public=lambda value: dict(value),
        apply_public_update=lambda _current, update: dict(update),
        title="Codex heartbeat context",
        description=(
            "Off by default. On supports declared Codex App and benchmark heartbeats only; "
            "unknown or unsupported modes fail before admission. Native hooks and input "
            "diagnostics still need host setup; unproven retention uses the full capture."
        ),
        documentation={"path": "docs/reference/required-work-context.md#machine-default"},
        default_configuration={"schema_version": CONTEXT_DELIVERY_MACHINE_SCHEMA, "mode": "off"},
    )


def _private_transport_root(runtime_root: Path) -> str:
    """Create only our leaf; never repair permissions or follow a replaced leaf."""
    if os.name != "posix":
        raise ValueError("native context continuity is unavailable on this platform")
    root = runtime_root.expanduser().resolve() / "context-delivery"
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("machine context transport requires a private physical directory owned by this user")
    return str(root)


def apply_context_machine_options(
    args: argparse.Namespace, *, registry_path: Path, runtime_root_arg: str | None,
    heartbeat: bool = False,
) -> None:
    """Resolve each invocation afresh; explicit options skip this default lookup.

    Saved capture pages stay registry/configuration independent. Native-only
    commands use the explicit machine runtime or normal machine route without
    loading a Goal registry. No hook, trust, tracing or automation is installed.
    """
    if getattr(args, "context_delivery", None) is not None:
        return
    args.context_delivery = "off"
    # Existing benchmark workers retain their explicit opt-out. A machine
    # default must not silently change a frozen worker's disabled transport.
    # An environment on alone still supplies no activation or host proof.
    if os.environ.get("LOOPX_CONTEXT_DELIVERY") == "off":
        return
    command = getattr(args, "quota_command", None)
    if not heartbeat and command not in {"should-run", "context-config", "context-project", "context-hook", "context-read"}:
        return
    if command == "context-read" and any(getattr(args, key, None) for key in (
        "capture_file", "capture_sha256", "codex_context_dir", "codex_context_root"
    )):
        return
    from ...paths import effective_runtime_root, resolve_runtime_root
    from ...capabilities.machine_configuration.builtins import build_builtin_machine_configuration_registry
    from ...capabilities.machine_configuration.store import read_machine_configuration

    runtime_root = (
        effective_runtime_root(registry_path, runtime_root_arg)
        if heartbeat or command == "should-run"
        else resolve_runtime_root({}, runtime_root_arg)
    )
    configuration = read_machine_configuration(runtime_root, registry=build_builtin_machine_configuration_registry())
    value = (configuration or {}).get("namespaces", {}).get("context_delivery")
    if value is None or value["mode"] == "off":
        return
    args._context_delivery_machine_runtime = str(runtime_root.expanduser().resolve())
    # Recovery does not activate a run mode or create a missing session.
    if command != "context-read":
        args.context_delivery = "on"
        context_delivery_for_arguments(args)
        if command == "should-run" and args.format != "json":
            raise ValueError("native Codex context delivery needs JSON and a capture destination")
    location_missing = not (getattr(args, "codex_context_dir", None) or getattr(args, "codex_context_root", None))
    capture_missing = (heartbeat or command == "should-run") and not (
        getattr(args, "decision_output_dir", None) or getattr(args, "decision_output_root", None)
    )
    if command == "context-read":
        if location_missing:
            args.codex_context_root = str(runtime_root.expanduser().resolve() / "context-delivery")
        return
    if location_missing or capture_missing:
        root = _private_transport_root(runtime_root)
        if location_missing:
            args.codex_context_root = root
        if capture_missing:
            args.decision_output_root = root
