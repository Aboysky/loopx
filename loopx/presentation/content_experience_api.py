"""Existing Goal-local content workspace transport, without author code execution."""
from urllib.parse import urlparse

from ..capabilities.content_ops.experience import ExperienceWorkspace

CONTENT_EXPERIENCE_PATH = "/api/chat/content-experience"


class ContentExperienceRequestMixin:
    def _content_experience_request(self) -> None:
        try:
            if urlparse(self.path).query:
                raise ValueError("Use the request body")
            body = self._read_json(max_bytes=16 * 1024)
            if set(body) - {"goal_id", "action", "experience_id", "expected_revision", "run"}:
                raise ValueError("Unsupported fields")
            workspace = ExperienceWorkspace(self._media_workspace(body["goal_id"]))
            if body["action"] == "list" and set(body) == {"goal_id", "action"}:
                result = workspace.list()
            elif body["action"] == "inspect" and set(body) == {"goal_id", "action", "experience_id"}:
                result = workspace.inspect(body["experience_id"])
            elif body["action"] == "run" and set(body) == {"goal_id", "action", "experience_id", "expected_revision", "run"}:
                result = workspace.run(body["experience_id"], expected_revision=body["expected_revision"], request=body["run"])
            else:
                raise ValueError("Unsupported operation")
            self._send_json(result)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            self._send_error("Learning model unavailable or changed. Reload the source before continuing.", status=400)
