"""Inert checkpoint capture reuses the real settled-Turn source owner."""
from pathlib import Path
import json
import hashlib
import pytest
import time

import test_quota_settlement_cli as cli
from canonical_authority_fixture import isolate_sqlite_runtime

from benchmark.runtime.checkpoint import capture_after_wake, capture_before_replan
from loopx.control_plane.effect_runtime import effect_runtime_result


def test_feature_off_and_failed_wakes_do_not_read_request_or_settlement(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("feature-off/wake-failure must perform no IO")
    monkeypatch.setattr("benchmark.runtime.checkpoint.read_heartbeat_settlement", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({}, receipt)
    assert receipt == {"ok": True, "stage": "execute", "mode": "heartbeat"}
    assert capture_before_replan({}, receipt, "original body") == "original body"
    failed = {"ok": False, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable"}, failed)
    assert failed["ok"] is False
    assert failed["checkpoint"]["captured"] is False


def test_closed_budget_never_reads_the_request_or_replays_work(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("closed budget must not read sources")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat"}
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable",
                        "LOOPX_PHASE_DEADLINE_EPOCH": str(time.time() - 1)}, receipt)
    assert receipt["ok"] is True
    assert receipt["checkpoint"]["reason"] == "capture_window_closed"
    capture_after_wake({"LOOPX_CHECKPOINT_REQUEST": "not-readable",
                        "LOOPX_PHASE_DEADLINE_EPOCH": "nan"}, receipt)
    assert receipt["ok"] is True
    assert receipt["checkpoint"]["reason"] == "capture_failed"


@pytest.mark.parametrize("trigger", [None, "fresh_replan"])
@pytest.mark.parametrize("failure", ["missing", "denied", "malformed"])
def test_worker_keeps_work_running_when_staged_capture_declaration_fails(
    tmp_path, monkeypatch, trigger, failure,
):
    """Real worker/session/guard; synthetic executable replaces only the model."""
    import os
    import sys
    from benchmark.runtime.worker import run_once

    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    if trigger:
        cli._configure_autonomous_replan_fixture(project, runtime, registry)
    skills = tmp_path / "skills"
    skills.mkdir()
    binary = tmp_path / "codex"
    binary.write_text(f"#!{sys.executable}\n" +
        "import json,pathlib,sys\n"
        "body=sys.stdin.read()\n"
        "pathlib.Path('host-input.txt').write_text(body)\n"
        "pathlib.Path('solution.py').write_text('after_decision = 11\\n')\n"
        "print(json.dumps({'type':'thread.started','thread_id':'synthetic-capture-session'}))\n")
    binary.chmod(0o755)
    logs = tmp_path / "logs"
    request = tmp_path / "request.json"
    declaration = json.dumps({"destination": str(logs / "checkpoints" / "point"),
        "components": [{"id": "code", "source_path": str(project / "solution.py")}],
        "point_metadata": {"purpose": "synthetic worker observer failure"},
        **({"trigger": trigger, "destination": str(logs / "checkpoints")} if trigger else {})})
    request.write_text(declaration)
    env = {**os.environ, "LOOPX_PROJECT": str(project), "LOOPX_CLI": str(Path(sys.executable).parent / "loopx"),
        "LOOPX_CODEX_HOME": str(tmp_path / "home"), "LOOPX_WAKE_LOG_DIR": str(logs / "wakes"),
        "LOOPX_SHARED_SKILLS": str(skills), "CODEX_BIN": str(binary),
        "MODEL_NAME": "fixture", "REASONING_EFFORT": "high", "OPENAI_BASE_URL": "http://localhost:8123/v1",
        "OPENAI_API_KEY": "fixture-key", "LOOPX_RUNTIME_ROOT": str(runtime),
        "LOOPX_REGISTRY": str(registry), "LOOPX_GOAL_ID": cli.GOAL_ID, "LOOPX_AGENT_ID": cli.AGENT_ID}
    monkeypatch.setattr("benchmark.runtime.worker.heartbeat_body", lambda *a, **kw: "original work contract")
    off = run_once(env)
    assert off["ok"] and "checkpoint" not in off
    (project / "host-input.txt").unlink()
    if failure == "missing":
        request.unlink()
    elif failure == "malformed":
        request.write_text("{")
    read_bytes = Path.read_bytes
    with monkeypatch.context() as faults:
        if failure == "denied":
            def denied_read(path):
                if path == request:
                    raise PermissionError("synthetic staged-file permission loss")
                return read_bytes(path)
            faults.setattr(Path, "read_bytes", denied_read)
        failed = run_once({**env, "LOOPX_CHECKPOINT_REQUEST": str(request)})
    assert failed["ok"] and failed["session"]["session_id"] == "synthetic-capture-session"
    assert (project / "host-input.txt").read_text().endswith("original work contract")
    assert failed["checkpoint"]["reason"] == "capture_failed"
    assert not failed["checkpoint"]["captured"]
    saved = json.loads((logs / "wakes" / failed["turn_id"] / "receipt.json").read_text())
    assert saved == failed
    request.write_text(declaration)
    if trigger:
        # A repaired declaration cannot label the model's later code as the
        # original missed pre-decision point, even on exact guard replay.
        replay = {"turn_id": failed["turn_id"], "mode": "heartbeat", "stage": "execute", "ok": False}
        body = capture_before_replan({**env, "LOOPX_CHECKPOINT_REQUEST": str(request)}, replay,
                                     "original work contract")
        assert replay["checkpoint"]["reason"] == "pre_decision_capture_already_attempted", replay
        assert body.endswith("original work contract")
        assert not list((logs / "checkpoints").glob("replan-*/checkpoint.json"))
    recovered = run_once({**env, "LOOPX_CHECKPOINT_REQUEST": str(request)})
    assert recovered["ok"]
    if trigger:
        # An unavailable declaration is optional; an unavailable original
        # admission owner is not. This boundary must still stop before work.
        import subprocess
        (project / "host-input.txt").unlink()
        request.unlink()
        registry.rename(registry.with_suffix(".unavailable"))
        with pytest.raises(subprocess.CalledProcessError):
            run_once({**env, "LOOPX_CHECKPOINT_REQUEST": str(request)})
        assert not (project / "host-input.txt").exists()


@pytest.mark.parametrize("opportunity,corrupt", [(False, False), (True, False), (True, True)])
def test_real_cli_settlement_capture_verification_and_inert_materialization(tmp_path, monkeypatch, opportunity, corrupt):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    binding = ("--agent-id", cli.AGENT_ID, "--todo-id", cli.TODO_ID, "--turn-instance-id", cli.TURN_ID)
    def run(*args):
        code, result = cli._run_cli(registry, runtime, *args)
        assert code == 0, result
        return result
    run("quota", "should-run", "--goal-id", cli.GOAL_ID, "--codex-app", *binding)
    logs = tmp_path / "logs"
    wake = logs / "wakes"
    wake.mkdir(parents=True)
    (wake / cli.TURN_ID).mkdir()
    observed = []
    incumbent_bytes = b"opaque older adopted candidate"
    opportunity_packet = {"meaning": "synthetic opportunity participant; no admission", "native_incumbent": {
        "round": "agent-1", "archive_sha256": hashlib.sha256(incumbent_bytes).hexdigest(), "archive_bytes": len(incumbent_bytes)}}
    def export(env, *, timeout, incumbent_path):
        assert 0 < timeout <= 30
        observed.append(True)
        incumbent_path.write_bytes(incumbent_bytes)
        return opportunity_packet
    monkeypatch.setattr("benchmark.runtime.sforge_checkpoint.capture_opportunity", export)
    if corrupt:
        def altered_probe(method, params, **kwargs):
            if params["action"] == "probe":
                next(wake.glob("*/checkpoint-incumbent.tar.gz")).write_bytes(b"altered after transport")
            return effect_runtime_result(method, params, **kwargs)
        monkeypatch.setattr("benchmark.runtime.checkpoint.effect_runtime_result", altered_probe)
    (project / "solution.py").write_text("retained_candidate = 7\n")
    request = tmp_path / "request.json"
    target = logs / "checkpoints" / "point"
    request.write_text(json.dumps({"destination": str(target), "components": [
        {"id": "code", "source_path": str(project / "solution.py")},
        {"id": "research", "source_path": str(project / f".codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md")},
    ], "point_metadata": {"meaning": "synthetic capture; no model/session or evaluator qualification"},
        **({"evaluation_opportunity": True} if opportunity else {})}))
    env = {"LOOPX_CHECKPOINT_REQUEST": str(request), "LOOPX_WAKE_LOG_DIR": str(wake),
        "LOOPX_RUNTIME_ROOT": str(runtime), "LOOPX_GOAL_ID": cli.GOAL_ID,
        "LOOPX_AGENT_ID": cli.AGENT_ID, "LOOPX_REGISTRY": str(registry)}
    receipt = {"ok": True, "stage": "execute", "mode": "heartbeat", "turn_id": cli.TURN_ID}
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "owned_turn_not_settled"
    assert not target.exists()
    assert observed == []
    vision = tmp_path / "vision.json"
    vision.write_text(json.dumps({"schema_version": "goal_vision_replan_contract_v0", "state": "vision_patch_proposed",
        "vision_patch": {"acceptance_summary": "Synthetic source fixture checked; checkpoint work remains."},
        "path_delta": {"outcome": "continue", "prior_assumption": "Fixture source is available.",
            "observed_reality": "The isolated source fixture was verified.", "retained": ["Inert checkpoint qualification"],
            "evidence_refs": ["evidence:synthetic-capture"]}}))
    run("refresh-state", "--goal-id", cli.GOAL_ID, *binding, "--classification", "checkpoint_fixture_verified",
        "--delivery-batch-scale", "multi_surface", "--delivery-outcome", "outcome_progress", "--agent-vision-json", str(vision))
    run("quota", "spend-slot", "--goal-id", cli.GOAL_ID, *binding, "--source", "heartbeat", "--execute")
    goal_state = project / f".codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md"
    retained_goal = goal_state.read_bytes()
    capture_after_wake(env, receipt)
    assert receipt["ok"] is True
    if corrupt:
        assert receipt["checkpoint"]["captured"] is False and not target.exists()
        assert "differs" in receipt["checkpoint"]["error"]
        assert goal_state.read_bytes() == retained_goal
        return
    assert receipt["checkpoint"].get("captured") is True, receipt
    assert receipt["checkpoint"]["research_point_qualified"] is False
    assert goal_state.read_bytes() == retained_goal
    if opportunity:
        assert json.loads((target / "components/evaluation_opportunity").read_text()) == opportunity_packet
        assert (target / "components/evaluation_incumbent").read_bytes() == incumbent_bytes

    digest = receipt["checkpoint"]["sha256"]
    restored = effect_runtime_result("runtime.checkpoint_artifacts", {"action": "materialize", "root": str(target),
        "expected_sha256": digest, "destination": str(tmp_path / "inert")})
    assert restored["activation_performed"] is False
    assert (tmp_path / "inert/components/code").read_text() == "retained_candidate = 7\n"
    if opportunity:
        assert (tmp_path / "inert/components/evaluation_incumbent").read_bytes() == incumbent_bytes
    before = (target / "checkpoint.json").read_bytes()
    capture_after_wake(env, receipt)
    assert receipt["checkpoint"]["reason"] == "destination_already_present_no_replay"
    assert (target / "checkpoint.json").read_bytes() == before
    assert goal_state.read_bytes() == retained_goal
    assert len(observed) == int(opportunity)


@pytest.mark.parametrize("capture_fails", [False, True])
def test_real_pre_replan_capture_is_before_decision_and_same_node_is_not_recaptured(tmp_path, monkeypatch, capture_fails):
    import os
    import sys

    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    binding = ("--agent-id", cli.AGENT_ID, "--todo-id", cli.TODO_ID, "--turn-instance-id", cli.TURN_ID)

    def run(*args):
        code, result = cli._run_cli(registry, runtime, *args)
        assert code == 0, result
        return result

    run("quota", "should-run", "--goal-id", cli.GOAL_ID, "--codex-app", *binding)
    vision = tmp_path / "vision.json"
    vision.write_text(json.dumps({"schema_version": "goal_vision_replan_contract_v0", "state": "vision_patch_proposed",
        "vision_patch": {"acceptance_summary": "Synthetic source fixture checked; capture work remains."},
        "path_delta": {"outcome": "continue", "prior_assumption": "Source fixture is available.",
            "observed_reality": "Isolated source fixture verified.", "retained": ["Capture qualification"],
            "evidence_refs": ["evidence:synthetic-pre-replan"]}}))
    run("refresh-state", "--goal-id", cli.GOAL_ID, *binding, "--classification", "pre_replan_fixture_verified",
        "--delivery-batch-scale", "multi_surface", "--delivery-outcome", "outcome_progress", "--agent-vision-json", str(vision))
    run("quota", "spend-slot", "--goal-id", cli.GOAL_ID, *binding, "--source", "heartbeat", "--execute")
    index = runtime / "goals" / cli.GOAL_ID / "runs/index.jsonl"
    original_settlement = index.read_bytes()
    cli._configure_autonomous_replan_fixture(project, runtime, registry)
    # This helper supplies synthetic repeated observations; retain the real
    # source settlement history instead of replacing its authoritative readback.
    index.write_bytes(original_settlement + index.read_bytes())
    logs = tmp_path / "logs"
    wakes = logs / "wakes"
    prior = wakes / "wake-100-prior"
    prior.mkdir(parents=True)
    prior_receipt = {"turn_id": cli.TURN_ID, "mode": "heartbeat", "stage": "execute", "ok": True}
    (prior / "receipt.json").write_text(json.dumps(prior_receipt))
    solution = project / "solution.py"
    solution.write_text("retained_candidate = 7\n")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"trigger": "fresh_replan", "loopx_state": True, "destination": str(logs / "checkpoints"),
        "components": [{"id": "code", "source_path": str(solution)}],
        "point_metadata": {"purpose": "synthetic original settlement and replan ordering"}}))
    env = {**os.environ, "LOOPX_CLI": str(Path(sys.executable).parent / "loopx"),
        "LOOPX_PROJECT": str(project), "LOOPX_CHECKPOINT_REQUEST": str(request),
        "LOOPX_WAKE_LOG_DIR": str(wakes), "LOOPX_RUNTIME_ROOT": str(runtime),
        "LOOPX_GOAL_ID": cli.GOAL_ID, "LOOPX_AGENT_ID": cli.AGENT_ID, "LOOPX_REGISTRY": str(registry)}
    receipt = {"turn_id": "synthetic-replan-point", "mode": "heartbeat", "stage": "execute", "ok": False}
    (wakes / receipt["turn_id"]).mkdir()
    attempted = []
    if capture_fails:
        def fail_probe(method, params, **kwargs):
            if params["action"] == "probe":
                attempted.append(True)
                raise RuntimeError("synthetic capture failure")
            return effect_runtime_result(method, params, **kwargs)
        monkeypatch.setattr("benchmark.runtime.checkpoint.effect_runtime_result", fail_probe)
    body = capture_before_replan(env, receipt, "original instructions")
    if capture_fails:
        assert receipt["checkpoint"]["reason"] == "capture_failed", receipt
        solution.write_text("later_decision = 11\n")
        again = {"turn_id": receipt["turn_id"], "mode": "heartbeat", "stage": "execute", "ok": False}
        capture_before_replan(env, again, "original instructions")
        assert again["checkpoint"]["reason"] == "pre_decision_capture_already_attempted", again
        assert attempted == [True] and not list((logs / "checkpoints").glob("replan-*/checkpoint.json"))
        assert body.endswith("original instructions") and receipt["ok"] is False
        return
    assert receipt["checkpoint"]["captured"] is True, json.dumps(receipt)
    target = Path(receipt["checkpoint"]["destination"])
    captured = (target / "checkpoint.json").read_bytes()
    assert (target / "components/code").read_text() == "retained_candidate = 7\n"
    assert body.endswith("original instructions") and "original quota guard once" in body
    assert receipt["ok"] is False  # Capturing cannot declare the new work completed.
    assert (prior / "receipt.json").read_text() == json.dumps(prior_receipt)
    # The model's subsequent decision/work must not replace the pre-decision point.
    solution.write_text("new_route = 11\n")
    capture_after_wake(env, receipt)
    assert (target / "checkpoint.json").read_bytes() == captured
    # Reentry on the exact original guard reads back one point, even if code moved.
    again = {"turn_id": receipt["turn_id"], "mode": "heartbeat", "stage": "execute", "ok": False}
    capture_before_replan(env, again, "original instructions")
    assert again["checkpoint"]["reason"] == "replan_already_captured", json.dumps(again)
    assert (target / "checkpoint.json").read_bytes() == captured


