"""Registered machine settings for the existing native Codex transport."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract import MachineConfigurationNamespace
from ...control_plane.turn_driver.codex_context import CONTEXT_DELIVERY_SETTINGS


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
