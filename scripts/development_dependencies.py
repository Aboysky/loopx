#!/usr/bin/env python3
"""Prepare scoped checkout dependencies and preview retirement of idle installs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

if sys.version_info < (3, 11):
    raise SystemExit("LoopX dependency setup requires Python 3.11 or newer")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loopx.file_lock import exclusive_file_lock, write_bytes_atomic

NODE_PROJECTS = {
    "node": ".",
    "dashboard": "apps/presentation/dashboard",
    "site": "apps/presentation/site",
    "desktop": "apps/desktop/loopx-control-plane",
}
SCOPES = ("python-core", "python-full", *NODE_PROJECTS)


def _target(root: Path, scope: str) -> tuple[Path, Path, Path]:
    if scope not in SCOPES:
        raise ValueError(f"unknown dependency scope: {scope}")
    project = root / NODE_PROJECTS[scope] if scope in NODE_PROJECTS else root
    target = project / ("node_modules" if scope in NODE_PROJECTS else ".venv")
    # A dependency folder linked to another checkout is not ours to replace.
    if any(p.is_symlink() for p in (project, *project.parents, target)):
        raise RuntimeError("dependency project and environment must not be symlinks")
    if not project.resolve().is_relative_to(root.resolve()):
        raise RuntimeError("dependency project escapes the checkout")
    receipt = target / ".loopx-development-dependencies.json"
    return project, target, receipt


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _tool(name: str) -> str:
    value = shutil.which(name + ".cmd" if os.name == "nt" and name == "npm" else name)
    if value is None:
        raise RuntimeError(f"{name} is required to prepare these dependencies")
    return value


def _node_key(project: Path, npm: str, ignore_scripts: bool) -> dict:
    files = ("package.json", "package-lock.json", ".npmrc")
    if not all((project / name).is_file() for name in files[:2]):
        raise RuntimeError("Node dependency setup requires package.json and package-lock.json")
    # Hash configuration values rather than persisting registry credentials.
    configuration = {
        key: value for key, value in os.environ.items()
        if key.lower().startswith("npm_config_") or key == "NODE_ENV"
    }
    configuration["effective_config"] = subprocess.check_output(
        [npm, "config", "list", "--json"], cwd=project, text=True,
        stderr=subprocess.DEVNULL,
    )
    return {
        "files": {name: _digest(project / name) for name in files},
        "node": subprocess.check_output([_tool("node"), "--version"], text=True).strip(),
        "npm": subprocess.check_output([npm, "--version"], text=True).strip(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "ignore_scripts": ignore_scripts,
        "configuration": hashlib.sha256(
            json.dumps(configuration, sort_keys=True).encode()
        ).hexdigest(),
    }


def _save(receipt: Path, root: Path, scope: str, key: dict) -> None:
    write_bytes_atomic(receipt, (json.dumps({
        "checkout": str(root.resolve()),
        "scope": scope,
        "key": key,
        "last_used": time.time(),
    }, sort_keys=True) + "\n").encode())


def _healthy_node_tree(project: Path, npm: str) -> bool:
    target = project / "node_modules"
    packages = _read(target / ".package-lock.json").get("packages")
    if not isinstance(packages, dict):
        return False
    for name in packages:
        path = project / name
        if not path.resolve().is_relative_to(target.resolve()):
            return False
        metadata = _read(path / "package.json")
        if not metadata:
            return False
        bins = metadata.get("bin") or {}
        if isinstance(bins, str):
            bins = {metadata.get("name", "").rsplit("/", 1)[-1]: bins}
        if not isinstance(bins, dict):
            return False
        for command, relative in bins.items():
            if not isinstance(relative, str) or not (path / relative).is_file():
                return False
            # npm puts executables in the nearest node_modules/.bin directory.
            modules = next((p for p in path.parents if p.name == "node_modules"), target)
            executable = modules / ".bin" / (command + (".cmd" if os.name == "nt" else ""))
            if not executable.is_file():
                return False
    return subprocess.run(
        [npm, "ls", "--all", "--include=dev", "--json"], cwd=project,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def _adoptable_node_tree(project: Path, target: Path, npm: str) -> bool:
    """Accept an existing pure-JS install only with matching lock provenance."""
    lifecycle = ("preinstall", "install", "postinstall", "prepare")
    if any(key in (_read(project / "package.json").get("scripts") or {}) for key in lifecycle):
        return False
    wanted = _read(project / "package-lock.json")
    installed = _read(target / ".package-lock.json")
    if wanted.get("lockfileVersion") != 3 or installed.get("lockfileVersion") != 3:
        return False
    packages = installed.get("packages")
    expected = wanted.get("packages")
    if not isinstance(packages, dict) or not packages or not isinstance(expected, dict):
        return False
    for name, entry in packages.items():
        source = expected.get(name)
        if not isinstance(entry, dict) or not isinstance(source, dict):
            return False
        if entry.get("link") or any(
            entry.get(key) != source.get(key) for key in ("version", "resolved", "integrity")
        ):
            return False
        # Do not infer native ABI or lifecycle-script compatibility from a lock.
        path = project / name
        if not path.resolve().is_relative_to(target.resolve()) or path.is_symlink():
            return False
        metadata = _read(path / "package.json")
        if metadata.get("version") != source.get("version"):
            return False
        scripts = metadata.get("scripts") or {}
        if any(key in scripts for key in ("preinstall", "install", "postinstall")):
            return False
        bins = metadata.get("bin") or {}
        if isinstance(bins, str):
            bins = {metadata.get("name", ""): bins}
        if not isinstance(bins, dict):
            return False
        if any(not isinstance(value, str) or not (path / value).is_file() for value in bins.values()):
            return False
    if any(target.rglob("*.node")):
        return False
    return _healthy_node_tree(project, npm)


def ensure_node_dependencies(
    root: Path, scope: str, *, ignore_scripts: bool = True, force: bool = False
) -> bool:
    """Return True only when npm ci ran; serialize managed installs per checkout."""
    if scope not in NODE_PROJECTS:
        raise ValueError("a Node scope is required")
    root = root.resolve()
    with exclusive_file_lock(root / ".local/development-dependencies", timeout_seconds=300):
        project, target, receipt = _target(root, scope)
        npm = _tool("npm")
        key = _node_key(project, npm, ignore_scripts)
        old = _read(receipt)
        reusable = (
            not force
            and old.get("checkout") == str(root)
            and old.get("scope") == scope
            and old.get("key") == key
            and (target / ".package-lock.json").is_file()
            and old.get("installed_lock") == _digest(target / ".package-lock.json")
        )
        if reusable:
            reusable = _healthy_node_tree(project, npm)
        elif not force and not old and target.is_dir():
            reusable = _adoptable_node_tree(project, target, npm)
        if not reusable:
            receipt.unlink(missing_ok=True)
            args = [npm, "ci", "--prefer-offline"]
            if ignore_scripts:
                args.append("--ignore-scripts")
            subprocess.run(args, cwd=project, check=True)
            if key != _node_key(project, npm, ignore_scripts):
                raise RuntimeError("dependency inputs changed during installation; retry")
            if not _healthy_node_tree(project, npm):
                raise RuntimeError("installed dependency tree is incomplete; check npm omit settings and retry")
        if key != _node_key(project, npm, ignore_scripts):
            receipt.unlink(missing_ok=True)
            raise RuntimeError("dependency inputs changed during validation; retry")
        _save(receipt, root, scope, key)
        payload = _read(receipt)
        payload["installed_lock"] = _digest(target / ".package-lock.json")
        write_bytes_atomic(receipt, (json.dumps(payload, sort_keys=True) + "\n").encode())
        return not reusable


def prepare_python(root: Path, scope: str) -> None:
    if scope not in ("python-core", "python-full"):
        raise ValueError("a Python scope is required")
    root = root.resolve()
    with exclusive_file_lock(root / ".local/development-dependencies", timeout_seconds=300):
        _, _, receipt = _target(root, scope)
        # A caller override must not redirect sync into an unrelated environment.
        env = {k: v for k, v in os.environ.items() if k != "UV_PROJECT_ENVIRONMENT"}
        receipt.unlink(missing_ok=True)
        subprocess.run(
            [_tool("uv"), "sync", "--extra", "test-core" if scope == "python-core" else "test"],
            cwd=root, env=env, check=True,
        )
        _save(receipt, root, scope, {
            name: _digest(root / name) for name in ("pyproject.toml", "uv.lock")
        })


def _in_use(root: Path) -> bool:
    """Unknown process visibility is a hold, including on unsupported hosts."""
    if os.name != "posix" or shutil.which("lsof") is None:
        return True
    opened = subprocess.run(["lsof", "-nP", "-Fpn"], capture_output=True, text=True)
    if opened.returncode != 0:
        return True
    current_pid = None
    for line in opened.stdout.splitlines():
        if line.startswith("p"):
            current_pid = line[1:]
        if current_pid != str(os.getpid()) and line.startswith("n/"):
            path = Path(line[1:])
            if path == root or root in path.parents:
                return True
    processes = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True
    )
    if processes.returncode:
        return True
    for line in processes.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0] != str(os.getpid()) and str(root) in parts[1]:
            return True
    return False


def retire(root: Path, scope: str, *, days: int, apply: bool) -> dict:
    root = root.resolve()
    if days < 2:
        raise ValueError("retention must be at least two days")
    with exclusive_file_lock(root / ".local/development-dependencies", timeout_seconds=300):
        project, target, receipt = _target(root, scope)
        old = _read(receipt)
        result = {"scope": scope, "path": str(target), "action": "retain"}
        if old.get("checkout") != str(root) or old.get("scope") != scope:
            return {**result, "reason": "not_owned_by_this_setup_scope"}
        last_used = old.get("last_used")
        if not isinstance(last_used, (int, float)) or not math.isfinite(last_used) or last_used > time.time() - days * 86400:
            return {**result, "reason": "recently_prepared"}
        definitions = ("package.json", "package-lock.json") if scope in NODE_PROJECTS else ("pyproject.toml", "uv.lock")
        if not all((project / name).is_file() for name in definitions):
            return {**result, "reason": "missing_restore_definitions"}
        tracked = subprocess.run(
            ["git", "ls-files", "--", str(target.relative_to(root))],
            cwd=root, capture_output=True, text=True,
        )
        if tracked.returncode or tracked.stdout.strip():
            return {**result, "reason": "tracked_files_or_git_unavailable"}
        if _in_use(root):
            return {**result, "reason": "checkout_in_use_or_visibility_unknown"}
        if apply:
            shutil.rmtree(target)
        return {**result, "action": "removed" if apply else "would_remove"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "retire"))
    parser.add_argument("--scope", choices=SCOPES, action="append", required=True)
    parser.add_argument("--force", action="store_true", help="reinstall Node dependencies")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--apply", action="store_true", help="delete eligible owned environments")
    args = parser.parse_args()
    if {"python-core", "python-full"} <= set(args.scope):
        parser.error("select one Python profile per checkout")
    if args.action == "setup" and args.apply:
        parser.error("--apply belongs to retire")
    root = ROOT.resolve()
    for scope in dict.fromkeys(args.scope):
        if args.action == "retire":
            print(json.dumps(retire(root, scope, days=args.days, apply=args.apply)))
        elif scope in NODE_PROJECTS:
            installed = ensure_node_dependencies(root, scope, ignore_scripts=False, force=args.force)
            print(f"{scope}: {'installed' if installed else 'reused'}")
        else:
            prepare_python(root, scope)
            print(f"{scope}: synchronized")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Dependency setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
