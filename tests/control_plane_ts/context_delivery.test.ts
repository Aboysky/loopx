import assert from "node:assert/strict";
import test from "node:test";
import type {JsonObject} from "../../loopx/control_plane/effect_program.ts";
import {compactSelectedTodoSource, prepareContextDelivery, restoreContextDelivery} from "../../loopx/control_plane/quota/context_delivery.ts";

const scope = {goal_id: "goal", agent_id: "agent", session_id: "session", context_epoch: "epoch-1"};
const long = "Keep the original acceptance and stop before publication. ".repeat(400);
function context(): JsonObject {
  return {complete: true, instruction: "Read requirements before work.", sources: [
    {source: "goal_state", command: "read-goal", content: {state_file: "goal.md", revision: "revision-a",
      excluded_todo_regions: [{role: "agent", start_line: 4, end_line: 6, revision: "tasks-a"}], text: long}},
    {source: "selected_todo", command: "read-task", content: {ok: true, matched: true,
      authority_read: {provider_revision: "a"}, todo: {todo_id: "todo_work", text: long,
        note: "Keep the validation evidence.", status: "open", claimed_by: "agent"}}},
    {source: "goal_acceptance", content: {provider_revision: "a", goal_acceptance_contract: {
      outcome_requirements: {revision: 1, outcomes: [{id: "outcome-a", objective: long,
        requirements: [{id: "r1", description: long, status: "unproven", agent_review: {note: "No evidence yet."}}]}]}}}},
    {kind: "unknown_source", content: {large_mixed_control: long}},
  ]};
}
const source = (value: JsonObject, index: number): JsonObject => (value.sources as JsonObject[])[index].content as JsonObject;
const full = (value: JsonObject, capture_id = "capture-1", extraScope = scope): JsonObject =>
  prepareContextDelivery({context: value, scope: extraScope, capture_id});
function warm(value: JsonObject, baseline: JsonObject): JsonObject {
  return prepareContextDelivery({context: value, scope, capture_id: "capture-2", baseline,
    retained: {complete: true, target: baseline.target}});
}
const recover = (delivery: JsonObject, baseline: JsonObject, value: JsonObject): JsonObject =>
  restoreContextDelivery({delivery, baseline, current: full(value, "capture-2")});

test("full first; unsupported or uncertain retention never becomes an Agent gate", () => {
  const original = context(), saved = structuredClone(original), baseline = full(original);
  assert.equal(baseline.mode, "full");
  assert.deepEqual(baseline.context, original);
  for (const retained of [undefined, {complete: false, target: baseline.target}, {complete: true, target: {}}]) {
    const result = prepareContextDelivery({context: original, scope, capture_id: "capture-2", baseline, retained});
    assert.equal(result.mode, "full");
    assert.deepEqual(result.context, original);
  }
  assert.deepEqual(original, saved);
});

test("fresh control with exact warm bodies; changed source revisions do not resend requirements", () => {
  const original = context(), baseline = full(original), current = structuredClone(original);
  source(current, 0).revision = "revision-b";
  source(current, 1).authority_read = {provider_revision: "b"};
  (source(current, 1).todo as JsonObject).claimed_by = "different-agent";
  const requirements = (((source(current, 2).goal_acceptance_contract as JsonObject).outcome_requirements as JsonObject).outcomes as JsonObject[])[0].requirements as JsonObject[];
  requirements[0].status = "failed";
  requirements[0].agent_review = {note: "New failure invalidates the earlier plan."};
  const result = warm(current, baseline), fresh = result.context as JsonObject;
  assert.equal(result.mode, "delta");
  assert.deepEqual(result.replacements, []);
  assert.equal(source(fresh, 0).revision, "revision-b");
  assert.equal((source(fresh, 1).todo as JsonObject).claimed_by, "different-agent");
  assert.deepEqual(source(fresh, 3), source(current, 3)); // Mixed/unknown sources stay full.
  assert.deepEqual(recover(result, baseline, current).context, current);
  assert.ok(JSON.stringify(result).length < JSON.stringify(full(current)).length / 2);
  assert.deepEqual(baseline.context, original);
});

