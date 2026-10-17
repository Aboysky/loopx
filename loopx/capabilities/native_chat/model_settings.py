"""Provider-neutral model values persisted by native Chat Sessions.

These are bounded visible provider values, not LoopX entity or file names.
"""
from __future__ import annotations

from typing import Any


_AGENT_MODEL_ID_MAX_LENGTH = 160


def normalize_agent_model_id(value: Any) -> str:
    """Keep a provider model value without applying file-name rules.

    ACP option values are protocol strings rather than LoopX entity IDs. They
    are persisted in JSON only, so retain a bounded printable value while
    rejecting controls that would make logs or projections unsafe.
    """
    token = str(value or "")
    if not token.strip() or len(token) > _AGENT_MODEL_ID_MAX_LENGTH or any(ord(character) < 32 for character in token):
        raise ValueError("agent_model_id must be a bounded model value")
    return token
