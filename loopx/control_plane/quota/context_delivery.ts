/** Presentation of an immutable work-context capture. No admission or state writes.
 * A candidate delta is usable only at a host's final model-input assembly boundary;
 * a previous CLI output or a successful capture handoff is not retention proof. */
import type {JsonObject} from "../effect_program.ts";
import {jsonObject, requireJsonObject, requireNonEmptyString} from "../runtime_decode.ts";
import {canonicalAuthorityJson, canonicalAuthoritySha256} from "../coordination/authority_store_codec.ts";
import {reusableTurnContextPaths} from "../capability_hooks.ts";

const VERSION = "work_context_delivery_v1";
const MAX_ANCESTRY = 32;
type Path = (string | number)[];
type Part = {path: Path; value: unknown};
type Split = {fresh: JsonObject; parts: Map<string, Part>; valid: boolean};
const clone = <T>(value: T): T => structuredClone(value);
const equal = (a: unknown, b: unknown): boolean => a === undefined || b === undefined ? a === b
  : JSON.stringify(canonicalAuthorityJson(a)) === JSON.stringify(canonicalAuthorityJson(b));
const digest = (value: unknown): string => `sha256:${canonicalAuthoritySha256(value)}`;
const bytes = (value: unknown): number => Buffer.byteLength(JSON.stringify(value), "utf8");

/** A title equal to the complete body carries no second instruction. Never use
 * the bounded hot title/text as the source, and retain a genuinely distinct title. */
export function compactSelectedTodoSource(content: JsonObject): JsonObject {
  const todo = jsonObject(content.todo);
  if (!todo || typeof todo.text !== "string" || todo.title !== todo.text) return content;
  const copy = {...todo};
  delete copy.title;
  return {...content, todo: copy};
}

function parentAt(root: JsonObject, path: Path): Record<string | number, unknown> {
  let value: unknown = root;
  for (const key of path.slice(0, -1)) value = (value as Record<string | number, unknown>)[key];
  return value as Record<string | number, unknown>;
}

/** Registered requirement fields and capability evidence subtrees are reusable. Revisions, source
 * failures, claims, reviews, grants, current gates and unknown fields stay fresh.
 * Source-array order is transport layout, never the identity of a requirement. */
function splitContext(context: JsonObject): Split {
  const fresh = clone(context), parts = new Map<string, Part>(), identities = new Set<string>();
  let valid = context.complete === true;
  const add = (identity: string, path: Path, structured = false) => {
    if (identities.has(identity)) { valid = false; return; }
    identities.add(identity);
    const parent = parentAt(fresh, path), key = path[path.length - 1];
    if (!Object.hasOwn(parent, key)) return;
    // These adapters own literal text, not arbitrary nested control records.
    if (!structured && parent[key] !== null && typeof parent[key] !== "string") { valid = false; return; }
    parts.set(identity, {path, value: parent[key]});
    delete parent[key];
  };
  const sources = Array.isArray(fresh.sources) ? fresh.sources : [];
  const sourceIds = new Set<string>();
  for (let i = 0; i < sources.length; i++) {
    const source = jsonObject(sources[i]), content = jsonObject(source?.content);
    if (!source || !content || content.ok === false || content.read_complete === false) continue;
    const prefix: Path = ["sources", i, "content"];
    const kind = source.source;
    if (kind === "goal_state" && typeof content.state_file === "string"
        && typeof content.text === "string" && Array.isArray(content.excluded_todo_regions)) {
      const id = JSON.stringify([kind, content.state_file]);
      if (sourceIds.has(id)) { valid = false; continue; }
      sourceIds.add(id);
      add(id, [...prefix, "text"]);
    } else if (kind === "selected_todo") {
      const todo = jsonObject(content.todo);
      // An already referenced selected body lacks an independent source id.
      // Keep such residual metadata full rather than guessing its identity.
      if (!todo || typeof todo.todo_id !== "string" || !todo.todo_id) continue;
      const id = JSON.stringify([kind, todo.todo_id]);
      if (sourceIds.has(id)) { valid = false; continue; }
      sourceIds.add(id);
      for (const key of ["text", "note", "title"]) add(JSON.stringify([kind, todo.todo_id, key]), [...prefix, "todo", key]);
    } else if (kind === "goal_acceptance") {
      if (sourceIds.has(kind)) { valid = false; continue; }
      sourceIds.add(kind);
      const contract = jsonObject(content.goal_acceptance_contract);
      const outcomes = jsonObject(contract?.outcome_requirements)?.outcomes;
      if (!Array.isArray(outcomes)) continue;
      const seen = new Set<string>();
      for (let j = 0; j < outcomes.length; j++) {
        const outcome = jsonObject(outcomes[j]);
        if (!outcome || typeof outcome.id !== "string" || !outcome.id || seen.has(outcome.id)) {
          valid = false; continue;
        }
        seen.add(outcome.id);
        const path = [...prefix, "goal_acceptance_contract", "outcome_requirements", "outcomes", j];
        add(JSON.stringify([kind, outcome.id, "objective"]), [...path, "objective"]);
        const requirements = outcome.requirements;
        if (!Array.isArray(requirements)) continue;
        const requirementIds = new Set<string>();
        for (let k = 0; k < requirements.length; k++) {
          const requirement = jsonObject(requirements[k]);
          if (!requirement || typeof requirement.id !== "string" || !requirement.id || requirementIds.has(requirement.id)) {
            valid = false; continue;
          }
          requirementIds.add(requirement.id);
          add(JSON.stringify([kind, outcome.id, requirement.id, "description"]), [...path, "requirements", k, "description"]);
        }
      }
    } else {
      const paths = reusableTurnContextPaths(source);
      if (!paths.length) continue;
      if (content.ok !== true || typeof content.goal_id !== "string" || typeof content.agent_id !== "string") continue;
      const identity = [kind, source.hook_id, source.capability_id, content.goal_id, content.agent_id, content.todo_id ?? null];
      const id = JSON.stringify(identity);
      if (sourceIds.has(id)) { valid = false; continue; }
      sourceIds.add(id);
      for (const path of paths) {
        let value: unknown = content;
        for (const key of path.slice(0, -1)) value = jsonObject(value)?.[key];
        if (jsonObject(value)) add(JSON.stringify([...identity, ...path]), [...prefix, ...path], true);
      }
    }
  }
  return {fresh, parts, valid};
}