@pytest.mark.parametrize('provider', ['file', 'sqlite'])
def test_controller_participant_keeps_canonical_state_and_journals_inert(tmp_path, monkeypatch, provider):
    from canonical_authority_fixture import initialize_canonical_authority
    from loopx.control_plane.coordination.runtime_shadow import build_todo_runtime_shadow_projection
    from loopx.control_plane.goals.first_party_host_admission import capture_first_party_host_goal_ref
    from loopx.control_plane.quota.settlement import read_heartbeat_settlement
    import subprocess

    def authority_head(root):
        module = Path(__file__).resolve().parents[2]/'loopx/control_plane/coordination/local_authority_provider.ts'
        script = ('import {openLocalAuthorityStore} from '+json.dumps(module.as_uri())+';'
            "let input='';for await(const chunk of process.stdin)input+=chunk;"
            'const x=JSON.parse(input);const store=await openLocalAuthorityStore(x.root,x.goal,{}, {existingOnly:true});'
            'process.stdout.write(JSON.stringify(await store.loadAuthority()));')
        result = subprocess.run(['node','--no-warnings','--experimental-strip-types','--input-type=module','-e',script],
            input=json.dumps({'root':str(root),'goal':cli.GOAL_ID}),capture_output=True,text=True,timeout=45)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    isolate_sqlite_runtime(tmp_path, monkeypatch)
    project, runtime, registry = cli._write_fixture(tmp_path)
    source_ref = capture_first_party_host_goal_ref(registry_path=registry, goal_id=cli.GOAL_ID)
    state = project / f'.codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md'
    code, listed = cli._run_cli(registry, runtime, 'todo', 'list', '--goal-id', cli.GOAL_ID)
    assert code == 0, listed
    initialize_canonical_authority(runtime, cli.GOAL_ID,
        build_todo_runtime_shadow_projection(goal_id=cli.GOAL_ID, todos=listed['todos'],
                                            handoff_mode='hard_lease', leases=[]),
        state_path=state, provider=provider)
    def run(*args):
        code, result = cli._run_cli(registry, runtime, *args)
        assert code == 0 and result['ok'] is True, result
        return result
    lease = run('task-lease', 'acquire', '--goal-id', cli.GOAL_ID, '--todo-id', cli.TODO_ID,
                '--owner', cli.AGENT_ID, '--idempotency-key', 'source-lease')
    binding = ('--agent-id', cli.AGENT_ID, '--todo-id', cli.TODO_ID, '--turn-instance-id', cli.TURN_ID)
    run('quota', 'should-run', '--goal-id', cli.GOAL_ID, '--codex-app', *binding)
    vision = tmp_path / 'vision.json'
    vision.write_text(json.dumps({'schema_version':'goal_vision_replan_contract_v0', 'state':'vision_patch_proposed',
        'vision_patch':{'acceptance_summary':'Controlled participant probe passed; research continuation remains.'},
        'path_delta':{'outcome':'continue','prior_assumption':'Capture requires settled original work.',
            'observed_reality':'Isolated source work was verified.', 'retained':['Participant capture'],
            'evidence_refs':['evidence:controller-fixture']}}))
    run('refresh-state', '--goal-id', cli.GOAL_ID, *binding, '--classification','controller_fixture_verified',
        '--delivery-batch-scale','multi_surface','--delivery-outcome','outcome_progress','--agent-vision-json',str(vision))
    run('quota','spend-slot','--goal-id',cli.GOAL_ID,*binding,'--source','heartbeat','--execute')
    before = run('todo','list','--goal-id',cli.GOAL_ID,'--todo-id',cli.TODO_ID)
    original_head = authority_head(runtime)
    assert original_head['status'] == 'loaded'
    source_settlement = read_heartbeat_settlement(runtime, goal_id=cli.GOAL_ID,agent_id=cli.AGENT_ID,
        todo_id=cli.TODO_ID,turn_instance_id=cli.TURN_ID,registry_path=registry)
    assert source_settlement.progress['state'] == 'settled'
    logs = tmp_path / 'logs'
    wakes = logs / 'wakes'
    (wakes / cli.TURN_ID).mkdir(parents=True)
    (project / 'solver.py').write_text('candidate = 7\n')
    target = logs / 'checkpoints/controller'
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'destination':str(target), 'loopx_state':True,
        'components':[{'id':'code','source_path':str(project/'solver.py')}], 'point_metadata':{}}))
    env = {'LOOPX_CHECKPOINT_REQUEST':str(request),'LOOPX_WAKE_LOG_DIR':str(wakes),
        'LOOPX_PROJECT':str(project),'LOOPX_RUNTIME_ROOT':str(runtime),'LOOPX_REGISTRY':str(registry),
        'LOOPX_GOAL_ID':cli.GOAL_ID,'LOOPX_AGENT_ID':cli.AGENT_ID}
    receipt = {'ok':True,'stage':'execute','mode':'heartbeat','turn_id':cli.TURN_ID}
    capture_after_wake(env, receipt)
    assert receipt['checkpoint'].get('captured') is True, json.dumps(receipt['checkpoint'])
    manifest = json.loads((target/'checkpoint.json').read_text())
    coverage = manifest['point_metadata']['loopx_state']['source_inventory']
    covered = {entry['source_path']:entry['component_id'] for entry in coverage}
    assert str(runtime) in covered and str(registry) in covered and str(state) in covered
    materialized = tmp_path / 'materialized'
    effect_runtime_result('runtime.checkpoint_artifacts', {'action':'materialize','root':str(target),
        'expected_sha256':receipt['checkpoint']['sha256'],'destination':str(materialized)})
    copied_runtime = materialized/'components'/covered[str(runtime)]
    assert authority_head(copied_runtime) == original_head
    copied_code, copied_todos = cli._run_cli(registry, copied_runtime, 'todo', 'list',
        '--goal-id', cli.GOAL_ID, '--todo-id', cli.TODO_ID)
    assert copied_code == 0, copied_todos
    assert copied_todos['todo'] == before['todo']
    assert copied_todos['authority_read']['source_authority'] == provider + '_v0'
    copied = read_heartbeat_settlement(copied_runtime,goal_id=cli.GOAL_ID,agent_id=cli.AGENT_ID,
        todo_id=cli.TODO_ID,turn_instance_id=cli.TURN_ID,registry_path=registry)
    assert copied.progress['state'] == 'settled' and copied.identity.value == source_settlement.identity.value
    registry_copy = materialized/'components'/covered[str(registry)]/manifest['point_metadata']['loopx_state']['registry_member_path']
    assert registry_copy.read_bytes() == registry.read_bytes()
    assert manifest['research_point_qualified'] is False and manifest['execution_authority_granted'] is False
    assert source_ref is None  # Preserve this legacy fixture; capture does not create an exact GoalRef.
    assert lease['lease']['status'] == 'active'
    after = run('todo','list','--goal-id',cli.GOAL_ID,'--todo-id',cli.TODO_ID)
    assert after['todo'] == before['todo']
    assert after['authority_read']['provider_revision'] == before['authority_read']['provider_revision']


