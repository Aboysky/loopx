"""Opt-in native lifecycle IO for the existing quota context projector.

The private directory belongs to one native session/workspace. Files are only
candidate references: actual native input must independently prove retention.
No hook grants execution authority or acknowledges model understanding.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import uuid

from .decision_capture import write_decision_capture


def _read(path: Path, *, private: bool = True) -> dict:
    from ..effect_runtime import MAX_REQUEST_BYTES

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or (private and info.st_mode & 0o077) or info.st_size > MAX_REQUEST_BYTES):
            raise ValueError("context transport needs a bounded private regular file")
        raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("context transport file is too large")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("context transport file must contain an object")
    return result


@contextmanager
def _locked(directory: str):
    if os.name != "posix":
        raise ValueError("native context continuity is unavailable on this platform")
    import fcntl

    root = Path(directory).expanduser().absolute()
    root = root.parent.resolve(strict=True) / root.name
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("context directory must already exist, be private and belong to this user")
    fd = os.open(root / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "r+") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("context lock is not a regular file")
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _state(root: Path) -> dict:
    try:
        return _read(root / "session.json")
    except FileNotFoundError:
        return {}


def _save(root: Path, state: dict) -> None:
    write_decision_capture(root / "session.json", state, publish=os.replace)


def codex_context_hook(directory: str, event: dict) -> dict:
    """Consume native lifecycle events; emit only same-capture recovery refs.

    Compaction/fork/restart invalidate. Same-session resume keeps only a candidate:
    the new active call's actual input must prove every byte before reuse.
    PreToolUse supplies the native call id; it is not retention proof. Failure to update the
    primary journal still returns the existing recovery ref when available.
    Trust/enablement and complete event delivery remain native host concerns.
    """
    name, session = event.get("hook_event_name"), event.get("session_id")
    if not isinstance(session, str) or not session:
        return {}
    recovery = None
    try:
        with _locked(directory) as root:
            state = _state(root)
            same = state.get("session_id") == session and state.get("cwd") == event.get("cwd")
            if same:
                recovery = state.get("recovery")
            else:
                state = {"session_id": session, "cwd": event.get("cwd")}
            resumed = name == "SessionStart" and event.get("source") == "resume" and same
            if resumed:
                state["active_call"] = None
            elif name in ("SessionStart", "PreCompact"):
                state.update(context_epoch=uuid.uuid4().hex, active_call=None)
                state.pop("candidate", None)
            elif name == "PreToolUse" and same and state.get("context_epoch"):
                state["active_call"] = event.get("tool_use_id")
            else:
                return {}
            _save(root, state)
    except (OSError, ValueError, TypeError, RecursionError):
        # A failed primary update cannot suppress a known full-read reference.
        # It also cannot manufacture a fresh active-call observation.
        pass
    if name == "SessionStart" and isinstance(recovery, dict) and recovery.get("command"):
        from ...cli_commands.quota_capture import CONTEXT_CAPTURE_READ_GUIDANCE

        if event.get("source") == "resume":
            return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                "LoopX resumed context is unconfirmed. Reuse prior context only when complete in current input. "
                "If missing before continuing the captured decision, read the original full capture. "
                "Recovery does not renew authority or freshness. " + CONTEXT_CAPTURE_READ_GUIDANCE + " "
                + recovery["command"]}}
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
            "LoopX context baseline invalidated. Before dependent work, read this original full capture. "
            "Capture recovery does not renew authority or source freshness. "
            + CONTEXT_CAPTURE_READ_GUIDANCE + " "
            + recovery["command"]}}
    return {}


def _trace_bundle(session: str, tool_id: str) -> str | None:
    from .codex_input_trace import read_native_trace_file

    value = os.environ.get("CODEX_ROLLOUT_TRACE_ROOT")
    if not value:
        return None  # never enable tracing implicitly
    matches = []
    # Native diagnostics are optional. Bound discovery instead of scanning a
    # long session archive. Resume can create another bundle for the same
    # session; the active-call/input verifier, never mtime, selects its source.
    for index, path in enumerate(Path(value).glob("trace-*")):
        if index >= 128:
            return None
        try:
            manifest = _read(path / "manifest.json", private=False)
        except (OSError, ValueError):
            continue
        if manifest.get("root_thread_id") == session and manifest.get("rollout_id") == session:
            try:
                raw = read_native_trace_file(path / "trace.jsonl", tail=True)
                if not raw.endswith(b"\n"):
                    return None
                events = [json.loads(line)["payload"] for line in raw.splitlines()]
                calls = [event for event in events if event.get("tool_call_id") == tool_id
                         and event.get("type") in ("tool_call_started", "tool_call_ended")]
                if calls and calls[-1]["type"] == "tool_call_started":
                    matches.append(str(path))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                return None
    # Count live call identities before checking retained content. Otherwise an
    # abandoned old call could win when a resumed call with the same id lost its
    # input. The selected bundle still needs the complete independent verifier.
    return matches[0] if len(matches) == 1 else None


def project_codex_context(payload: dict, *, directory: str, capture_directory: Path,
                          goal_id: str, agent_id: str, surface: str, capture_id: str) -> dict:
    """Existing CLI consumer, sharing the rendezvous projector and recovery IO.

    Serialization prevents an invalidation from moving the epoch during
    preparation. The current capture reference is durable before publication,
    so a later compact event recovers those exact bytes. Full candidates are
    never advanced from file existence, hook success or a saved delivery flag.
    """
    from ...cli_commands.quota_capture import project_captured_context
    from .codex_input_trace import codex_context_in_active_input

    try:
        with _locked(directory) as root:
            state = _state(root)
            session, epoch = state.get("session_id"), state.get("context_epoch")
            if (not isinstance(session, str) or not isinstance(epoch, str)
                    or not session or not epoch or session != os.environ.get("CODEX_THREAD_ID")
                    or Path(state.get("cwd", "")).resolve() != Path.cwd().resolve()):
                return payload
            scope = dict(goal_id=goal_id, agent_id=agent_id, session_id=session, context_epoch=epoch)
            request = {"scope": scope}
            candidate = state.get("candidate")
            if isinstance(candidate, dict) and isinstance(state.get("active_call"), str):
                try:
                    baseline = _read(Path(candidate["path"]))
                    trace = _trace_bundle(session, state["active_call"])
                    if trace:
                        observation = dict(trace_bundle=trace, tool_call_id=state["active_call"],
                            capture_file=candidate["capture_file"], capture_sha256=candidate["capture_sha256"])
                        if codex_context_in_active_input(observation, baseline=baseline, session_id=session):
                            request.update(baseline=baseline, retained={"complete": True, "target": baseline["target"]},
                                native_input=observation)
                except (OSError, ValueError, KeyError, TypeError, RecursionError):
                    pass  # Missing candidate: publish a new full capture, never an old recovery ref.
            result = project_captured_context(payload, directory=capture_directory, request=request,
                goal_id=goal_id, agent_id=agent_id, surface=surface, capture_id=capture_id)
            if result.get("schema_version") != "context_delivery_v1":
                return result
            recovery = result["recovery"]
            state["recovery"] = {key: recovery[key] for key in ("path", "sha256", "command")}
            if result["mode"] == "full":
                path = capture_directory / "presentation.json"
                write_decision_capture(path, result)
                state["candidate"] = dict(path=str(path), capture_file=recovery["path"],
                    capture_sha256=recovery["sha256"])
            _save(root, state)
            return result
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        # A broken optional adapter preserves the already admitted full result.
        return payload
