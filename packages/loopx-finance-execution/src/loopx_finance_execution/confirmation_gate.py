"""Provider-neutral admission gate for one human-confirmed financial operation.

The Core typed-action store owns the confirmation receipt, the single execution
claim and the canonical operation envelope. A venue executor must additionally
prove that the effect it is about to perform is the effect the operator
approved.

This module performs that check against records that are already loaded from
the canonical store. It never mutates state, never reads credentials and never
talks to a venue, so it can run before any effect-bearing call. A refusal is a
typed result, not an exception: callers must report it honestly instead of
retrying or working around it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


GATE_SCHEMA_VERSION = "finance_confirmation_gate_v0"

#: Record statuses that still represent a live, human-confirmed operation.
#: ``applying`` is the ordinary state while the claimed effect is in flight.
LIVE_RECORD_STATUSES = frozenset({"applied", "applying"})

#: Canonical lifecycle states an executor may act on.
LIVE_LIFECYCLE_STATES = frozenset({"claimed", "consumed", "outcome_observed"})

#: Refusal codes are stable public tokens; they never carry private material.
CONFIRMATION_MISSING = "confirmation_missing"
CONFIRMATION_PROVIDER_MISMATCH = "confirmation_provider_mismatch"
CONFIRMATION_PRINCIPAL_MISMATCH = "confirmation_principal_mismatch"
CONFIRMATION_CARD_MISMATCH = "confirmation_card_mismatch"
OPERATION_NOT_LIVE = "operation_not_live"
CLAIM_MISSING = "claim_missing"
PAYLOAD_TERMS_MISSING = "payload_terms_missing"
TERMS_MISMATCH = "terms_mismatch"
EXPIRED = "expired"


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a JSON object") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: object) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def verify_bound_confirmation(
    proposal: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    expected_provider: str = "lark",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Check one canonical operation against a frozen execution plan.

    ``proposal`` is the record as stored by the canonical action store
    (``normalized_parameters`` plus ``operation``). ``plan`` is the frozen plan
    the executor would run: ``terms_key`` (default ``bound_order``), ``terms``,
    optional ``authorized_principal`` and ``expires_at``, and
    ``require_claim`` (default ``True``).
    """

    parameters = _mapping(proposal.get("normalized_parameters"), field="normalized_parameters")
    operation = _mapping(proposal.get("operation"), field="operation")
    payload = parameters.get("payload")
    payload = dict(payload) if isinstance(payload, Mapping) else {}

    confirmation = operation.get("confirmation")
    confirmation = dict(confirmation) if isinstance(confirmation, Mapping) else None
    claim = operation.get("claim")
    claim = dict(claim) if isinstance(claim, Mapping) else None
    delivery = operation.get("delivery")
    delivery = dict(delivery) if isinstance(delivery, Mapping) else {}

    terms_key = str(plan.get("terms_key") or "bound_order")
    expected_terms = plan.get("terms")
    authorized_principal = plan.get("authorized_principal")
    require_claim = plan.get("require_claim", True) is not False
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    refusals: list[str] = []
    card_message_ids = {
        value
        for value in (delivery.get("message_id"), operation.get("card_message_id"))
        if isinstance(value, str) and value
    }

    if confirmation is None:
        refusals.append(CONFIRMATION_MISSING)
    else:
        if str(confirmation.get("provider") or "") != expected_provider:
            refusals.append(CONFIRMATION_PROVIDER_MISMATCH)
        if authorized_principal and confirmation.get("principal") != authorized_principal:
            refusals.append(CONFIRMATION_PRINCIPAL_MISMATCH)
        confirmed_card = confirmation.get("message_id")
        # A confirmation is only valid for the card that carried this exact
        # operation; a receipt from any other message proves nothing here.
        if not isinstance(confirmed_card, str) or not confirmed_card or (
            card_message_ids and confirmed_card not in card_message_ids
        ):
            refusals.append(CONFIRMATION_CARD_MISMATCH)

    record_status = str(proposal.get("status") or "")
    lifecycle_state = str(operation.get("lifecycle_state") or "")
    if record_status not in LIVE_RECORD_STATUSES or lifecycle_state not in LIVE_LIFECYCLE_STATES:
        refusals.append(OPERATION_NOT_LIVE)

    if require_claim and claim is None:
        refusals.append(CLAIM_MISSING)

    payload_terms = payload.get(terms_key)
    if not isinstance(payload_terms, Mapping) or expected_terms is None:
        refusals.append(PAYLOAD_TERMS_MISSING)
    elif _canonical(payload_terms) != _canonical(expected_terms):
        refusals.append(TERMS_MISMATCH)

    expiry = _timestamp(plan.get("expires_at")) or _timestamp(payload.get("expires_at"))
    if expiry is not None and clock > expiry:
        refusals.append(EXPIRED)

    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "allowed": not refusals,
        "refusals": refusals,
        "evidence": {
            "operation_id": operation.get("operation_id") or proposal.get("proposal_id"),
            "record_status": record_status,
            "lifecycle_state": lifecycle_state,
            "confirmation_digest": operation.get("confirmation_digest"),
            "confirmation_provider": (confirmation or {}).get("provider"),
            "confirmation_principal": (confirmation or {}).get("principal"),
            "confirmation_card_message_id": (confirmation or {}).get("message_id"),
            "operation_card_message_id": delivery.get("message_id"),
            "claim_id": (claim or {}).get("claim_id"),
            "terms_key": terms_key,
            "terms_digest": _digest(payload_terms) if isinstance(payload_terms, Mapping) else None,
            "expected_terms_digest": _digest(expected_terms),
            "expires_at": expiry.isoformat() if expiry else None,
            "observed_at": clock.isoformat(),
        },
    }
