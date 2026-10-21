/** Source-bound, finite teaching models. These are local content outcomes,
 * never Goal state, tool permissions, learner assessment or publication proof. */
import {createHash} from "node:crypto";
import {EffectRuntimeRequestError} from "../effect_runtime_errors.ts";

import type {ExperienceParameter, ExperiencePlan, ExperienceFrame, ExperienceRun} from "./content_experience_contract.ts";

type Obj = Record<string, unknown>;
function obj(value: unknown, label: string, fields?: readonly string[]): Obj {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new EffectRuntimeRequestError(`${label} must be an object`);
  if (fields && Object.keys(value).some(key => !fields.includes(key))) throw new EffectRuntimeRequestError(`${label} contains unsupported fields`);
  return value as Obj;
}
function text(value: unknown, label: string, max = 1200): string {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value)) throw new EffectRuntimeRequestError(`${label} must be nonempty text, at most ${max} characters`);
  return value.trim();
}
function id(value: unknown, label: string): string {
  const s = text(value, label, 48);
  if (!/^[a-z][a-z0-9_-]*$/u.test(s) || ["constructor", "prototype", "__proto__"].includes(s)) throw new EffectRuntimeRequestError(`${label} must be a simple stable id`);
  return s;
}
function array<T>(value: unknown, label: string, min: number, max: number, read: (v: unknown) => T): T[] {
  if (!Array.isArray(value) || value.length < min || value.length > max) throw new EffectRuntimeRequestError(`${label} requires ${min}–${max} entries`);
  return value.map(read);
}
function number(value: unknown, label: string, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) throw new EffectRuntimeRequestError(`${label} must be an integer from ${min} to ${max}`);
  return value;
}
function unique<T extends {id: string}>(values: T[], label: string): T[] {
  if (new Set(values.map(v => v.id)).size !== values.length) throw new EffectRuntimeRequestError(`${label} ids must be unique`);
  return values;
}
function digest(value: unknown): string {
  const sort = (v: unknown): unknown => Array.isArray(v) ? v.map(sort) : v && typeof v === "object"
    ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort((v as Obj)[k])])) : v;
  return `sha256:${createHash("sha256").update(JSON.stringify(sort(value))).digest("hex")}`;
}
function selections(value: unknown, parameters: ExperienceParameter[], label: string): Record<string, string> {
  const raw = obj(value, label), result: Record<string, string> = {};
  for (const [key, v] of Object.entries(raw)) {
    const p = parameters.find(p => p.id === key);
    if (!p || !p.choices.some(c => c.id === v)) throw new EffectRuntimeRequestError(`${label} contains an unknown parameter or choice`);
    result[key] = String(v);
  }
  return result;
}

export function validateExperiencePlan(input: unknown) {
  const request = obj(input, "request", ["plan"]);
  const p = obj(request.plan, "plan", ["schema_version", "title", "learning_goal", "source_ref", "boundary", "assumptions", "initial_state", "budget", "max_steps", "parameters", "states", "actions", "transitions", "policies", "scenarios"]);
  if (p.schema_version !== "content_ops_experience_v0") throw new EffectRuntimeRequestError("Unsupported experience schema");
  const parameters = unique(array(p.parameters, "parameters", 0, 4, v => {
    const a = obj(v, "parameter", ["id", "label", "choices", "default"]);
    const choices = unique(array(a.choices, "choices", 2, 4, v => {
      const c = obj(v, "choice", ["id", "label"]); return {id: id(c.id, "choice.id"), label: text(c.label, "choice.label", 120)};
    }), "choice");
    const defaultId = id(a.default, "parameter.default");
    if (!choices.some(c => c.id === defaultId)) throw new EffectRuntimeRequestError("Parameter default must be a declared choice");
    return {id: id(a.id, "parameter.id"), label: text(a.label, "parameter.label", 120), choices, default: defaultId};
  }), "parameter");
  const states = unique(array(p.states, "states", 2, 24, v => {
    const a = obj(v, "state", ["id", "label", "description", "terminal", "goal"]);
    if (typeof a.terminal !== "boolean" || typeof a.goal !== "boolean" || a.goal && !a.terminal) throw new EffectRuntimeRequestError("States declare terminal/goal booleans; a goal must be terminal");
    return {id: id(a.id, "state.id"), label: text(a.label, "state.label", 120), description: text(a.description, "state.description"), terminal: a.terminal, goal: a.goal};
  }), "state");
  const actions = unique(array(p.actions, "actions", 1, 16, v => {
    const a = obj(v, "action", ["id", "label", "cost"]); return {id: id(a.id, "action.id"), label: text(a.label, "action.label", 140), cost: number(a.cost, "action.cost", 1, 100)};
  }), "action");
  const initial = id(p.initial_state, "initial_state");
  if (!states.some(s => s.id === initial) || !states.some(s => s.goal)) throw new EffectRuntimeRequestError("Declare an initial state and at least one goal state");
  const transitions = array(p.transitions, "transitions", 1, 128, v => {
    const a = obj(v, "transition", ["from", "action", "to", "when", "feedback"]);
    const from = id(a.from, "transition.from"), to = id(a.to, "transition.to"), action = id(a.action, "transition.action");
    if (!states.some(s => s.id === from && !s.terminal) || !states.some(s => s.id === to) || !actions.some(a => a.id === action)) throw new EffectRuntimeRequestError("Transition references an unknown state/action or leaves a terminal state");
    return {from, to, action, when: selections(a.when ?? {}, parameters, "transition.when"), feedback: text(a.feedback, "transition.feedback")};
  });
  // Overlap is a content authoring error. Never let input order choose cause.
  for (let i = 0; i < transitions.length; i++) for (let j = i + 1; j < transitions.length; j++) {
    const a = transitions[i]!, b = transitions[j]!;
    if (a.from === b.from && a.action === b.action && Object.entries(a.when).every(([k, v]) => !Object.hasOwn(b.when, k) || b.when[k] === v)) {
      throw new EffectRuntimeRequestError("Transition conditions overlap for the same state/action");
    }
  }
  const policies = unique(array(p.policies, "policies", 1, 8, v => {
    const a = obj(v, "policy", ["id", "label", "choices"]);
    const choices = array(a.choices, "policy.choices", 1, 24, v => {
      const c = obj(v, "policy choice", ["state", "action"]), state = id(c.state, "policy state"), action = id(c.action, "policy action");
      if (!states.some(s => s.id === state) || !actions.some(a => a.id === action)) throw new EffectRuntimeRequestError("Policy references an unknown state/action");
      return {state, action};
    });
    if (new Set(choices.map(c => c.state)).size !== choices.length) throw new EffectRuntimeRequestError("Policy declares more than one action for a state");
    return {id: id(a.id, "policy.id"), label: text(a.label, "policy.label", 140), choices};
  }), "policy");
  const scenarios = unique(array(p.scenarios, "scenarios", 1, 8, v => {
    const a = obj(v, "scenario", ["id", "label", "parameters"]); return {id: id(a.id, "scenario.id"), label: text(a.label, "scenario.label", 140), parameters: selections(a.parameters, parameters, "scenario.parameters")};
  }), "scenario");
  const plan: ExperiencePlan = {schema_version: "content_ops_experience_v0", title: text(p.title, "title", 140), learning_goal: text(p.learning_goal, "learning_goal"), source_ref: text(p.source_ref, "source_ref", 400), boundary: text(p.boundary, "boundary", 400), assumptions: array(p.assumptions, "assumptions", 1, 8, v => text(v, "assumption", 400)), initial_state: initial, budget: number(p.budget, "budget", 1, 1000), max_steps: number(p.max_steps, "max_steps", 1, 40), parameters, states, actions, transitions, policies, scenarios};
  return {ok: true, schema_version: "content_ops_experience_plan_result_v0", plan, plan_digest: digest(plan), visibility: "local_private", learning_effect: "not_tested", publish_authorized: false};
}

