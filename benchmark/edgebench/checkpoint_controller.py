"""Controller-only transport for the native SForge checkpoint API.

Native admission/ranking retain their native owner. The existing typed artifact
owner seals and verifies the bank bytes. Nothing here belongs in a solver payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from loopx.control_plane.effect_runtime import effect_runtime_result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward controller credentials to another origin.


def _physical(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("Controller paths must be normalized, physical and absolute")
    return path


def _controller(path: Path) -> dict:
    path = _physical(path)
    if path.stat().st_mode & 0o077:
        raise ValueError("Controller configuration must be owner-only")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or set(value) != {"url", "admin_secret", "bank_root"}:
        raise ValueError("Controller configuration requires url, admin_secret and bank_root")
    if not isinstance(value["admin_secret"], str) or not value["admin_secret"]:
        raise ValueError("Fresh controller authority is unavailable")
    url = urlsplit(value["url"])
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or
            url.password or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Controller URL must identify one explicit HTTP origin")
    value["bank_root"] = _physical(Path(value["bank_root"]))
    return value


def _post(controller: dict, route: str, body: dict, timeout: float) -> dict:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Controller timeout must be finite and positive")
    request = Request(controller["url"].rstrip("/") + route,
        data=json.dumps({**body, "admin_secret": controller["admin_secret"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        # A remote body can echo submitted credentials. Keep only the status.
        raise ValueError(f"Native checkpoint operation rejected: HTTP {error.code}") from None
    if not isinstance(result, dict):
        raise ValueError("Native checkpoint operation returned an invalid object")
    return result


def _reference(value: dict) -> dict:
    if (set(value) != {"checkpoint_id", "manifest_sha256", "task_id", "source_run_id", "opportunity", "incumbent"} or
            not re.fullmatch(r"[0-9a-f]{32}", value.get("checkpoint_id", "")) or
            not re.fullmatch(r"[0-9a-f]{64}", value.get("manifest_sha256", ""))):
        raise ValueError("Native checkpoint reference is malformed")
    return value


def _bound_bank(folder: Path, reference: dict) -> None:
    """Byte/source binding only; native restore owns eligibility and validity."""
    raw = _physical(folder / "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    witnessed = _physical(folder / "manifest.sha256").read_text()
    packet = json.loads(raw)
    if (digest != reference["manifest_sha256"] or witnessed != digest or
            packet.get("schema_version") != "sforge_judge_checkpoint_v1" or
            any(packet.get(key) != reference[key] for key in (
                "task_id", "source_run_id", "opportunity", "incumbent"))):
        raise ValueError("Native bank bytes differ from the captured reference")
    expected = {"manifest.json", "manifest.sha256"}
    incumbent = reference["incumbent"]
    if incumbent is not None:
        expected.add("incumbent.tar.gz")
        archive = _physical(folder / "incumbent.tar.gz").read_bytes()
        if (len(archive) != incumbent["archive_bytes"] or
                hashlib.sha256(archive).hexdigest() != incumbent["archive_sha256"]):
            raise ValueError("Native selected archive differs from the captured reference")
    if {p.name for p in folder.iterdir()} != expected:
        raise ValueError("Native bank contains undeclared members")


def capture(controller_file: Path, *, token: str, capture_id: str, destination: Path,
            timeout: float = 30) -> dict:
    """Capture one native-owned point without exporting controller configuration."""
    if not re.fullmatch(r"[0-9a-f]{32}", capture_id):
        raise ValueError("Capture identity must be the declared 32-hex native identity")
    destination = Path(destination)
    _physical(destination.parent)
    if not destination.is_absolute() or destination != destination.resolve() or destination.exists():
        raise ValueError("Capture export requires a fresh physical destination")
    controller = _controller(controller_file)
    reference = _reference(_post(controller, "/api/v1/checkpoint/capture",
        {"token": token, "capture_id": capture_id}, timeout))
    if reference["checkpoint_id"] != capture_id:
        raise ValueError("Native capture returned a different identity")
    folder = _physical(controller["bank_root"] / capture_id)
    _bound_bank(folder, reference)
    components = [{"id": "native_judge", "source_path": str(folder)}]
    probe = effect_runtime_result("runtime.checkpoint_artifacts", {"action": "probe", "components": components})
    result = effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "capture", "components": components, "destination": str(destination),
        "expected_source_sha256": probe["source_sha256"],
        "point_metadata": {"native_reference": reference},
    }, retry_safe=False)
    # Bind the actually copied bytes, not merely a prior source observation.
    _bound_bank(destination / "components/native_judge", reference)
    return {**result, "native_reference": reference}


def restore(controller_file: Path, *, root: Path, expected_sha256: str, run_id: str,
            timeout: float = 30) -> dict:
    """Import verified inert bytes, then ask fresh native authority to admit them.

    Does not restore a model, LoopX Goal, effect authority or whole-trial budget.
    An uncertain response is not replayed under a different run or capture id.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
        raise ValueError("Continuation requires one explicit native run component")
    controller = _controller(controller_file)
    root = _physical(root)
    effect_runtime_result("runtime.checkpoint_artifacts", {
        "action": "verify", "root": str(root), "expected_sha256": expected_sha256})
    manifest = json.loads((root / "checkpoint.json").read_bytes())
    if [c["id"] for c in manifest["components"]] != ["native_judge"]:
        raise ValueError("Native import requires its single declared capsule component")
    reference = _reference(manifest["point_metadata"]["native_reference"])
    if run_id == reference["source_run_id"]:
        raise ValueError("Continuation requires a fresh run identity")
    folder = root / "components/native_judge"
    _bound_bank(folder, reference)
    bank = controller["bank_root"]
    target = bank / reference["checkpoint_id"]
    stage = Path(tempfile.mkdtemp(prefix=".loopx-native-import-", dir=bank))
    try:
        effect_runtime_result("runtime.checkpoint_artifacts", {
            "action": "materialize", "root": str(root), "expected_sha256": expected_sha256,
            "destination": str(stage / "unit"),
        }, retry_safe=False)
        imported = stage / "unit/components/native_judge"
        _bound_bank(imported, reference)
        if target.exists():
            _bound_bank(_physical(target), reference)  # No overwrite, even on retry.
        else:
            # POSIX rename can replace an empty destination. Reserve its name
            # exclusively; interruption leaves an unusable point, never grants.
            target.mkdir(mode=0o700)
            try:
                imported.rename(target)
            except BaseException:
                target.rmdir()
                raise
            descriptor = os.open(bank, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return _post(controller, "/api/v1/checkpoint/restore", {
            "checkpoint_id": reference["checkpoint_id"], "manifest_sha256": reference["manifest_sha256"],
            "run_id": run_id,
        }, timeout)
    finally:
        shutil.rmtree(stage)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-file", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--token-file", required=True, type=Path)
    capture_parser.add_argument("--capture-id", required=True)
    capture_parser.add_argument("--destination", required=True, type=Path)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--root", required=True, type=Path)
    restore_parser.add_argument("--expected-sha256", required=True)
    restore_parser.add_argument("--run-id", required=True)
    restore_parser.add_argument("--result-file", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "capture":
        source_token = _physical(args.token_file).read_text().strip()
        result = capture(args.controller_file, token=source_token,
                         capture_id=args.capture_id, destination=args.destination)
        print(json.dumps(result))
    else:
        # Reserve before admission. A lost output is explicit recovery, never a
        # fresh registration that silently refills the captured opportunity.
        _physical(args.result_file.parent)
        if args.result_file != args.result_file.resolve():
            raise ValueError("Continuation result must be a normalized physical path")
        with args.result_file.open("x") as result_file:
            args.result_file.chmod(0o600)
            result = restore(args.controller_file, root=args.root,
                expected_sha256=args.expected_sha256, run_id=args.run_id)
            json.dump(result, result_file)
            result_file.flush()
            os.fsync(result_file.fileno())
        print(json.dumps({"result_file": str(args.result_file), "run_id": args.run_id}))


if __name__ == "__main__":
    main()