test("source and requirement reordering use identities, with current positions preserved", () => {
  const initial = context();
  const outcomes = ((source(initial, 2).goal_acceptance_contract as JsonObject).outcome_requirements as JsonObject).outcomes as JsonObject[];
  (outcomes[0].requirements as JsonObject[]).push({id: "r2", description: "Keep a distinct requirement", status: "unproven"});
  const baseline = full(initial), current = structuredClone(initial);
  const currentOutcomes = ((source(current, 2).goal_acceptance_contract as JsonObject).outcome_requirements as JsonObject).outcomes as JsonObject[];
  (currentOutcomes[0].requirements as JsonObject[]).reverse();
  (current.sources as JsonObject[]).reverse();
  const delta = warm(current, baseline);
  assert.equal(delta.mode, "delta");
  assert.deepEqual(delta.replacements, []);
  assert.deepEqual(recover(delta, baseline, current).context, current);
});

test("late constraints, null, empty and removed fields remain distinct", () => {
  for (const value of ["Late constraint: never delete the original source.", "", null, undefined]) {
    const initial = context(), baseline = full(initial), current = structuredClone(initial);
    const task = source(current, 1).todo as JsonObject;
    if (value === undefined) delete task.note;
    else task.note = value;
    const delta = warm(current, baseline);
    assert.equal(delta.mode, "delta");
    if (value === undefined) assert.equal((delta.removals as string[]).length, 1);
    else assert.equal((delta.replacements as JsonObject[]).length, 1);
    const restored = recover(delta, baseline, current);
    assert.equal(restored.mode, "delta");
    assert.deepEqual(restored.context, current);
  }
});

test("unexpected structured values in text-only adapters stay full", () => {
  const initial = context(), baseline = full(initial);
  for (const note of [{stop: true}, ["A", "B"], 42]) {
    const current = structuredClone(initial);
    (source(current, 1).todo as JsonObject).note = note;
    const result = warm(current, baseline);
    assert.equal(result.mode, "full");
    assert.deepEqual(result.context, current);
  }
});

test("scope/epoch/version, corruption, loss and ancestry automatically select full", () => {
  const initial = context(), baseline = full(initial);
  for (const key of ["goal_id", "agent_id", "session_id", "context_epoch", "projection_version"]) {
    const wrong = structuredClone(baseline); (wrong.target as JsonObject)[key] = "other";
    assert.equal(warm(initial, wrong).mode, "full", key);
  }
  const corrupt = structuredClone(baseline); (corrupt.context as JsonObject).instruction = "Changed after ACK";
  assert.equal(warm(initial, corrupt).mode, "full");
  assert.equal(warm(initial, {...baseline, ancestry: 32}).mode, "full");
  const tiny = {complete: true, sources: []};
  assert.equal(warm(tiny, full(tiny)).mode, "full");
  const failed = {...initial, complete: false};
  assert.equal(warm(failed, baseline).mode, "full");
  const duplicate = structuredClone(initial);
  (duplicate.sources as JsonObject[]).push(structuredClone((initial.sources as JsonObject[])[0]));
  assert.equal(warm(duplicate, baseline).mode, "full");
});

test("final assembly race, truncated or out-of-order delta uses same-capture full", () => {
  const initial = context(), baseline = full(initial), current = structuredClone(initial);
  source(current, 0).text = long + "NEW STOP CONDITION";
  const delta = warm(current, baseline), capture = full(current, "capture-2");
  const corruptions = [
    {...delta, replacements: []}, {...delta, removals: ["unknown"]}, {...delta, ancestry: 20},
    {...delta, reused: []}, {...delta, base: {...baseline.target as JsonObject, capture_id: "lost"}},
    {...delta, context: {complete: true}},
  ];
  for (const delivery of corruptions) {
    const restored = restoreContextDelivery({delivery, baseline, current: capture});
    assert.equal(restored.mode, "full");
    assert.deepEqual(restored.context, current);
  }
  // Epoch moves after preparation but before the final model request.
  const resetCapture = full(current, "capture-2", {...scope, context_epoch: "epoch-2"});
  const reset = restoreContextDelivery({delivery: delta, baseline, current: resetCapture});
  assert.equal(reset.mode, "full");
  assert.deepEqual(reset.context, current);
  // Missing acknowledgement leaves the previous baseline in place: a later
  // delta referring to another capture cannot advance it retroactively.
  const retained = {...delta, context: current};
  const next = warm(current, retained);
  assert.equal(recover(next, baseline, current).mode, "full");
});