export function runExperience(input: unknown): ExperienceRun {
  const r = obj(input, "request", ["plan", "parameters", "scenario_id", "policy_id", "actions"]), checked = validateExperiencePlan({plan: r.plan}), p = checked.plan;
  if (r.policy_id != null && r.actions != null) throw new EffectRuntimeRequestError("Choose a policy or manual actions, not both");
  const scenario = r.scenario_id == null ? null : p.scenarios.find(s => s.id === r.scenario_id);
  if (r.scenario_id != null && !scenario) throw new EffectRuntimeRequestError("Unknown scenario");
  const policy = r.policy_id == null ? null : p.policies.find(s => s.id === r.policy_id);
  if (r.policy_id != null && !policy) throw new EffectRuntimeRequestError("Unknown policy");
  const parameters = {...Object.fromEntries(p.parameters.map(p => [p.id, p.default])), ...scenario?.parameters, ...selections(r.parameters ?? {}, p.parameters, "parameters")};
  const requestedActions = array(r.actions ?? [], "actions", 0, 40, v => id(v, "action"));
  if (requestedActions.some(id => !p.actions.some(a => a.id === id))) throw new EffectRuntimeRequestError("Unknown manual action");
  const trace: ExperienceFrame[] = [{state: p.initial_state, action: null, feedback: p.states.find(s => s.id === p.initial_state)!.description, spent: 0, applied: true}];
  let status: ExperienceRun["status"] = "in_progress", consumed = 0;
  for (let i = 0; i <= p.max_steps; i++) {
    const frame = trace[trace.length - 1]!, state = p.states.find(s => s.id === frame.state)!;
    if (state.terminal) {status = state.goal ? "goal_reached" : "terminal"; break;}
    if (i === p.max_steps) {status = "step_limit"; break;}
    const next = policy ? policy.choices.find(c => c.state === state.id)?.action : requestedActions[consumed];
    if (next === undefined) {if (policy) status = "policy_incomplete"; break;}
    const action = p.actions.find(a => a.id === next)!;
    const edge = p.transitions.find(t => t.from === state.id && t.action === next && Object.entries(t.when).every(([k, v]) => parameters[k] === v));
    if (!policy) consumed++;
    if (!edge || frame.spent + action.cost > p.budget) {
      status = edge ? "budget_exhausted" : "action_unavailable";
      trace.push({state: state.id, action: next, spent: frame.spent, applied: false, feedback: edge ? "The action exceeds the remaining budget; no transition occurred." : "This action has no transition under the selected conditions; the state is unchanged."});
      break;
    }
    trace.push({state: edge.to, action: next, spent: frame.spent + action.cost, feedback: edge.feedback, applied: true});
  }
  return {ok: true, schema_version: "content_ops_experience_run_v0", plan_digest: checked.plan_digest, parameters, policy_id: policy?.id ?? null, scenario_id: scenario?.id ?? null, trace, status, unexecuted_actions: requestedActions.slice(consumed), remaining_budget: p.budget - trace[trace.length - 1]!.spent, learning_effect: "not_tested", publish_authorized: false};
}
