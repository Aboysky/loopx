"""Private checkpoint context transport through existing canonical Todo owners.

Captured records are historical input, never a replacement authority store.
Only the existing explicit continuation owner can adopt a note on an already
claimed destination Todo. Graph/effect/vision reactivation is outside this seam.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path, PurePosixPath

from loopx.control_plane.effect_runtime import effect_runtime_result
from loopx.control_plane.coordination.canonical_snapshot import read_canonical_snapshot


def canonical_context(env: dict[str, str], *, deadline: float) -> dict:
    """Retain the complete revision-bound read, without the execution leases."""
    def rpc(method, payload, **kwargs):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("research checkpoint capture window closed")
        return effect_runtime_result(method, payload, timeout=remaining)
    result = read_canonical_snapshot(rpc=rpc, runtime_root=env["LOOPX_RUNTIME_ROOT"],
        goal_id=env["LOOPX_GOAL_ID"], include_leases=False, projection_readback=None,
        timeout=max(.1, deadline - time.time()))
    if result.get("status") != "loaded":
        raise ValueError("research checkpoint requires complete canonical Todo context")
    return {"goal_id": env["LOOPX_GOAL_ID"], "snapshot": result}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _handoff(env, payload):
    from loopx.agent_registry import registered_agent_ids_from_registry
    request = {"runtime_root": env["LOOPX_RUNTIME_ROOT"], "goal_id": env["LOOPX_GOAL_ID"],
        "agent_id": env["LOOPX_AGENT_ID"], "registered_agents": registered_agent_ids_from_registry(
            Path(env["LOOPX_REGISTRY"]), env["LOOPX_GOAL_ID"]), **payload}
    result = effect_runtime_result("coordination.local_authority.todo_continuation", request)
    if result.get("ok") is not True:
        raise ValueError("checkpoint context continuation rejected: " + str(result.get("reason_code", result.get("status"))))
    return result



def _context_session(env, metadata):
    """Read the admitted native branch before publishing captured Todo context."""
    from .codex import Execution
    from .sessions import BenchmarkSessionWake
    from .native_checkpoint import native_session_checkpoint

    wake = BenchmarkSessionWake(env, Execution(context="resume", sandbox=env["LOOPX_CODEX_SANDBOX"]), {})
    native = metadata["native_session"]
    if (not wake.session_id or wake.session_id == native["session_id"] or
            wake.digest != metadata.get("session", {}).get("session_profile_digest")):
        raise ValueError("context adoption requires the admitted destination session profile")
    observed = native_session_checkpoint(env, wake.session_id, timeout=30)["metadata"]
    for key in ("visible_history_sha256", "turn_ids", "completed_turn_id", "host_version", "config_sha256"):
        if observed[key] != native[key]:
            raise ValueError("destination native history or configuration moved beyond the captured context")
    return wake.session_id


def adopt_todo_context(env: dict[str, str], unit: Path, digest: str, *, source_todo_id: str,
                       todo_id: str, operation_id: str, expected_revision: str,
                       lease_key: str, lease_version: int) -> dict:
    """Adopt retained context using the destination's current claim and lease.

    No Todo is created, completed or transferred, and no historical authority,
    effect, strategy or graph is installed. Prepare/adopt each use stable original
    operation identities. A failed/uncertain call must be read back through that
    same owner; this adapter never guesses a new identity or starts model work.
    """
    from loopx.control_plane.turn_driver.codex_sessions import select_codex_cli_session
    from loopx.control_plane.todos.provider_projection import settle_canonical_todo_projection

    effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "verify", "root": str(unit), "expected_sha256": digest})
    metadata = json.loads((unit / "checkpoint.json").read_bytes())["point_metadata"]
    if not all(isinstance(metadata.get(key), dict) for key in ("loopx_state", "native_session", "research_context")):
        raise ValueError("checkpoint lacks its canonical Todo or native session context participant")
    source = metadata["loopx_state"]
    if (source["goal_id"] == env["LOOPX_GOAL_ID"] or source["agent_id"] == env["LOOPX_AGENT_ID"]):
        raise ValueError("context adoption requires distinct destination Goal and Agent")
    declared = metadata["research_context"]
    component, member = declared["component_id"], declared["member_path"]
    if (not isinstance(component, str) or Path(component).name != component or component in {".", ".."} or
            not isinstance(member, str) or PurePosixPath(member).is_absolute() or
            ".." in PurePosixPath(member).parts or (member and str(PurePosixPath(member)) != member)):
        raise ValueError("retained context member must stay within its artifact component")
    context_file = unit / "components" / component
    if member:
        context_file /= member
    raw = context_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != declared["sha256"]:
        raise ValueError("retained canonical context digest differs")
    carrier = json.loads(raw)
    context = carrier["snapshot"]
    if (carrier.get("goal_id") != source["goal_id"] or
            context.get("provider_revision") != declared["provider_revision"] or
            context.get("store_identity") != declared["store_identity"]):
        raise ValueError("retained canonical context revision differs")
    retained = next((row for row in context["todos"] if row["todo_id"] == source_todo_id), None)
    if retained is None:
        raise ValueError("source Todo is absent from the captured context")
    session_id = _context_session(env, metadata)
    bound = select_codex_cli_session(Path(env["LOOPX_RUNTIME_ROOT"]), lineage={
        "goal_id": env["LOOPX_GOAL_ID"], "agent_id": env["LOOPX_AGENT_ID"]}, session_scope="agent")
    if bound is None or bound["session_id"] != session_id:
        raise ValueError("context adoption requires the current distinct destination session binding")
    workspace = Path(env["LOOPX_PROJECT"])
    if not workspace.is_absolute() or workspace.resolve(strict=True) != workspace:
        raise ValueError("destination context workspace must be a physical absolute path")
    proof = {"idempotency_key": lease_key, "expected_version": lease_version}
    common = {"todo_id": todo_id, "session_id": bound["session_id"], "workspace": str(workspace),
              "artifacts": [], "lease_proof": proof}
    # The owner's inspect performs the real current claim/lease/dependency and
    # acceptance checks. Source records only contribute context; they are never
    # passed as operational fields to prepare or adopt.
    inspect = _handoff(env, {**common, "action": "inspect"})
    if (inspect["provider_revision"] != expected_revision or
            inspect["claimed_by"] != env["LOOPX_AGENT_ID"] or
            inspect.get("execution_authority", {}).get("allowed") is not True):
        raise ValueError("destination context revision, owner or execution authority changed")
    destination = canonical_context(env, deadline=time.time() + 30)["snapshot"]
    current = next((row for row in destination["todos"] if row["todo_id"] == todo_id), None)
    if destination["provider_revision"] != expected_revision or current is None:
        raise ValueError("destination canonical context moved before preparation")
    if current.get("note"):
        raise ValueError("destination Todo already has context; inspect its original owner instead of replacing it")
    # Keep the complete source read in a workspace-relative private artifact.
    # Never overwrite a moved artifact on an operation retry.
    relative = Path(".local/checkpoint-context") / (digest + ".json")
    target = workspace / relative
    for directory in (workspace / ".local", target.parent):
        if directory.is_symlink() or (directory.exists() and directory.resolve(strict=True) != directory):
            raise ValueError("destination context artifact must not use a symlink")
        directory.mkdir(exist_ok=True, mode=0o700)
    if target.is_symlink():
        raise ValueError("destination context artifact must not use a symlink")
    try:
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
            if file.write(raw) != len(raw):
                raise OSError("destination context artifact write is incomplete")
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        if target.read_bytes() != raw:
            raise ValueError("destination context artifact already differs")
    if target.read_bytes() != raw:
        raise ValueError("destination context artifact readback differs")
    effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "verify", "root": str(unit), "expected_sha256": digest})
    note = {"work_summary": "Retained canonical Todo context from the verified checkpoint is available in " + relative.as_posix() +
            ". Historical owners, statuses and operational references are evidence only; current Goal/Todo/lease rules govern work.",
        "source_refs": ["checkpoint:" + digest, "source-todo:" + source_todo_id,
                        "source-revision:" + declared["provider_revision"]],
        "files_touched": [{"path": relative.as_posix(), "action": "read",
                           "summary": "Complete captured canonical Todo population, including retained notes and rejected approaches."}]}
    prepared = _handoff(env, {**common, "action": "prepare", "session_id": metadata["native_session"]["session_id"],
        "operation_id": operation_id + "-prepare", "expected_provider_revision": expected_revision, "context": note})
    if select_codex_cli_session(Path(env["LOOPX_RUNTIME_ROOT"]), lineage={
            "goal_id": env["LOOPX_GOAL_ID"], "agent_id": env["LOOPX_AGENT_ID"]}, session_scope="agent") != bound:
        raise ValueError("destination session changed; inspect the original prepared context")
    if _context_session(env, metadata) != session_id:
        raise ValueError("destination native branch changed; inspect the original prepared context")
    adopted = _handoff(env, {**common, "action": "adopt", "artifacts": [relative.as_posix()],
        "operation_id": operation_id + "-adopt", "expected_provider_revision": prepared["provider_revision"]})
    effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "verify", "root": str(unit), "expected_sha256": digest})
    if target.read_bytes() != raw:
        raise ValueError("adopted context artifact changed; inspect the original continuation receipt")
    result = settle_canonical_todo_projection(adopted, registry_path=Path(env["LOOPX_REGISTRY"]),
        runtime_root=Path(env["LOOPX_RUNTIME_ROOT"]), goal_id=env["LOOPX_GOAL_ID"])
    if result.get("ok") is not True:
        raise ValueError("continuation committed; reconcile its original projection receipt")
    return {"context_adopted": True, "session_id": bound["session_id"], "todo_id": todo_id,
        "artifact": str(target), "context_sha256": declared["sha256"],
        "continuation": result, "model_calls": 0, "research_point_qualified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adopt checkpoint Todo context on an already owned destination Todo.")
    for name in ("root", "expected-sha256", "source-todo-id", "todo-id", "operation-id", "expected-revision", "lease-key"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--lease-version", type=int, required=True)
    args = parser.parse_args(argv)
    required = ("LOOPX_PROJECT", "LOOPX_REGISTRY", "LOOPX_RUNTIME_ROOT", "LOOPX_GOAL_ID", "LOOPX_AGENT_ID",
                "CODEX_BIN", "CODEX_HOME", "MODEL_NAME", "REASONING_EFFORT", "LOOPX_CODEX_SANDBOX")
    if any(not os.environ.get(key) for key in required):
        parser.error("Explicit destination registry, runtime, workspace, Goal and Agent are required")
    print(json.dumps(adopt_todo_context(dict(os.environ), Path(args.root), args.expected_sha256,
        source_todo_id=args.source_todo_id, todo_id=args.todo_id, operation_id=args.operation_id,
        expected_revision=args.expected_revision, lease_key=args.lease_key, lease_version=args.lease_version)))


if __name__ == "__main__":
    main()
