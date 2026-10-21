import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {runExperience, validateExperiencePlan} from "../../loopx/control_plane/capabilities/content_experience.ts";

const brief = () => JSON.parse(readFileSync(new URL("../../examples/content-ops-experience/evidence-return.json", import.meta.url), "utf8"));

test("one policy exposes context cost and a genuine failed return route", () => {
  const plan = brief();
  const complete = runExperience({plan, scenario_id: "complete", policy_id: "evidence_first"});
  assert.equal(complete.status, "goal_reached");
  assert.equal(complete.remaining_budget, 1);
  assert.deepEqual(complete.trace.map(f => f.state), ["intent", "working", "review", "accepted"]);
  const missing = runExperience({plan, scenario_id: "missing", policy_id: "evidence_first"});
  assert.equal(missing.remaining_budget, 0);
  assert.deepEqual(missing.trace.map(f => f.state), ["intent", "clarification", "working", "review", "accepted"]);
  const wrong = runExperience({plan, scenario_id: "wrong_route", policy_id: "evidence_first"});
  assert.equal(wrong.status, "budget_exhausted");
  assert.equal(wrong.trace.at(-1)!.state, "lost");
  assert.equal(wrong.trace.at(-1)!.spent, 3, "unaffordable recovery cannot spend or transition");
  assert.equal(wrong.trace.at(-1)!.applied, false);
  assert.equal(complete.learning_effect, "not_tested");
  assert.equal(complete.publish_authorized, false);
});

test("manual decisions, reset and strategy replay use the same transitions", () => {
  const plan = brief(), parameters = {context: "complete", return_route: "origin"};
  const manual = runExperience({plan, parameters, actions: ["delegate", "return", "verify"]});
  assert.deepEqual(manual.trace, runExperience({plan, parameters, policy_id: "evidence_first"}).trace);
  const reset = runExperience({plan, parameters, actions: []});
  assert.equal(reset.trace.length, 1);
  assert.equal(reset.trace[0]!.state, "intent");
  assert.equal(reset.remaining_budget, 4);
  assert.equal(runExperience({plan, parameters, actions: ["delegate", "claim_done"]}).status, "terminal");
  const unavailable = runExperience({plan, parameters, actions: ["verify"]});
  assert.equal(unavailable.status, "action_unavailable");
  assert.equal(unavailable.remaining_budget, 4);
  assert.equal(unavailable.trace.at(-1)!.state, "intent");
  assert.deepEqual(runExperience({plan, parameters, actions: ["delegate", "return", "verify", "reroute"]}).unexecuted_actions, ["reroute"]);
});

test("a second brief reuses the engine without handoff-specific states", () => {
  const plan = JSON.parse(readFileSync(new URL("../../examples/content-ops-experience/service-diagnosis.json", import.meta.url), "utf8"));
  for (const scenario_id of ["cpu", "io"]) {
    const measured = runExperience({plan, scenario_id, policy_id: "measure_first"});
    assert.equal(measured.status, "goal_reached");
    assert.equal(measured.trace[1]!.state, `${scenario_id}_found`);
    assert.equal(measured.remaining_budget, 1);
    assert.equal(runExperience({plan, scenario_id, policy_id: "restart_first"}).status, "terminal");
  }
});

test("ambiguous causes, impossible references and author code are rejected", () => {
  for (const change of [
    (p: any) => p.transitions.push({...p.transitions[0], when: {}}),
    (p: any) => {p.transitions[0].to = "absent";},
    (p: any) => {p.transitions[0].from = "accepted";},
    (p: any) => {p.transitions[0].when = {context: "absent"};},
    (p: any) => p.states.push({...p.states[0]}),
    (p: any) => {p.states[0].goal = true;},
    (p: any) => {p.actions[0].cost = 0;},
    (p: any) => {p.budget = true;},
    (p: any) => {p.states[0].id = "__proto__";},
    (p: any) => p.policies[0].choices.push({...p.policies[0].choices[0]}),
    (p: any) => {p.scenarios[0].parameters = {unknown: "complete"};},
    (p: any) => {p.script = "fetch('/outside')";},
  ]) {const plan = brief(); change(plan); assert.throws(() => validateExperiencePlan({plan}));}
});

test("source and rules bind the digest; ambiguous requests cannot be ignored", () => {
  const plan = brief(), original = validateExperiencePlan({plan});
  assert.equal(validateExperiencePlan({plan: original.plan}).plan_digest, original.plan_digest);
  for (const key of ["source_ref", "boundary", "learning_goal"]) {
    assert.notEqual(validateExperiencePlan({plan: {...plan, [key]: `${plan[key]} revised`}}).plan_digest, original.plan_digest);
  }
  for (const request of [{actions: ["unknown"]}, {parameters: {context: "unknown"}}, {scenario_id: "unknown"},
      {policy_id: "unknown"}, {policy_id: "evidence_first", actions: []}, {script: "anything"}]) {
    assert.throws(() => runExperience({plan, ...request}));
  }
});

test("cycles and incomplete policies stop at the declared boundary", () => {
  const plan = brief();
  plan.transitions = [{from: "intent", action: "delegate", to: "intent", feedback: "Still waiting", when: {}}];
  plan.max_steps = 2;
  const run = runExperience({plan, actions: ["delegate", "delegate", "delegate"]});
  assert.equal(run.status, "step_limit");
  assert.equal(run.trace.length, 3);
  assert.deepEqual(run.unexecuted_actions, ["delegate"]);
  assert.equal(runExperience({plan, actions: ["delegate", "delegate"]}).status, "step_limit");
  plan.policies[0].choices = [{state: "working", action: "return"}];
  assert.equal(runExperience({plan, policy_id: "evidence_first"}).status, "policy_incomplete");
});
