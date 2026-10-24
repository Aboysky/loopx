"""Opt-in local transport capture; quota and envelope owners remain unchanged."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import socket
import stat
import tempfile
from pathlib import Path

from ..control_plane.quota.error_codes import QuotaCommandValidationError, QuotaDecisionTransportError
from ..control_plane.turn_driver.decision_capture import validate_handoff_socket


CONTEXT_CAPTURE_READ_GUIDANCE = (
    "Follow next_command through eof and combine content in byte-offset order. "
    "In code-mode, forward successful exec stdout directly with text(result.output); "
    "retain errors. Small batches can save model round trips; start with at most two default pages "
    "and inspect every output. A host may truncate inside valid JSON or omit a whole output. "
    "Check each model-visible content's UTF-8 byte length against next_offset (total_bytes at eof), "
    "complete coverage and the original SHA-256. If incomplete, reread the affected range "
    "of this same capture with fewer pages or a smaller --page-bytes; do not trust a preview or EOF alone. "
    "Do not rerun admission or ask the owner. File existence and page EOF are not retention proof."
)


def context_capture_read_command(path: Path, digest: str, *, offset: int = 0, page_bytes: int = 4096) -> str:
    from ..command_invocation import loopx_cli_argv

    return shlex.join([*loopx_cli_argv(), "--format", "json", "quota", "context-read",
        "--capture-file", str(path), "--capture-sha256", digest,
        "--offset", str(offset), "--page-bytes", str(page_bytes)])


def read_context_capture(args: argparse.Namespace) -> dict:
    """Bounded local IO over immutable JSON, not a new context/authority owner.

    Verify the complete byte digest on every page. The cursor addresses bytes
    in that exact capture, so a replacement cannot silently mix two decisions.
    EOF describes this page, never a model's complete-consumption receipt.
    """
    from ..control_plane.effect_runtime import MAX_REQUEST_BYTES

    try:
        digest = getattr(args, "capture_sha256", None)
        value = getattr(args, "capture_file", None)
        offset, size = args.offset, args.page_bytes
        from ..control_plane.turn_driver.codex_context import codex_context_directory

        context_dir = codex_context_directory(directory=getattr(args, "codex_context_dir", None),
            root=getattr(args, "codex_context_root", None))
        if context_dir:
            if value or digest or offset != 0:
                raise ValueError("session lookup starts at offset zero without capture-file or capture-sha256; follow next_command afterwards")
            from ..control_plane.turn_driver.codex_context import read_codex_context_reference

            value, digest = read_codex_context_reference(context_dir,
                goal_id=getattr(args, "goal_id", None), agent_id=getattr(args, "agent_id", None))
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or not value:
            raise ValueError("context-read requires the original capture file and its exact SHA-256")
        if type(offset) is not int or offset < 0 or type(size) is not int or not 256 <= size <= 8192:
            raise ValueError("context-read requires a nonnegative byte offset and page-bytes between 256 and 8192")
        path = Path(value).expanduser().absolute()
        # Parent aliases such as macOS /tmp are normal capture locations.
        # Resolve those once, but never follow a substituted final file.
        path = path.parent.resolve(strict=True) / path.name
        if path.is_symlink():
            raise ValueError("context-read requires the physical original capture path, not a symlink")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REQUEST_BYTES:
                raise ValueError("capture must be a regular JSON file within the existing transport size limit")
            raw = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("capture digest mismatch; restore the original capture, do not rerun admission")
        if not isinstance(json.loads(raw.decode("utf-8")), dict):
            raise ValueError("capture must contain a complete JSON object")
        if offset > len(raw) or (offset < len(raw) and raw[offset] & 0xC0 == 0x80):
            raise ValueError("capture offset is outside the file or not a UTF-8 boundary; use the returned next offset")
        end = min(offset + size, len(raw))
        while end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1
        result = {"ok": True, "schema_version": "context_capture_page_v1", "sha256": digest,
            "offset": offset, "next_offset": end if end < len(raw) else None,
            "total_bytes": len(raw), "eof": end == len(raw), "content": raw[offset:end].decode("utf-8")}
        if context_dir:
            result["read_instruction"] = CONTEXT_CAPTURE_READ_GUIDANCE
        if end < len(raw):
            result["next_command"] = context_capture_read_command(path, digest, offset=end, page_bytes=size)
        return result
    except (OSError, ValueError, RecursionError) as exc:
        # Recovery is presentation-only: keep failures separate from quota's
        # collection error path and retain the existing receipt/capture.
        return {"ok": False, "schema_version": "context_capture_page_v1",
            "reason": str(exc) if isinstance(exc, ValueError) else "original capture could not be read",
            "recovery": "Restore the original digest-bound capture; no guard, admission or spend was performed."}


def prepare_decision_capture(args: argparse.Namespace) -> Path | None:
    requested = getattr(args, "decision_output_dir", None)
    root = getattr(args, "decision_output_root", None)
    handoff = getattr(args, "decision_handoff_socket", None)
    if (getattr(args, "codex_context_dir", None) is not None
            or getattr(args, "codex_context_root", None) is not None) and (
            args.format != "json" or (requested is None and root is None)):
        raise QuotaCommandValidationError(
            "native Codex context delivery needs JSON and a capture destination")
    if handoff is not None:
        validate_handoff_socket(handoff)
        if requested is None and root is None:
            raise QuotaCommandValidationError("decision handoff requires an explicit decision capture destination")
    if requested is None and root is None:
        return None
    if requested is not None and root is not None:
        raise QuotaCommandValidationError("choose one decision capture destination")
    if args.quota_command != "should-run" or not (
        getattr(args, "turn_instance_id", None)
        or bool(getattr(args, "begin_turn", False))
    ):
        raise QuotaCommandValidationError(
            "decision capture requires quota should-run and either "
            "--turn-instance-id or --begin-turn"
        )
    try:
        if root is not None:
            parent = Path(root).expanduser().absolute()
            if parent.is_symlink() or not parent.is_dir():
                raise OSError("capture root must be an existing directory, not a symlink")
            return Path(tempfile.mkdtemp(prefix="decision-", dir=parent))
        directory = Path(requested).expanduser().absolute()
        # A new directory per invocation prevents overwriting a prior observation,
        # including a prior invocation in the same Turn. Existing symlinks fail too.
        directory.mkdir(mode=0o700)
    except OSError as exc:
        raise QuotaCommandValidationError(
            "decision capture needs a new directory or an existing writable root; "
            f"no guard was run: {exc}"
        ) from exc
    return directory


def capture_decision(directory: Path | None, payload: dict[str, object]) -> None:
    if directory is None:
        return
    from ..control_plane.turn_driver.decision_capture import write_decision_capture

    try:
        write_decision_capture(directory / "decision.json", payload, publish=os.replace)
    except (OSError, ValueError) as exc:
        raise QuotaDecisionTransportError(
            "Decision capture failed after guard evaluation; the Turn receipt may "
            "already exist. Do not treat this as missing admission or blindly rerun "
            f"the guard. Inspect the existing Turn receipt. Capture directory: {directory}"
        ) from exc


def bind_capture_selection_transport(payload: dict, args: argparse.Namespace) -> None:
    """Retain caller display/capture options in the existing selection command.

    Only transport argv is added here; the typed quota owner still selects the
    action and owns admission. Each selection invocation allocates a new capture.
    """
    root = getattr(args, "decision_output_root", None)
    if root is None:
        return
    interaction = payload.get("interaction_contract")
    cli = interaction.get("cli_channel") if isinstance(interaction, dict) else None
    selection = cli.get("selection_command") if isinstance(cli, dict) else None
    if not isinstance(selection, dict):
        return
    template = selection.get("command_args_template")
    if not isinstance(template, str):
        return
    suffix = " --decision-output-root " + shlex.quote(str(Path(root).expanduser().absolute()))
    if getattr(args, "decision_handoff_socket", None):
        suffix += " --decision-handoff-socket " + shlex.quote(args.decision_handoff_socket)
    if getattr(args, "turn_envelope", False):
        suffix += " --turn-envelope"
    if getattr(args, "codex_context_dir", None):
        suffix += " --codex-context-dir " + shlex.quote(args.codex_context_dir)
    if getattr(args, "codex_context_root", None):
        suffix += " --codex-context-root " + shlex.quote(args.codex_context_root)
    selection["command_args_template"] = template + suffix


def handoff_decision(directory: Path | None, socket_path: str | None) -> tuple[dict, str] | None:
    """Withhold the original output until the Host releases these exact bytes.

    No second guard, admission, settlement or retry is performed here. A lost
    acknowledgement leaves the saved decision available for original-identity
    recovery; it must never be silently replaced by a later observation.
    """
    if socket_path is None:
        return
    if directory is None:
        raise ValueError("decision handoff requires a captured decision")
    path = directory / "decision.json"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(120)
            channel.connect(str(validate_handoff_socket(socket_path)))
            channel.sendall(json.dumps({"path": str(path), "sha256": digest}).encode() + b"\n")
            with channel.makefile("rb") as stream:
                line = stream.readline(1025)
            response = json.loads(line)
            ordinary_release = {"released": True, "sha256": digest}
            if response not in (ordinary_release, {**ordinary_release, "context_delivery": True}):
                raise ValueError("Host did not release the original decision digest")
        if path.read_bytes() != raw:
            raise ValueError("captured decision changed during handoff")
    except (OSError, ValueError) as exc:
        raise QuotaDecisionTransportError(
            "Decision handoff failed after guard evaluation; inspect the original "
            f"Turn receipt and {path}. Do not blindly rerun the guard."
        ) from exc
    if response.get("context_delivery") is not True:
        return None
    # Only an explicit Host request opts in. The release itself does not prove
    # delivery/retention. Read one private snapshot, never an arbitrary pathname
    # supplied by a response or a model. Invalid optimization input selects full.
    request_path = directory / "delivery-request.json"
    try:
        from ..control_plane.effect_runtime import MAX_REQUEST_BYTES
        descriptor = os.open(request_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or
                    metadata.st_size > MAX_REQUEST_BYTES or metadata.st_uid != os.getuid()):
                return {}, digest
            raw = source.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            return {}, digest
        request = json.loads(raw)
        return (request if isinstance(request, dict) else {}), digest
    except (OSError, ValueError, RecursionError):
        return {}, digest


def project_captured_context(
    payload: dict, *, directory: Path | None, request: dict | None,
    goal_id: str, agent_id: str, surface: str, capture_id: str,
) -> dict:
    """Adapt an admitted capture to the shared TS presentation owner.

    The caller-owned rendezvous may supply a continuity observation. It must
    still recheck the candidate at final model-input assembly and ACK only intact
    delivery. Unsupported ordinary CLI clients never supply this request. Every
    opt-in attempt saves the complete projected JSON for same-capture recovery;
    neither malformed requests nor optimization failures rerun the guard.
    """
    if request is None or directory is None:
        return payload
    from ..control_plane.effect_runtime import EffectRuntimeRemoteError, EffectRuntimeStartupError
    from ..control_plane.quota.turn_envelope import prepare_context_delivery
    from ..control_plane.turn_driver.decision_capture import write_decision_capture

    try:
        projection = directory / "projection.json"
        write_decision_capture(projection, payload)
        scope = request.get("scope")
        if not isinstance(scope, dict) or scope.get("goal_id") != goal_id or scope.get("agent_id") != agent_id:
            return payload
        retained = request.get("retained")
        if "native_input" in request:
            from ..control_plane.turn_driver.codex_input_trace import codex_context_in_active_input

            # An optional native observation can only narrow the caller's
            # retention claim. It never mints an ACK or enables tracing, and a
            # malformed/stale observation must not fall back to that claim.
            observation, baseline = request["native_input"], request.get("baseline")
            if (not isinstance(observation, dict) or not isinstance(baseline, dict)
                    or not codex_context_in_active_input(observation, baseline=baseline,
                        session_id=scope.get("session_id"))):
                retained = None
        delivery = prepare_context_delivery(payload, scope=scope,
            capture_id=capture_id, surface=surface,
            baseline=request.get("baseline"), retained=retained)
        delivery["recovery"] = {
            "path": str(projection), "sha256": hashlib.sha256(projection.read_bytes()).hexdigest(),
            "instruction": "Complete JSON for this original capture. If the baseline is missing, compacted, "
                "truncated or uncertain, use this full projection before dependent work. "
                + CONTEXT_CAPTURE_READ_GUIDANCE,
        }
        delivery["recovery"]["command"] = context_capture_read_command(projection, delivery["recovery"]["sha256"])
        return delivery
    except (OSError, ValueError, TypeError, EffectRuntimeRemoteError, EffectRuntimeStartupError):
        # The original full payload is already available. An unavailable optional
        # codec/capture must not convert safe full delivery into an execution gate.
        return payload
