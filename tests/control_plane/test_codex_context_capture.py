"""Native tools execute the actual quota CLI and recover its original capture.

The loopback provider is a deterministic input-boundary observer. This qualifies
the transport composition, not a shipped continuity observer or solver benefit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import threading

import pytest

from canonical_authority_fixture import initialize_canonical_authority, isolate_sqlite_runtime, read_fixture_todos
from loopx.control_plane.coordination.runtime_shadow import build_todo_runtime_shadow_projection
from loopx.control_plane.quota.turn_envelope import prepare_context_delivery, restore_context_delivery
from test_quota_settlement_cli import AGENT_ID, GOAL_ID, TODO_ID, _spend_run_count, _write_fixture
from tests.control_plane.codex_checkpoint_fixture import local_inference_provider
from tests.control_plane.test_codex_context_boundary import _app_server, _configure_provider, _input_text, _native_fixture

pytestmark = pytest.mark.skipif(not os.environ.get("LOOPX_NATIVE_CHECKPOINT_BIN"),
    reason="Explicit native Codex binary required; inference uses loopback only")


def _delivered(request, name):
    pages = {}
    for item in request["input"]:
        output = item.get("output")
        marker = f"CAPTURE_PAGE {name} "
        if item.get("type") == "function_call_output" and isinstance(output, str) and marker in output:
            index, body = output.split(marker, 1)[1].split("\n", 1)
            assert "truncated output" not in output
            pages[int(index)] = body.rstrip("\n")
    return "".join(pages[i] for i in range(len(pages)))


@pytest.mark.parametrize("host,surface", [("exec", "quota_packet"), ("app_server", "turn_envelope")])
@pytest.mark.parametrize("failed_primary", [False, True])
def test_native_cli_capture_delta_and_compact_recovery(tmp_path, monkeypatch, host, surface, failed_primary):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    binary, env, workspace, home = _native_fixture(tmp_path)
    env.update(NODE_OPTIONS="--experimental-sqlite", LOOPX_USAGE_PING="0")
    project, runtime, registry = _write_fixture(workspace)
    state = project / f".codex/goals/{GOAL_ID}/ACTIVE_GOAL_STATE.md"
    body = "\n".join(f"Requirement {i:04d}: preserve this row and its evidence." for i in range(400))
    body += "\nFINAL REQUIREMENT: stop before publication."
    todos = read_fixture_todos(state)
    todos[0].update(text=body, title=body)
    initialize_canonical_authority(runtime, GOAL_ID,
        build_todo_runtime_shadow_projection(goal_id=GOAL_ID, todos=todos, handoff_mode="soft_claim"),
        state_path=state, provider="sqlite")
    original_state = state.read_bytes()
    root = workspace / "captures"
    root.mkdir()
    wire_paths = {name: workspace / f"{name}.json" for name in ("cold", "warm")}
    reference = home / "current-reference.json"
    identity = home / "session.json"
    hook = home / "hook.py"
    hook.write_text(
        "import json,pathlib,sys\nevent=json.load(sys.stdin)\n"
        f"root=pathlib.Path({str(home)!r})\n"
        "if event['hook_event_name']=='SessionStart':\n"
        "    (root/'session.json').write_text(json.dumps({'session_id':event['session_id']}))\n"
        "    if event.get('source')=='compact':\n"
        "        (root/'epoch-invalidated').write_text('compact')\n"
        "        try:\n"
        + ("            raise RuntimeError('primary handler failure')\n" if failed_primary else "            pass\n")
        + "        except RuntimeError:\n            pass\n"
        "        ref=json.loads((root/'current-reference.json').read_text())\n"
        "        print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart',"
        "'additionalContext':'Baseline invalidated. Read the complete original capture before dependent work; '"
        "'do not rerun admission or ask the owner. '+json.dumps(ref)}}))\n"
    )
    handler = {"type": "command", "command": shlex.join([sys.executable, str(hook)]), "timeout": 10}
    (home / "hooks.json").write_text(json.dumps({"hooks": {
        event: [{"hooks": [handler]}] for event in ("SessionStart", "PostToolUse")}}))
    snapshots, requests_to_host, errors = [], [], []
    stopped = threading.Event()
    stages = {"phase": "start", "pages": [], "baseline_confirmed": False, "compact_response": None}
    wires = {}

    with tempfile.TemporaryDirectory(prefix="context-native-", dir="/tmp") as short:
        endpoint = Path(short).resolve() / "host.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(endpoint))
            listener.listen(2)
            listener.settimeout(0.2)

            def release():
                try:
                    while len(snapshots) < 2 and not stopped.is_set():
                        try:
                            channel, _ = listener.accept()
                        except TimeoutError:
                            continue
                        index = len(snapshots)
                        with channel:
                            channel.settimeout(30)
                            message = json.loads(channel.makefile("rb").readline(4096))
                            path = Path(message["path"])
                            raw = path.read_bytes()
                            assert hashlib.sha256(raw).hexdigest() == message["sha256"]
                            scope = dict(goal_id=GOAL_ID, agent_id=AGENT_ID,
                                session_id=json.loads(identity.read_text())["session_id"], context_epoch="initial")
                            request = {"scope": scope}
                            if index:
                                # This is observed *post-processing* native model input,
                                # not a release/file/session-id acknowledgement.
                                assert stages["baseline_confirmed"] is True
                                request.update(baseline=wires["cold"],
                                    retained={"complete": True, "target": wires["cold"]["target"]})
                            request_path = path.parent / "delivery-request.json"
                            request_path.write_text(json.dumps(request))
                            request_path.chmod(0o600)
                            requests_to_host.append(request)
                            snapshots.append((path, raw))
                            channel.sendall(json.dumps({"released": True, "sha256": message["sha256"],
                                "context_delivery": True}).encode() + b"\n")
                except BaseException as error:
                    errors.append(error)

            worker = threading.Thread(target=release, daemon=True)
            worker.start()
            command = ["env", f"PYTHONPATH={Path(__file__).resolve().parents[2]}", sys.executable,
                "-m", "loopx.entrypoint", "--registry", str(registry), "--runtime-root", str(runtime),
                "--format", "json", "quota", "should-run", "--goal-id", GOAL_ID, "--agent-id", AGENT_ID,
                "--todo-id", TODO_ID, "--turn-instance-id", "native-capture-turn", "--codex-app",
                "--decision-output-root", str(root), "--decision-handoff-socket", str(endpoint)]
            if surface == "turn_envelope":
                command.append("--turn-envelope")

            def invoke(name):
                return shlex.join(command) + " > " + shlex.quote(str(wire_paths[name])) + " && printf WIRE_READY"

            def pages(name, path):
                raw = path.read_text().rstrip("\n")
                chunks = []
                for index, start in enumerate(range(0, len(raw), 5000)):
                    script = ("from pathlib import Path; import sys; "
                        f"sys.stdout.write('CAPTURE_PAGE {name} {index}\\n' + "
                        f"Path({str(path)!r}).read_text().rstrip('\\n')[{start}:{start + 5000}])")
                    chunks.append(shlex.join([sys.executable, "-c", script]))
                return chunks

            def response(request, number, message):
                phase = stages["phase"]
                if stages["pages"]:
                    cmd = stages["pages"].pop(0)
                elif phase == "start":
                    stages["phase"] = "cold_ready"
                    cmd = invoke("cold")
                elif phase in {"cold_ready", "warm_ready"}:
                    name = phase.split("_")[0]
                    wires[name] = json.loads(wire_paths[name].read_text())
                    assert wires[name]["mode"] == ("full" if name == "cold" else "delta")
                    stages["pages"] = pages(name, wire_paths[name])
                    stages["phase"] = name + "_read"
                    cmd = stages["pages"].pop(0)
                elif phase == "cold_read":
                    assert _delivered(request, "cold") == wire_paths["cold"].read_text().rstrip("\n")
                    stages.update(baseline_confirmed=True, phase="warm_ready")
                    cmd = invoke("warm")
                elif phase == "warm_read":
                    assert _delivered(request, "cold") == wire_paths["cold"].read_text().rstrip("\n")
                    assert _delivered(request, "warm") == wire_paths["warm"].read_text().rstrip("\n")
                    reference.write_text(json.dumps(wires["warm"]["recovery"]))
                    stages.update(phase="compact", compact_response=number)
                    cmd = "printf synthetic-work"
                elif phase == "compact":
                    stages["phase"] = "recovery_ready"
                    message["content"][0]["text"] = "Summary deliberately omitting all packet source bodies."
                    return message
                elif phase == "recovery_ready":
                    assert (home / "epoch-invalidated").read_text() == "compact"
                    assert "Baseline invalidated." in _input_text(request)
                    assert _delivered(request, "cold") == "" and _delivered(request, "warm") == ""
                    stages["phase"] = "recovered"
                    stages["pages"] = pages("recovery", Path(wires["warm"]["recovery"]["path"]))
                    cmd = stages["pages"].pop(0)
                else:
                    assert phase == "recovered"
                    recovered = _delivered(request, "recovery")
                    assert recovered == Path(wires["warm"]["recovery"]["path"]).read_text().rstrip("\n")
                    stages["phase"] = "done"
                    return message
                return {"type": "function_call", "id": f"fc_{number}", "call_id": f"call_{number}",
                    "name": "exec_command", "arguments": json.dumps({"cmd": cmd, "max_output_tokens": 2000})}

            def usage(request, number):
                count = 30000 if number == stages["compact_response"] else 1
                return {"input_tokens": count, "output_tokens": 1, "total_tokens": count + 1}

            def observed_response(request, number, message):
                try:
                    return response(request, number, message)
                except Exception as error:
                    # End the native fixture and report the original assertion,
                    # rather than making Codex retry a broken HTTP connection.
                    errors.append(error)
                    stopped.set()
                    return message

            try:
                with local_inference_provider(observed_response, usage) as (url, calls, observed):
                    _configure_provider(home, url)
                    # The real CLI talks to its isolated local TS Effect process.
                    # Native sandbox networking is disabled by default; allow this
                    # synthetic workspace's loopback transport explicitly.
                    with (home / "config.toml").open("a") as config:
                        config.write("[sandbox_workspace_write]\nnetwork_access=true\n")
                    if host == "exec":
                        result = subprocess.run([binary, "exec", "--dangerously-bypass-hook-trust",
                            "--skip-git-repo-check", "--json", "-s", "workspace-write", "-C", str(workspace),
                            "Synthetic CLI context-delivery fixture."], env=env, capture_output=True, text=True, timeout=90)
                        assert result.returncode == 0, result.stderr
                    else:
                        _app_server(binary, env, workspace, home, True, sandbox="workspace-write")
            finally:
                stopped.set()
                worker.join(2)
            assert not errors, errors
            assert not worker.is_alive()

    assert stages["phase"] == "done"
    assert len(snapshots) == 2  # compaction/readback never invokes a third guard
    assert wire_paths["warm"].stat().st_size < wire_paths["cold"].stat().st_size
    assert len(calls) == len(observed) and stages["baseline_confirmed"]
    projection = Path(wires["warm"]["recovery"]["path"])
    assert hashlib.sha256(projection.read_bytes()).hexdigest() == wires["warm"]["recovery"]["sha256"]
    current = prepare_context_delivery(json.loads(projection.read_bytes()), scope=requests_to_host[-1]["scope"],
        capture_id=wires["warm"]["target"]["capture_id"], surface=surface)
    assert restore_context_delivery(wires["warm"], baseline=wires["cold"], current=current)["context"] == current["context"]
    for document in (wires["cold"]["context"], current["context"]):
        context = (document["work_context"] if surface == "turn_envelope" else
                   document["interaction_contract"]["agent_channel"]["work_context"])
        selected = next(source["content"]["todo"] for source in context["sources"]
                        if source["source"] == "selected_todo")
        assert selected["todo_id"] == TODO_ID and selected["text"] == body
    assert all(path.read_bytes() == raw for path, raw in snapshots)
    assert state.read_bytes() == original_state and _spend_run_count(runtime) == 0
