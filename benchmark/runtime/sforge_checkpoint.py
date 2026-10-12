"""SForge checkpoint read transport, included in the existing worker payload."""
from __future__ import annotations

import json
import math
import time
from urllib.request import Request, urlopen

SCHEMA = "sforge_checkpoint_opportunity_v0"  # Local provider artifact, not a LoopX authority contract.
ROUTE = "/api/v1/checkpoint/opportunity"


def capture_opportunity(env, *, timeout):
    """Read only this worker's registration; retain its original deadline."""
    deadline = float(env["LOOPX_PHASE_DEADLINE_EPOCH"])
    if not math.isfinite(deadline) or deadline <= time.time() or timeout <= 0:
        raise ValueError("checkpoint requires an open original trial deadline")
    request = Request(env["SFORGE_JUDGE_URL"].rstrip("/") + ROUTE,
        data=json.dumps({"token": env["SFORGE_TOKEN"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        packet = json.load(response)
    if (packet.get("schema_version") != SCHEMA or packet.get("execution_authority_granted") is not False or
            packet.get("outstanding_evaluations") != 0):
        raise ValueError("native opportunity checkpoint readback is unavailable")
    observed = time.time()
    return {**packet, "source_trial_deadline_epoch": deadline,
            "client_observed_at_epoch": observed,
            "remaining_trial_seconds": max(0, deadline - observed),
            "continuation_qualified": False}