function targetBinding(request: JsonObject, context: JsonObject): JsonObject {
  const scope = requireJsonObject(request.scope, "context delivery scope");
  const binding: JsonObject = {projection_version: VERSION};
  for (const key of ["goal_id", "agent_id", "session_id", "context_epoch"]) {
    binding[key] = requireNonEmptyString(scope[key], `scope.${key}`);
  }
  binding.capture_id = requireNonEmptyString(request.capture_id, "capture_id");
  binding.context_digest = digest(context);
  return binding;
}

function compatible(base: JsonObject, target: JsonObject): boolean {
  return ["goal_id", "agent_id", "session_id", "context_epoch", "projection_version"]
    .every(key => base[key] === target[key]);
}

/** Host-facing preparation, also used through the existing Turn projection RPC.
 * `retained` is an exact host observation, not an Agent-supplied CLI option.
 * The host MUST re-evaluate at final input assembly, then ACK only intact input.
 * Unsupported native hosts keep their existing complete output unchanged. */
export function prepareContextDelivery(request: JsonObject): JsonObject {
  const context = requireJsonObject(request.context, "current work context");
  const target = targetBinding(request, context);
  const full = (reason: string): JsonObject => ({schema_version: VERSION, mode: "full", target,
    ancestry: 0, reason, context: clone(context)});
  const baseline = jsonObject(request.baseline), retained = jsonObject(request.retained);
  const binding = jsonObject(baseline?.target), prior = jsonObject(baseline?.context);
  if (!binding || !prior || !retained || retained.complete !== true
      || !equal(retained.target, binding) || !compatible(binding, target)
      || binding.context_digest !== digest(prior)) return full("baseline_unavailable");
  const depth = baseline?.ancestry;
  if (!Number.isSafeInteger(depth) || Number(depth) < 0 || Number(depth) >= MAX_ANCESTRY) return full("full_refresh_due");
  const before = splitContext(prior), after = splitContext(context);
  if (!before.valid || !after.valid) return full("source_not_reusable");
  const replacements: JsonObject[] = [], removals: Path[] = [], reused: JsonObject[] = [];
  for (const [id, part] of after.parts) {
    const previous = before.parts.get(id);
    if (!previous || !equal(previous.value, part.value)) replacements.push({path: part.path, value: clone(part.value)});
    else reused.push({path: part.path, ...(!equal(previous.path, part.path) ? {from: previous.path} : {})});
  }
  for (const [id, part] of before.parts) if (!after.parts.has(id)) removals.push(part.path);
  const delta: JsonObject = {schema_version: VERSION, mode: "delta", target, base: binding,
    ancestry: Number(depth) + 1, context: after.fresh, reused, replacements, removals,
    instruction: "Fresh control and source metadata are complete. Reuse unchanged registered subtrees from the confirmed baseline; their requirements remain binding. Apply exact replacements/removals. Lost context requires automatic same-capture full delivery, not an owner question."};
  if (bytes(delta) >= bytes(full("delta_not_smaller"))) return full("delta_not_smaller");
  // An independent reconstruction check guards the released candidate.
  const restored = restoreContextDelivery({delivery: delta, baseline, current: full("recovery")});
  if (restored.mode !== "delta" || !equal(restored.context, context)) return full("reconstruction_failed");
  return delta;
}