@pytest.mark.parametrize('gap', ['shared_registry','wrong_actor','wrong_runtime','missing_state','symlink_state','overlap'])
def test_loopx_participant_rejects_wrong_or_ambiguous_routes(tmp_path, gap):
    from benchmark.runtime.checkpoint import _loopx_state_components
    project, runtime, registry = cli._write_fixture(tmp_path)
    runtime.mkdir()
    (project/'solver.py').write_text('candidate = 7\n')
    env = {'LOOPX_PROJECT':str(project),'LOOPX_RUNTIME_ROOT':str(runtime),'LOOPX_REGISTRY':str(registry),
        'LOOPX_GOAL_ID':cli.GOAL_ID,'LOOPX_AGENT_ID':cli.AGENT_ID}
    state = project/f'.codex/goals/{cli.GOAL_ID}/ACTIVE_GOAL_STATE.md'
    components = [{'id':'code','source_path':str(project/'solver.py')}]
    source = json.loads(registry.read_text())
    if gap == 'shared_registry':
        source['goals'].append({**source['goals'][0],'id':'other-goal'})
        registry.write_text(json.dumps(source))
    elif gap == 'wrong_actor':
        env['LOOPX_AGENT_ID'] = 'other-agent'
    elif gap == 'wrong_runtime':
        other = tmp_path/'other'
        other.mkdir()
        env['LOOPX_RUNTIME_ROOT'] = str(other)
    elif gap == 'missing_state':
        state.unlink()
    elif gap == 'symlink_state':
        state.unlink()
        state.symlink_to(project/'solver.py')
    else:
        components.append({'id':'narrow','source_path':str(registry)})
    with pytest.raises(ValueError):
        _loopx_state_components(env, components, tmp_path/'logs/checkpoints/point')
    assert not (tmp_path/'logs').exists()


