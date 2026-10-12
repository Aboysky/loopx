"""Opt-in read-only checkpoint participant over the native SForge judge.

Native admission, grading, history and ranking retain their owners. This
adapter exports a quiescent registration's public history and opportunity
clock; it cannot register, submit, restore or extend a trial.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from dataclasses import replace
from pathlib import Path
from benchmark.runtime.sforge_checkpoint import ROUTE, SCHEMA


def create_app(config, *, checkpoint_capture=False):
    if type(checkpoint_capture) is not bool:
        raise ValueError("checkpoint_capture must be an explicit boolean")
    from sforge.harness.judge_server import SubmissionStatus, create_app as native_app
    app = native_app(config)
    if not checkpoint_capture:
        return app  # Preserve the native route/admission surface when disabled.
    from fastapi import HTTPException
    from pydantic import BaseModel, ConfigDict
    import sforge

    state = getattr(app.state, "judge", None)
    if state is None or not all(hasattr(state, key) for key in (
            "_admission_lock", "_outstanding_by_run", "_tokens_lock", "_history_lock")):
        raise ValueError("Checkpoint capture requires a pinned SForge with its native admission owner exposed")
    epoch = uuid.uuid4().hex
    source = hashlib.sha256()
    source_root = Path(sforge.__file__).parent
    for path in sorted(source_root.rglob("*.py")):
        source.update(path.relative_to(source_root).as_posix().encode() + b"\0")
        source.update(hashlib.sha256(path.read_bytes()).digest())
    tasks = {key: {
        "native_source_sha256": source.hexdigest(),
        "task_spec_sha256": hashlib.sha256((config.tasks_dir / f"{key}.json").read_bytes()).hexdigest(),
        "judge_image_key": task.judge_image_key,
        "selection": task.judge.selection, "score_direction": task.judge.score_direction,
    } for key, task in state.tasks.items()}

    class ReadRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        token: str

    # FastAPI resolves annotations in module globals; keep this factory's
    # private request type concrete rather than a forward reference.
    def capture(request):
        # Reuse the native lock order and outstanding admission counter. A
        # pending grade or unexplained consumed round is never a complete point.
        with state._admission_lock, state._tokens_lock, state._history_lock:
            info = state.tokens.get(request.token)
            if info is None:
                raise HTTPException(403, "Unknown registration")
            run, task = info["run_id"], info["task_id"]
            if state._closed or state.tasks[task].game_mode:
                raise HTTPException(409, "Checkpoint requires an open non-game registration")
            if state._outstanding_by_run.get((run, task), 0):
                raise HTTPException(409, "Accepted evaluation is still outstanding")
            if info["next_auto"] != 1:
                raise HTTPException(409, "This checkpoint profile requires no automatic evaluations")
            history = state.run_history.get(state._run_key(run, task), [])
            rounds = [entry.get("round") for entry in history]
            expected = {f"agent-{index}" for index in range(1, info["next_agent"])}
            if (len(rounds) != len(expected) or set(rounds) != expected or
                    any(entry.get("status") not in {SubmissionStatus.COMPLETED, SubmissionStatus.ERROR} for entry in history)):
                raise HTTPException(409, "Consumed rounds and released history are not reconciled")
            results = {}
            for entry in history:
                identifier = entry.get("submission_id")
                native = state.submissions.get(identifier)
                if (native is None or native.get("run_id") != run or native.get("task_id") != task or
                        native.get("round") != entry["round"] or native.get("status") != entry["status"]):
                    raise HTTPException(409, "Released result details are unavailable or differ")
                results[identifier] = {key: native.get(key) for key in ("status", "report", "error")}
            observed = time.time()
            last = info["last_agent_submit_at"]
            cooldown = info["submission_cooldown"]
            remaining = max(0, last + (cooldown or 0) - observed) if last else 0
            packet = {
                "schema_version": SCHEMA, "judge_epoch": epoch,
                "run_id": run, "task_id": task, "evaluator": tasks[task],
                "observed_at_epoch": observed, "last_agent_submit_at_epoch": last,
                "submission_cooldown_seconds": cooldown,
                "remaining_cooldown_seconds": remaining,
                "max_agent_submissions": info["max_agent_submissions"],
                "next_agent_round": info["next_agent"], "next_auto_round": info["next_auto"],
                "released_history": history, "released_results": results, "outstanding_evaluations": 0,
                "execution_authority_granted": False,
            }
            return json.loads(json.dumps(packet))  # No live references or tokens leave the lock.
    capture.__annotations__["request"] = ReadRequest
    app.post(ROUTE)(capture)
    return app


def main(argv=None):
    import uvicorn
    from sforge.harness.config import load_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-capture", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--tasks-dir", type=Path)
    parser.add_argument("--log-dir", type=Path)
    args = parser.parse_args(argv)
    config = load_config()
    overrides = {key: getattr(args, key) for key in ("tasks_dir", "log_dir") if getattr(args, key) is not None}
    uvicorn.run(create_app(replace(config, **overrides), checkpoint_capture=args.checkpoint_capture),
                host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
