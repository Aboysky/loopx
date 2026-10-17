"""Synthetic coverage for the provider-neutral confirmation gate."""

from __future__ import annotations

from datetime import datetime, timezone
import copy
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "loopx-finance-execution" / "src"))

from loopx_finance_execution.confirmation_gate import (  # noqa: E402
    CLAIM_MISSING,
    CONFIRMATION_CARD_MISMATCH,
    CONFIRMATION_MISSING,
    CONFIRMATION_PRINCIPAL_MISMATCH,
    CONFIRMATION_PROVIDER_MISMATCH,
    EXPIRED,
    OPERATION_NOT_LIVE,
    PAYLOAD_TERMS_MISSING,
    TERMS_MISMATCH,
    verify_bound_confirmation,
)


NOW = datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)
CARD = "om_synthetic_card_1"
PRINCIPAL = "lark:ou_synthetic_operator"
TERMS = {
    "enabled": True,
    "type": "market",
    "side": "long",
    "amount_usdc": "20",
    "limit_price": None,
    "reduce_only": False,
    "take_profit_stop_loss": None,
}


def _proposal() -> dict:
    return {
        "proposal_id": "proposal-synthetic-1",
        "status": "applying",
        "normalized_parameters": json.dumps(
            {
                "payload": {
                    "schema_version": "finance_bound_order_v1",
                    "bound_order": copy.deepcopy(TERMS),
                    "expires_at": "2026-10-17T05:00:00Z",
                }
            }
        ),
        "operation": {
            "operation_id": "proposal-synthetic-1",
            "lifecycle_state": "claimed",
            "confirmation_digest": "a" * 64,
            "confirmation": {
                "provider": "lark",
                "event_id": "synthetic-event-1",
                "principal": PRINCIPAL,
                "message_id": CARD,
            },
            "claim": {"claim_id": "claim-synthetic-1"},
            "delivery": {"message_id": CARD},
        },
    }


def _plan() -> dict:
    return {
        "terms_key": "bound_order",
        "terms": copy.deepcopy(TERMS),
        "authorized_principal": PRINCIPAL,
    }


def test_confirmed_operation_is_admitted() -> None:
    result = verify_bound_confirmation(_proposal(), _plan(), now=NOW)
    assert result["allowed"] is True
    assert result["refusals"] == []
    assert result["evidence"]["claim_id"] == "claim-synthetic-1"
    assert result["evidence"]["confirmation_card_message_id"] == CARD


def test_missing_confirmation_refuses() -> None:
    proposal = _proposal()
    proposal["operation"].pop("confirmation")
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert result["allowed"] is False
    assert CONFIRMATION_MISSING in result["refusals"]


def test_confirmation_from_another_channel_refuses() -> None:
    proposal = _proposal()
    proposal["operation"]["confirmation"]["provider"] = "web"
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert CONFIRMATION_PROVIDER_MISMATCH in result["refusals"]


def test_confirmation_from_another_principal_refuses() -> None:
    proposal = _proposal()
    proposal["operation"]["confirmation"]["principal"] = "lark:ou_someone_else"
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert CONFIRMATION_PRINCIPAL_MISMATCH in result["refusals"]


def test_confirmation_from_another_card_refuses() -> None:
    proposal = _proposal()
    proposal["operation"]["confirmation"]["message_id"] = "om_other_card"
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert CONFIRMATION_CARD_MISMATCH in result["refusals"]


def test_cancelled_operation_is_not_live() -> None:
    proposal = _proposal()
    proposal["status"] = "cancelled"
    proposal["operation"]["lifecycle_state"] = "prepared"
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert OPERATION_NOT_LIVE in result["refusals"]


def test_missing_claim_refuses() -> None:
    proposal = _proposal()
    proposal["operation"].pop("claim")
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert CLAIM_MISSING in result["refusals"]


def test_missing_payload_terms_refuses() -> None:
    proposal = _proposal()
    parameters = json.loads(proposal["normalized_parameters"])
    parameters["payload"].pop("bound_order")
    proposal["normalized_parameters"] = json.dumps(parameters)
    result = verify_bound_confirmation(proposal, _plan(), now=NOW)
    assert PAYLOAD_TERMS_MISSING in result["refusals"]


def test_terms_drift_refuses() -> None:
    plan = _plan()
    plan["terms"]["amount_usdc"] = "500"
    result = verify_bound_confirmation(_proposal(), plan, now=NOW)
    assert TERMS_MISMATCH in result["refusals"]
    assert result["evidence"]["terms_digest"] != result["evidence"]["expected_terms_digest"]


def test_expired_operation_refuses() -> None:
    result = verify_bound_confirmation(
        _proposal(), _plan(), now=datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)
    )
    assert EXPIRED in result["refusals"]
    assert result["allowed"] is False
