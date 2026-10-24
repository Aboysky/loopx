"""Native input observation is narrower than history, release or a future ACK."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loopx.control_plane.turn_driver.codex_input_trace import codex_context_in_active_input


def fixture(root):
    bundle = root / "trace"
    (bundle / "payloads").mkdir(parents=True)
    baseline = {"schema_version": "context_delivery_v1", "mode": "full",
        "target": {"session_id": "session"}, "context": {"enabled": True, "text": "完整🙂 " * 200, "stop": "Stop before publication."}}
    raw = json.dumps(baseline, ensure_ascii=False).encode()
    path = root / "capture.json"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    # Split at ASCII JSON separators, independently from the production reader.
    first = raw.index(b'"context"')
    second = raw.index(b'"stop"')
    pages = []
    for start, end in ((0, first), (first, second), (second, len(raw))):
        page = {"ok": True, "schema_version": "context_capture_page_v1", "sha256": digest,
            "offset": start, "next_offset": end if end < len(raw) else None, "total_bytes": len(raw),
            "eof": end == len(raw), "content": raw[start:end].decode()}
        pages.append({"type": "function_call_output", "output": "Chunk ID: fixture\nOutput:\n" + json.dumps(page)})
    request = {"input": pages}
    (bundle / "manifest.json").write_text(json.dumps({"schema_version": 1, "root_thread_id": "session", "rollout_id": "session"}))
    (bundle / "payloads/input.json").write_text(json.dumps(request))
    (bundle / "payloads/output.json").write_text(json.dumps({"output_items": [
        {"type": "function_call", "name": "exec_command", "call_id": "guard"}]}))
    payloads = [
        {"type": "inference_started", "inference_call_id": "inference", "request_payload": {"path": "payloads/input.json"}},
        {"type": "inference_completed", "inference_call_id": "inference", "response_payload": {"path": "payloads/output.json"}},
        {"type": "tool_call_started", "tool_call_id": "guard", "model_visible_call_id": "guard",
         "requester": {"type": "model"}, "kind": {"type": "exec_command"}},
    ]
    rows = [{"schema_version": 1, "seq": i, "thread_id": "session", "rollout_id": "session",
             "codex_turn_id": "turn", "payload": payload} for i, payload in enumerate(payloads)]
    (bundle / "trace.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    observation = {"trace_bundle": str(bundle), "tool_call_id": "guard", "capture_file": str(path), "capture_sha256": digest}
    return observation, baseline, request, rows


def test_only_complete_tool_output_in_current_input_is_observed_without_writes(tmp_path):
    observation, baseline, request, _ = fixture(tmp_path)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert codex_context_in_active_input(observation, baseline=baseline, session_id="session")
    assert all(path.read_bytes() == raw for path, raw in original.items())
    # Identical repeated pages are ordinary history; every byte is still needed.
    request["input"].append(request["input"][0])
    path = tmp_path / "trace/payloads/input.json"
    path.write_text(json.dumps(request))
    assert codex_context_in_active_input(observation, baseline=baseline, session_id="session")
    path.write_text(json.dumps({"input": [{"type": "function_call_output", "output": json.dumps(baseline)}]}))
    assert codex_context_in_active_input(observation, baseline=baseline, session_id="session")


def test_long_trace_uses_current_window_and_never_old_delivery(tmp_path):
    from loopx.control_plane.effect_runtime import MAX_REQUEST_BYTES

    observation, baseline, _, rows = fixture(tmp_path)
    trace = tmp_path / "trace/trace.jsonl"
    # Old history need not fit in memory or be reread to observe a live call.
    old = {**rows[0], "seq": -1, "payload": {"type": "protocol_event_observed", "text": "x" * (MAX_REQUEST_BYTES + 100)}}
    trace.write_text(json.dumps(old) + "\n" + trace.read_text())
    assert codex_context_in_active_input(observation, baseline=baseline, session_id="session")
    # If the current inference itself fell outside the bounded window, decline.
    with trace.open("a") as stream:
        stream.write(json.dumps({**old, "seq": 3}) + "\n")
    assert not codex_context_in_active_input(observation, baseline=baseline, session_id="session")


def test_full_projection_read_is_retention_evidence_with_json_number_semantics(tmp_path):
    observation, baseline, _, _ = fixture(tmp_path)
    baseline["context"]["compute"] = 1
    context = {**baseline["context"], "compute": 1.0}
    raw = json.dumps(context).encode()
    Path(observation["capture_file"]).write_bytes(raw)
    observation["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    path = tmp_path / "trace/payloads/input.json"
    path.write_text(json.dumps({"input": [{"type": "function_call_output", "output": raw.decode()}]}))
    assert codex_context_in_active_input(observation, baseline=baseline, session_id="session")
    context["compute"] = True
    path.write_text(json.dumps({"input": [{"type": "function_call_output", "output": json.dumps(context)}]}))
    assert not codex_context_in_active_input(observation, baseline=baseline, session_id="session")


@pytest.mark.parametrize("failure", ["middle_missing", "pruned", "preview", "quoted", "wrong_role", "server_history",
    "bad_page", "overlap", "capture_changed", "other_session", "other_tool", "ended", "new_inference", "compacted",
    "child", "code_mode", "wrong_response", "partial_trace", "reordered_trace", "missing_trace", "outside_payload", "symlink", "boolean_type"])
def test_unknown_stale_lossy_or_unbound_observation_never_reuses(tmp_path, failure):
    observation, baseline, request, rows = fixture(tmp_path)
    bundle = Path(observation["trace_bundle"])
    if failure == "middle_missing":
        request["input"].pop(1)
    elif failure == "pruned":
        request["input"] = []
    elif failure == "preview":
        request["input"][1]["output"] = "Warning: truncated output\n" + request["input"][1]["output"][:100]
    elif failure == "quoted":
        request["input"] = [{"type": "function_call_output", "output": "Example: " + json.dumps(baseline)}]
    elif failure == "wrong_role":
        request["input"] = [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(baseline)}]}]
    elif failure == "boolean_type":
        other = json.loads(json.dumps(baseline))
        other["context"]["enabled"] = 1
        request["input"] = [{"type": "function_call_output", "output": json.dumps(other)}]
    elif failure == "server_history":
        request["previous_response_id"] = "opaque-history"
    elif failure == "bad_page":
        request["input"][1]["output"] = request["input"][1]["output"].replace('"eof": false', '"eof": true')
    elif failure == "overlap":
        page = json.loads(request["input"][1]["output"].split("\nOutput:\n")[1])
        page["offset"] -= 1
        request["input"][1]["output"] = json.dumps(page)
    elif failure == "capture_changed":
        Path(observation["capture_file"]).write_text("{}")
    elif failure == "other_session":
        baseline["target"]["session_id"] = "other"
    elif failure == "other_tool":
        observation["tool_call_id"] = "other"
    elif failure == "ended":
        rows.append({**rows[-1], "seq": 3, "payload": {"type": "tool_call_ended", "tool_call_id": "guard"}})
    elif failure in {"new_inference", "compacted"}:
        rows.append({**rows[0], "seq": 3, "payload": {**rows[0]["payload"], "inference_call_id": "later"}})
    elif failure == "child":
        rows[-1]["thread_id"] = "child"
    elif failure == "code_mode":
        rows[-1]["payload"]["code_mode_runtime_tool_id"] = "nested"
    elif failure == "wrong_response":
        (bundle / "payloads/output.json").write_text(json.dumps({"output_items": []}))
    elif failure == "reordered_trace":
        rows[0], rows[1] = rows[1], rows[0]
    elif failure == "outside_payload":
        rows[0]["payload"]["request_payload"]["path"] = "../input.json"
    (bundle / "payloads/input.json").write_text(json.dumps(request))
    trace = bundle / "trace.jsonl"
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
    if failure == "partial_trace":
        trace.write_text(trace.read_text() + '{"partial":')
    elif failure == "missing_trace":
        trace.unlink()
    elif failure == "symlink":
        original = tmp_path / "original.jsonl"
        trace.rename(original)
        trace.symlink_to(original)
    assert not codex_context_in_active_input(observation, baseline=baseline, session_id="session")
