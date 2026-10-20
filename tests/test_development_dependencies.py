"""Checkout dependency reuse must fail closed on changed or broken installs."""
import json
import subprocess
import time

import pytest

from scripts import development_dependencies as deps


@pytest.fixture
def node(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / 'package.json').write_text('{"dependencies":{"example":"1.0.0"}}')
    lock = {'lockfileVersion': 3, 'packages': {'node_modules/example': {
        'version': '1.0.0', 'integrity': 'test', 'resolved': 'https://example.invalid/pkg'}}}
    (root / 'package-lock.json').write_text(json.dumps(lock))
    calls = []
    monkeypatch.setattr(deps, '_tool', lambda name: name)
    monkeypatch.setattr(deps.subprocess, 'check_output', lambda *a, **kw: 'v1')

    def install():
        target = root / 'node_modules'
        (target / 'example').mkdir(parents=True, exist_ok=True)
        (target / '.package-lock.json').write_text(json.dumps(lock))
        (target / 'example/package.json').write_text('{"name":"example","version":"1.0.0"}')

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == 'ci':
            install()
        return subprocess.CompletedProcess(command, 0, stdout='')

    monkeypatch.setattr(deps.subprocess, 'run', run)
    return root, calls, install


def test_cold_install_then_reuse_and_changed_lock_reinstall(node):
    root, calls, _ = node
    assert deps.ensure_node_dependencies(root, 'node')
    assert not deps.ensure_node_dependencies(root, 'node')
    (root / 'package-lock.json').write_text((root / 'package-lock.json').read_text() + '\n')
    assert deps.ensure_node_dependencies(root, 'node')
    assert len([c for c in calls if c[1] == 'ci']) == 2


def test_adopt_existing_pure_js_without_install(node):
    root, calls, install = node
    install()
    assert not deps.ensure_node_dependencies(root, 'node')
    assert not any(c[1] == 'ci' for c in calls)


def test_unknown_native_install_gets_rebuilt(node):
    root, _, install = node
    install()
    (root / 'node_modules/example/addon.node').touch()
    assert deps.ensure_node_dependencies(root, 'node')


def test_missing_metadata_and_force_trigger_install(node):
    root, _, _ = node
    deps.ensure_node_dependencies(root, 'node')
    (root / 'node_modules/example/package.json').unlink()
    assert deps.ensure_node_dependencies(root, 'node')
    assert deps.ensure_node_dependencies(root, 'node', force=True)


def test_missing_executable_is_unhealthy(node):
    root, _, install = node
    install()
    (root / 'node_modules/example/package.json').write_text(
        '{"name":"example","version":"1.0.0","bin":{"example":"cli.js"}}')
    (root / 'node_modules/example/cli.js').touch()
    assert not deps._healthy_node_tree(root, 'npm')


def test_tool_version_and_script_policy_invalidate_receipt(node, monkeypatch):
    root, _, _ = node
    deps.ensure_node_dependencies(root, 'node')
    monkeypatch.setattr(deps.subprocess, 'check_output', lambda *a, **kw: 'v2')
    assert deps.ensure_node_dependencies(root, 'node')
    assert deps.ensure_node_dependencies(root, 'node', ignore_scripts=False)


def test_failed_install_does_not_leave_success_receipt(node, monkeypatch):
    root, _, _ = node
    deps.ensure_node_dependencies(root, 'node')
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ['npm', 'ci'])
    monkeypatch.setattr(deps.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        deps.ensure_node_dependencies(root, 'node', force=True)
    assert not (root / 'node_modules/.loopx-development-dependencies.json').exists()


def test_symlink_target_rejected(node, tmp_path):
    root, _, _ = node
    other = root / 'other'
    other.mkdir()
    (root / 'node_modules').symlink_to(other, target_is_directory=True)
    with pytest.raises(RuntimeError, match='symlinks'):
        deps.ensure_node_dependencies(root, 'node')


def test_python_uses_uv_sync_without_external_environment(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv('UV_PROJECT_ENVIRONMENT', '/unrelated')
    monkeypatch.setattr(deps, '_tool', lambda name: name)
    def run(command, **kwargs):
        calls.append((command, kwargs))
        (tmp_path / '.venv').mkdir(exist_ok=True)
    monkeypatch.setattr(deps.subprocess, 'run', run)
    deps.prepare_python(tmp_path.resolve(), 'python-core')
    assert calls[0][0] == ['uv', 'sync', '--extra', 'test-core']
    assert 'UV_PROJECT_ENVIRONMENT' not in calls[0][1]['env']


def test_retirement_requires_old_owned_idle_restoreable_install(node, monkeypatch):
    root, _, _ = node
    assert deps.retire(root, 'node', days=7, apply=False)['action'] == 'retain'
    deps.ensure_node_dependencies(root, 'node')
    receipt = root / 'node_modules/.loopx-development-dependencies.json'
    old = json.loads(receipt.read_text())
    old['last_used'] = time.time() - 8 * 86400
    receipt.write_text(json.dumps(old))
    monkeypatch.setattr(deps, '_in_use', lambda _: True)
    assert deps.retire(root, 'node', days=7, apply=True)['action'] == 'retain'
    monkeypatch.setattr(deps, '_in_use', lambda _: False)
    assert deps.retire(root, 'node', days=7, apply=False)['action'] == 'would_remove'
    assert receipt.exists()
    (root / 'package-lock.json').unlink()
    assert deps.retire(root, 'node', days=7, apply=True)['action'] == 'retain'
    (root / 'package-lock.json').write_text('{}')
    assert deps.retire(root, 'node', days=7, apply=True)['action'] == 'removed'


def test_broken_dependency_graph_never_gets_receipt(node, monkeypatch):
    root, _, install = node
    def run(command, **kwargs):
        if command[1] == 'ci':
            install()
        return subprocess.CompletedProcess(command, 1 if command[1] == 'ls' else 0)
    monkeypatch.setattr(deps.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='incomplete'):
        deps.ensure_node_dependencies(root, 'node')
    assert not (root / 'node_modules/.loopx-development-dependencies.json').exists()


def test_root_lifecycle_script_prevents_legacy_adoption(node):
    root, _, install = node
    install()
    (root / 'package.json').write_text('{"scripts":{"prepare":"echo build"}}')
    assert deps.ensure_node_dependencies(root, 'node')


def test_unknown_process_visibility_holds_retirement(tmp_path, monkeypatch):
    monkeypatch.setattr(deps.shutil, 'which', lambda _: None)
    assert deps._in_use(tmp_path.resolve())


def test_tracked_dependency_files_hold_retirement(node, monkeypatch):
    root, _, _ = node
    deps.ensure_node_dependencies(root, 'node')
    receipt = root / 'node_modules/.loopx-development-dependencies.json'
    old = json.loads(receipt.read_text())
    old['last_used'] = time.time() - 8 * 86400
    receipt.write_text(json.dumps(old))
    monkeypatch.setattr(deps.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 0, stdout='node_modules/important'))
    monkeypatch.setattr(deps, '_in_use', lambda _: False)
    assert deps.retire(root, 'node', days=7, apply=True)['reason'] == 'tracked_files_or_git_unavailable'
    assert receipt.exists()