test("cold-source title deduplication retains full body, distinct title and original capture", () => {
  const original = {todo: {text: long, title: long, note: "Keep this note", status: "open"}};
  const result = compactSelectedTodoSource(original);
  assert.deepEqual(result, {todo: {text: long, note: "Keep this note", status: "open"}});
  assert.equal(original.todo.title, long);
  const distinct = {todo: {...original.todo, title: "A meaningful short title"}};
  assert.strictEqual(compactSelectedTodoSource(distinct), distinct);
});

function evidenceContext(): JsonObject {
  return {complete: true, sources: [{source: "turn_start_capability_hook", kind: "explore_turn_context",
    hook_id: "explore.turn_context", capability_id: "explore", content: {
      ok: true, goal_id: "goal", agent_id: "agent", graph_enabled: true, harness_enabled: true,
      graph: {writeback_results: [{finding_id: "f1", status: "confirmed", summary: long,
        evidence_refs: ["artifact:source"], execution_observation: {scope: "candidate-a"}}],
        measurement_feedback: [{metric: "cost", value: 3, unit: "tokens", input_revision: "input-a"}],
        result_page: {revision: "r1", remaining: 0}, guidance: long,
        unknown_future_gate: {allowed: true}},
      harness: {orchestration_gate: {allowed: true}, selected_branches: [{todo_id: "task-a", status: "open"}],
        guidance: long}, boundary: {starts_agents: false}}}]};
}

test("registered structured evidence is reusable; live gates and unknown fields stay fresh", () => {
  const initial = evidenceContext(), baseline = full(initial), current = structuredClone(initial);
  const graph = source(current, 0).graph as JsonObject, harness = source(current, 0).harness as JsonObject;
  graph.result_page = {revision: "r2", remaining: 1, next_command: "read-next-page"};
  graph.unknown_future_gate = {allowed: false};
  harness.orchestration_gate = {allowed: false, reason: "stop"};
  harness.selected_branches = [];
  const delta = warm(current, baseline), fresh = source(delta.context as JsonObject, 0);
  assert.equal(delta.mode, "delta");
  assert.deepEqual(delta.replacements, []);
  assert.equal((fresh.graph as JsonObject).writeback_results, undefined);
  assert.deepEqual((fresh.graph as JsonObject).result_page, graph.result_page);
  assert.deepEqual((fresh.graph as JsonObject).unknown_future_gate, {allowed: false});
  assert.deepEqual((fresh.harness as JsonObject).orchestration_gate, harness.orchestration_gate);
  assert.deepEqual((fresh.harness as JsonObject).selected_branches, []);
  assert.deepEqual(recover(delta, baseline, current).context, current);
});

test("changed evidence replaces whole arrays including provenance, null and late refutation", () => {
  const initial = evidenceContext(), baseline = full(initial);
  for (const evidence of [[], null, [{finding_id: "f1", status: "refuted", summary: "A new counterexample.",
    evidence_refs: ["artifact:new-source"], execution_observation: {scope: "candidate-b"}}], undefined]) {
    const current = structuredClone(initial), graph = source(current, 0).graph as JsonObject;
    if (evidence === undefined) delete graph.writeback_results;
    else graph.writeback_results = evidence;
    const delta = warm(current, baseline);
    assert.equal(delta.mode, "delta");
    if (evidence === undefined) assert.equal((delta.removals as string[]).length, 1);
    else assert.deepEqual((delta.replacements as JsonObject[]).map(row => row.value), [evidence]);
    assert.deepEqual(recover(delta, baseline, current).context, current);
  }
});

test("unknown/failed hook and ambiguous scope never borrow a registered hook's evidence", () => {
  const initial = evidenceContext(), baseline = full(initial);
  for (const field of ["hook_id", "capability_id", "kind"]) {
    const current = structuredClone(initial);
    (current.sources as JsonObject[])[0][field] = "unknown";
    assert.equal(warm(current, baseline).mode, "full");
  }
  const failed = structuredClone(initial); source(failed, 0).ok = false;
  assert.equal(warm(failed, baseline).mode, "full");
  const duplicate = structuredClone(initial);
  (duplicate.sources as JsonObject[]).push(structuredClone((initial.sources as JsonObject[])[0]));
  assert.equal(warm(duplicate, baseline).mode, "full");
  const different = structuredClone(initial); source(different, 0).todo_id = "different-task";
  assert.equal(warm(different, baseline).mode, "full");
});