/** Recover against the immutable CURRENT capture, never by rerunning admission.
 * A changed epoch, truncated/lost/reordered delivery or failed reconstruction
 * returns that full capture. Fresh authority/source checks remain caller-owned. */
export function restoreContextDelivery(request: JsonObject): JsonObject {
  const current = requireJsonObject(request.current, "current full capture");
  const currentContext = requireJsonObject(current.context, "current full context");
  const target = requireJsonObject(current.target, "current capture binding");
  if (current.mode !== "full" || current.schema_version !== VERSION || target.context_digest !== digest(currentContext)) {
    throw new Error("current full capture is invalid");
  }
  const fallback = (): JsonObject => ({...clone(current), reason: "automatic_full_recovery", ancestry: 0});
  try {
    const delivery = requireJsonObject(request.delivery, "delivery"), baseline = requireJsonObject(request.baseline, "baseline");
    const base = requireJsonObject(baseline.target, "baseline target"), context = requireJsonObject(baseline.context, "baseline context");
    if (delivery.schema_version !== VERSION || delivery.mode !== "delta" || !equal(delivery.target, target)
        || !equal(delivery.base, base) || !compatible(base, target) || base.context_digest !== digest(context)
        || !Number.isSafeInteger(baseline.ancestry) || Number(baseline.ancestry) < 0
        || delivery.ancestry !== Number(baseline.ancestry) + 1 || Number(delivery.ancestry) > MAX_ANCESTRY) return fallback();
    const split = splitContext(context), expected = splitContext(currentContext);
    if (!split.valid || !expected.valid || !Array.isArray(delivery.removals)
        || !Array.isArray(delivery.replacements) || !Array.isArray(delivery.reused)) return fallback();
    const removed = [...split.parts].filter(([id]) => !expected.parts.has(id)).map(([, part]) => part.path);
    if (!equal(delivery.removals, removed)) return fallback();
    // Stable source identities stay internal. Wire paths are readable and occur
    // once; a moved source adds its prior path rather than repeating long ids.
    const rows = (items: unknown[]): Map<string, JsonObject> => {
      const result = new Map<string, JsonObject>();
      for (const raw of items) {
        const item = requireJsonObject(raw, "subtree");
        if (!Array.isArray(item.path)) throw new Error("subtree path missing");
        const key = JSON.stringify(item.path);
        if (result.has(key)) throw new Error("duplicate subtree path");
        result.set(key, item);
      }
      return result;
    };
    const replacements = rows(delivery.replacements), reused = rows(delivery.reused);
    if (replacements.size + reused.size !== expected.parts.size) return fallback();
    const result = clone(requireJsonObject(delivery.context, "fresh context"));
    for (const [id, part] of expected.parts) {
      const key = JSON.stringify(part.path), replacement = replacements.get(key), reuse = reused.get(key);
      if (Boolean(replacement) === Boolean(reuse)) return fallback();
      let value: unknown;
      if (replacement) {
        if (!Object.hasOwn(replacement, "value")) return fallback();
        value = replacement.value;
      } else {
        const previous = split.parts.get(id);
        if (!previous || !equal(reuse!.from ?? reuse!.path, previous.path)) return fallback();
        value = previous.value;
      }
      // Write only independently derived current paths, never wire paths.
      parentAt(result, part.path)[part.path[part.path.length - 1]] = clone(value);
    }
    if (!equal(result, currentContext)) return fallback();
    return {...clone(delivery), context: result};
  } catch { return fallback(); }
}