def test_loopx_participant_preserves_legacy_and_current_owned_goal_directories(tmp_path):
    from benchmark.runtime.checkpoint import _loopx_state_components, parse_checkpoint_request
    project, runtime, registry = cli._write_fixture(tmp_path)
    # These are legitimate controller partitions, not two Goal registrations.
    # Inventory follows the backup owner, not a basename-based Goal classifier.
    for name in (cli.GOAL_ID, cli.GOAL_ID+'-partition'):
        (runtime/'goals'/name).mkdir(parents=True)
    components, metadata = _loopx_state_components({'LOOPX_PROJECT':str(project),
        'LOOPX_RUNTIME_ROOT':str(runtime),'LOOPX_REGISTRY':str(registry),
        'LOOPX_GOAL_ID':cli.GOAL_ID,'LOOPX_AGENT_ID':cli.AGENT_ID}, [], tmp_path/'logs/checkpoints/point')
    assert sum(entry['source_path'] == str(runtime) for entry in components) == 1
    assert metadata['execution_authority_granted'] is False
    with pytest.raises(ValueError, match='explicit boolean'):
        parse_checkpoint_request(json.dumps({'destination':'/logs/agent/checkpoints/point',
            'components':[{'id':'code','source_path':'/tmp/solver.py'}], 'point_metadata':{},
            'loopx_state':'true'}).encode())
