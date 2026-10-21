"""Private teaching artifacts; the existing TS content owner decides all rules.

Reuse the media workspace's Goal route, path checks and atomic private I/O.
There is no extension activation, model invocation or learning-score store.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from ...control_plane.effect_runtime import effect_runtime_result
from ...file_lock import exclusive_file_lock
from .media import MediaWorkspace, _read, _safe_path, _save


def _owner(operation: str, request: dict) -> dict:
    return effect_runtime_result(f"content_experience.{operation}", request)


class ExperienceWorkspace:
    def __init__(self, media_workspace: MediaWorkspace):
        self.root = _safe_path(media_workspace.root, "experiences")

    def _bundle(self, ident: str) -> Path:
        if not isinstance(ident, str) or not re.fullmatch(r"experience_[a-f0-9]{24}", ident):
            raise ValueError("Invalid experience reference")
        return _safe_path(self.root, ident)

    def inspect(self, ident: str) -> dict:
        record = _read(_safe_path(self._bundle(ident), "record.json"))
        checked = _owner("plan", {"plan": record["plan"]})
        revision = record["revision"]
        if (record.get("experience_id") != ident or record.get("plan_digest") != checked["plan_digest"]
                or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1):
            raise ValueError("Experience source verification failed; restore the original artifact")
        return {**checked, "experience_id": ident, "revision": revision}

    def prepare(self, plan: dict, *, experience_id: str | None = None, expected_revision: int | None = None) -> dict:
        checked = _owner("plan", {"plan": plan})
        # The same source has the same reference after a lost prepare response.
        ident = experience_id or f"experience_{checked['plan_digest'].removeprefix('sha256:')[:24]}"
        bundle = self._bundle(ident)
        if expected_revision is not None and (isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1):
            raise ValueError("Read the current experience revision")
        bundle.mkdir(mode=0o700, parents=True, exist_ok=True)
        with exclusive_file_lock(bundle / "record.json", operation="content-experience-prepare"):
            saved = _read(_safe_path(bundle, "record.json")) if (bundle / "record.json").exists() else None
            if saved and (saved.get("experience_id") != ident or isinstance(saved.get("revision"), bool)
                          or not isinstance(saved.get("revision"), int) or saved["revision"] < 1):
                raise ValueError("Restore the artifact metadata before preparing a replacement")
            if expected_revision is not None and (saved is None or saved["revision"] != expected_revision):
                raise ValueError("The experience revision changed; inspect before editing")
            previous = None
            if saved:
                try:
                    previous = self.inspect(ident)
                except (ValueError, RuntimeError, KeyError, TypeError):
                    if expected_revision is None:
                        raise ValueError("Repair requires the known current revision and a validated source") from None
            if previous and previous["plan_digest"] == checked["plan_digest"]:
                return previous
            if previous and expected_revision is None:
                raise ValueError("Read the current experience revision before replacing its source")
            revision = saved["revision"] + 1 if saved else 1
            _save(_safe_path(bundle, "record.json"), {"experience_id": ident, "revision": revision,
                  "plan_digest": checked["plan_digest"], "plan": checked["plan"]})
        return self.inspect(ident)

    def list(self) -> dict:
        results = []
        if self.root.exists():
            for path in sorted(self.root.glob("experience_*")):
                try:
                    result = self.inspect(path.name)
                    results.append({"experience_id": path.name, "revision": result["revision"],
                                    "title": result["plan"]["title"], "status": "ready"})
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    # An unreadable artifact must not erase other prepared work.
                    if re.fullmatch(r"experience_[a-f0-9]{24}", path.name):
                        results.append({"experience_id": path.name, "status": "damaged", "title": "Unreadable experience"})
        return {"ok": True, "experiences": results, "visibility": "local_private", "publish_authorized": False}

    def run(self, ident: str, *, expected_revision: int, request: dict) -> dict:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("Read the current experience revision")
        if not isinstance(request, dict) or set(request) - {"parameters", "scenario_id", "policy_id", "actions"}:
            raise ValueError("Unsupported experience run input")
        current = self.inspect(ident)
        if current["revision"] != expected_revision:
            raise ValueError("The experience revision changed; reload before running")
        return {**_owner("run", {"plan": current["plan"], **request}),
                "experience_id": ident, "revision": current["revision"]}


def read_experience_json(path: str, *, limit: int = 128 * 1024) -> dict:
    source = Path(path).expanduser()
    if source.stat().st_size > limit:
        raise ValueError("Experience input exceeds its byte limit")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Experience input must contain an object")
    return value
