/** Reconcile persisted request counters without changing session-counter accounting. */
import type {TrajectoryRequestCoverage, TrajectoryRequestTokens} from './trajectory_assessment_types.ts';

const keys = ['input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
  'output_tokens', 'reasoning_output_tokens', 'total_tokens'] as const;
const sessionKeys = ['input_tokens', 'cached_input_tokens', 'output_tokens'] as const;
const zero = (): TrajectoryRequestTokens => Object.fromEntries(keys.map(k => [k, 0])) as unknown as TrajectoryRequestTokens;
class ReconciliationError extends Error {}
const invalid = (reason: string): never => { throw new ReconciliationError(reason); };
const object = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return invalid('Missing request fields.');
  return v as Record<string, unknown>;
};
function tokens(value: unknown): TrajectoryRequestTokens {
  const v = object(value);
  if (keys.some(k => typeof v[k] !== 'number' || !Number.isSafeInteger(v[k]) || (v[k] as number) < 0)) return invalid('Missing or invalid request counters.');
  const t = Object.fromEntries(keys.map(k => [k, v[k]])) as unknown as TrajectoryRequestTokens;
  if (t.cached_input_tokens > t.input_tokens || t.cache_write_input_tokens > t.input_tokens
    || t.reasoning_output_tokens > t.output_tokens || t.total_tokens !== t.input_tokens + t.output_tokens) return invalid('Inconsistent request counter subsets or total.');
  return t;
}
const add = (a: TrajectoryRequestTokens, b: TrajectoryRequestTokens) => tokens(Object.fromEntries(keys.map(k => [k, a[k] + b[k]])));
const equal = (a: TrajectoryRequestTokens, b: TrajectoryRequestTokens) => keys.every(k => a[k] === b[k]);
function record(value: unknown, session: string) {
  const p = object(value);
  if (['response_id', 'turn_id', 'root_turn_id'].some(k => typeof p[k] !== 'string' || !p[k])
    || p.thread_id !== session || p.session_id !== session) return invalid('Request session or Turn identity mismatch.');
  return {response_id: p.response_id as string, turn_id: p.turn_id as string, root_turn_id: p.root_turn_id as string,
    usage: tokens(p.usage), thread: tokens(p.thread_token_usage), turn: tokens(p.turn_token_usage)};
}
type Request = ReturnType<typeof record>;
const same = (a: Request, b: Request) => a.response_id === b.response_id && a.turn_id === b.turn_id
  && a.root_turn_id === b.root_turn_id && equal(a.usage, b.usage) && equal(a.thread, b.thread) && equal(a.turn, b.turn);

/** Called only after the existing session/lifecycle validation has succeeded. */
export function reconcileTrajectoryRequests(rows: Array<{type?: unknown; payload?: unknown; timestamp?: unknown}>, session: string): TrajectoryRequestCoverage | undefined {
  // Old captures keep their exact projection and identity. Absence is unknown,
  // not a zero-request or zero-compaction observation.
  if (!rows.some(e => e.type === 'token_usage_record' || e.type === 'compacted')) return undefined;
  const method = 'codex_request_reconciliation_v1';
  try {
    const compactionIds = new Set<string>();
    for (const e of rows.filter(e => e.type === 'compacted')) {
      const id = object(e.payload).compaction_response_id;
      if (typeof id !== 'string' || !id) return invalid('Compaction request identity is unavailable.');
      compactionIds.add(id);
    }
    const requests = new Map<string, Request>(), turns = new Map<string, TrajectoryRequestTokens>();
    let total = zero(), ordinary = zero(), compaction = zero(), duplicates = 0, snapshots = 0;
    let active: string | null = null, previousTime = -Infinity, observedThrough = '';
    let lastCounter: Record<string, number> | null = null;
    for (const e of rows) {
      const p = object(e.payload);
      if (e.type === 'session_meta') continue;
      if (e.type !== 'token_usage_record' && e.type !== 'compacted'
        && !(e.type === 'event_msg' && ['task_started', 'task_complete', 'token_count'].includes(p.type as string))) continue;
      if (e.type === 'event_msg' && p.type === 'task_started') active = p.turn_id as string;
      if (e.type === 'event_msg' && p.type === 'task_complete') active = null;
      if (typeof e.timestamp !== 'string' || !/\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(e.timestamp)
        || !Number.isFinite(Date.parse(e.timestamp)) || Date.parse(e.timestamp) < previousTime) return invalid('Request timestamps are invalid or out of order.');
      previousTime = Date.parse(e.timestamp);
      if (e.type === 'token_usage_record') {
        observedThrough = e.timestamp;
        const r = record(p, session), old = requests.get(r.response_id);
        if (old) {
          if (!same(old, r)) return invalid('Conflicting records for one response.');
          duplicates++;
          continue;
        }
        if (!active || r.turn_id !== active) return invalid('Request is outside its captured Turn.');
        total = add(total, r.usage);
        const turn = add(turns.get(r.turn_id) ?? zero(), r.usage);
        if (!equal(total, r.thread)) return invalid('Request prefix is missing or cumulative counters disagree.');
        if (!equal(turn, r.turn)) return invalid('Turn request prefix is missing or cumulative counters disagree.');
        turns.set(r.turn_id, turn); requests.set(r.response_id, r);
        if (compactionIds.has(r.response_id)) compaction = add(compaction, r.usage);
        else ordinary = add(ordinary, r.usage);
      } else if (e.type === 'compacted') {
        const r = requests.get(p.compaction_response_id as string);
        if (!r || !active || r.turn_id !== active || !same(r, record(p.latest_token_usage_record, session))) return invalid('Compaction request or its mirror cannot be reconciled.');
        // latest_token_usage_record is a mirror, never another request.
      } else if (p.type === 'token_count' && p.info) {
        const counter = object(object(p.info).total_token_usage);
        if (sessionKeys.some(k => ordinary[k] !== counter[k])) return invalid('Session counters disagree with non-compaction requests.');
        lastCounter = counter as Record<string, number>; snapshots++;
      }
    }
    if (!requests.size || !snapshots) return invalid('Request or session-counter observations are missing.');
    if (sessionKeys.some(k => ordinary[k] !== lastCounter![k])) return invalid('Requests extend beyond the last session-counter observation.');
    return {method, status: 'verified', unique_requests: requests.size, compaction_requests: compactionIds.size,
      duplicate_records: duplicates, counter_observations: snapshots, observed_through: observedThrough, all_requests: total, compaction};
  } catch (error) {
    // A supplementary source failure does not rewrite or invalidate the
    // independently validated historical session counters.
    if (!(error instanceof ReconciliationError)) throw error;
    return {method, status: 'unavailable', reason: error.message};
  }
}
