"""Actual bootstrap/SQLite, artifact, session and leased-continuation owners.

This stage adopts Todo context, not a native/whole research-state continuation.
No model call or historical lease/effect is activated by these fixtures.
"""
import hashlib
import json
import time
from pathlib import Path

import pytest

from loopx.cli import main
from loopx.control_plane.effect_runtime import effect_runtime_result
from benchmark.runtime.research_checkpoint import canonical_context, adopt_todo_context, _encoded
from canonical_authority_fixture import isolate_sqlite_runtime
from loopx.control_plane.turn_driver.codex_sessions import _store_codex_cli_session


def test_retained_context_is_adopted_only_with_fresh_current_ownership(tmp_path, monkeypatch, capsys):
    isolate_sqlite_runtime(tmp_path, monkeypatch)
    workspace = tmp_path / 'branch'
    workspace.mkdir()
    def setup(name, agent):
        registry, root = tmp_path/name/'registry.json', tmp_path/name/'runtime'
        prefix = ['--format','json','--registry',str(registry),'--runtime-root',str(root)]
        def run(*args):
            code = main([*prefix,*args])
            output = capsys.readouterr().out
            assert code == 0, output
            return json.loads(output)
        run('bootstrap','--project',str(workspace),'--goal-id',name,'--objective','Investigate synthetic candidates.',
            '--adapter-kind','read_only_project_map_v0','--adapter-status','connected-read-only','--write-scope','**','--no-global-sync')
        run('configure-goal','--goal-id',name,'--registered-agent',agent,'--agent-work-mode',agent+'=active','--execute')
        todo = run('todo','add','--goal-id',name,'--role','agent','--claimed-by',agent,
            '--task-class','advancement_task','--required-capability','shell','--text','Investigate the retained synthetic candidates.')['todo_id']
        return registry,root,todo,run
    source_registry,source_root,source_todo,source_run = setup('source','source-actor')
    destination_registry,destination_root,destination_todo,run = setup('branch','branch-actor')
    source_env={'LOOPX_RUNTIME_ROOT':str(source_root),'LOOPX_GOAL_ID':'source'}
    source_revision=source_run('todo','list','--goal-id','source','--todo-id',source_todo)['authority_read']['provider_revision']
    source_run('task-lease','acquire','--goal-id','source','--todo-id',source_todo,'--owner','source-actor','--idempotency-key','source-lease')
    # The evidence includes a rejected approach, with its original status/owner.
    source_current=source_run('todo','list','--goal-id','source','--todo-id',source_todo)['authority_read']['provider_revision']
    source_run('todo','update','--goal-id','source','--todo-id',source_todo,'--agent-id','source-actor',
        '--note','Candidate 3 failed the synthetic check; preserve candidate 7.',
        '--update-operation-id','source-evidence','--update-expected-provider-revision',source_current,
        '--task-lease-idempotency-key','source-lease','--task-lease-expected-version','1')
    source_context=canonical_context(source_env,deadline=time.time()+30)
    assert source_context['snapshot']['provider_revision'] != source_revision
    assert 'leases' not in source_context['snapshot']
    raw=_encoded(source_context)
    export=tmp_path/'context.json'
    export.write_bytes(raw)
    unit=tmp_path/'point'
    components=[{'id':'research_context','source_path':str(export)}]
    probe=effect_runtime_result('runtime.checkpoint_artifacts',{'action':'probe','components':components})
    captured=effect_runtime_result('runtime.checkpoint_artifacts',{'action':'capture','destination':str(unit),
        'components':components,'expected_source_sha256':probe['source_sha256'],
        'point_metadata':{'native_session':{'session_id':'source-session'},
            'loopx_state':{'goal_id':'source','agent_id':'source-actor'},
            'research_context':{'component_id':'research_context','member_path':'','sha256':hashlib.sha256(raw).hexdigest(),
                'provider_revision':source_context['snapshot']['provider_revision'],'store_identity':source_context['snapshot']['store_identity']}}})
    digest=captured['sha256']
    env={'LOOPX_REGISTRY':str(destination_registry),'LOOPX_RUNTIME_ROOT':str(destination_root),
        'LOOPX_PROJECT':str(workspace),'LOOPX_GOAL_ID':'branch','LOOPX_AGENT_ID':'branch-actor'}
    _store_codex_cli_session(destination_root,lineage={'goal_id':'branch','agent_id':'branch-actor'},
        session_scope='agent',session_id='branch-session',session_profile_digest='synthetic-profile')
    # This owner-focused fixture substitutes only native history verification.
    # The real Host + CLI + canonical context journey lives in test_native_checkpoint.
    monkeypatch.setattr('benchmark.runtime.research_checkpoint._context_session', lambda *_: 'branch-session')
    before=run('todo','list','--goal-id','branch','--todo-id',destination_todo)
    args=dict(source_todo_id=source_todo,todo_id=destination_todo,operation_id='context-adoption',
        expected_revision=before['authority_read']['provider_revision'],lease_key='branch-lease',lease_version=1)
    with pytest.raises(ValueError,match='execution authority changed'):
        adopt_todo_context(env,unit,digest,**args)
    assert not (workspace/'.local/checkpoint-context').exists()
    lease=run('task-lease','acquire','--goal-id','branch','--todo-id',destination_todo,
        '--owner','branch-actor','--idempotency-key','branch-lease')
    assert lease['lease']['owner']=='branch-actor' and lease['lease']['version']==1
    current=run('todo','list','--goal-id','branch','--todo-id',destination_todo)
    args['expected_revision']=current['authority_read']['provider_revision']
    with pytest.raises(ValueError,match='absent'):
        adopt_todo_context(env,unit,digest,**{**args,'source_todo_id':'missing'})
    with pytest.raises(ValueError,match='execution authority changed'):
        adopt_todo_context(env,unit,digest,**{**args,'expected_revision':'stale-revision'})
    outside=tmp_path/'outside'
    outside.mkdir()
    (workspace/'.local').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):
        adopt_todo_context(env,unit,digest,**args)
    assert list(outside.iterdir())==[]
    (workspace/'.local').unlink()
    source_run('todo','update','--goal-id','source','--todo-id',source_todo,'--agent-id','source-actor',
        '--note','Candidate 999 is later evidence excluded from the captured point.',
        '--update-operation-id','later-source-evidence','--update-expected-provider-revision',source_context['snapshot']['provider_revision'],
        '--task-lease-idempotency-key','source-lease','--task-lease-expected-version','1')
    source_before=source_run('todo','list','--goal-id','source','--todo-id',source_todo)
    result=adopt_todo_context(env,unit,digest,**args)
    assert result['context_adopted'] and result['model_calls']==0 and not result['research_point_qualified']
    assert Path(result['artifact']).read_bytes()==raw
    after=run('todo','list','--goal-id','branch','--todo-id',destination_todo)
    assert after['todo']['claimed_by']=='branch-actor' and after['todo']['status']=='open'
    for key,value in current['todo'].items():
        if key not in {'note','updated_at','last_actor_agent_id'}:
            assert after['todo'].get(key)==value
    note=json.loads(after['todo']['note'])
    assert note['source_session']=='source-session' and 'checkpoint:'+digest in note['source_refs']
    inspected=run('handoff','inspect','--goal-id','branch','--todo-id',destination_todo,'--agent-id','branch-actor',
        '--session-id','branch-session','--workspace',str(workspace),'--artifact',str(Path(result['artifact']).relative_to(workspace)),
        '--task-lease-idempotency-key','branch-lease','--task-lease-expected-version','1')
    assert inspected['can_adopt'] and inspected['availability']['ready']
    assert 'source-revision:'+source_context['snapshot']['provider_revision'] in inspected['evidence_refs']
    assert 'Candidate 3 failed' in Path(result['artifact']).read_text()
    assert 'Candidate 999' not in Path(result['artifact']).read_text()
    assert source_run('todo','list','--goal-id','source','--todo-id',source_todo)==source_before
    assert run('task-lease','inspect','--goal-id','branch','--todo-id',destination_todo)['lease']==lease['lease']
    # The adapter does not mint another receipt/session when retried after commit.
    with pytest.raises(ValueError,match='execution authority changed'):
        adopt_todo_context(env,unit,digest,**args)
    with pytest.raises(ValueError,match='already has context'):
        adopt_todo_context(env,unit,digest,**{**args,'operation_id':'different-operation',
            'expected_revision':after['authority_read']['provider_revision']})
    assert run('todo','list','--goal-id','branch','--todo-id',destination_todo)['todo']==after['todo']
