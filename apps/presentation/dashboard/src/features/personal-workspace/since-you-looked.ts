/**
 * "Since you looked": what changed in a Goal between two of the owner's
 * visits, per RFC goal-workspace-surface-v0 §5.7.
 *
 * The browser keeps one marker per (status source, Goal) in local storage:
 * typed counts, decision ids, a bounded set of done Todo and result ids, and
 * the observation time. No titles, content or cost ever enter it, and nothing
 * is written to the service. A delta is reported only when it is material;
 * cost is omitted because the usage projection cannot qualify the interval.
 * The marker advances when the owner marks it seen or leaves the Goal after
 * the line was shown. This is not a notification channel.
 */

export const seenMarkerSchema = "goal_seen_marker_v0";
export const seenMarkerIdLimit = 200;

export type SeenMarker = {
  schema: typeof seenMarkerSchema;
  observedAt: string;
  counts: { open: number; blocked: number; done: number | null };
  decisionIds: string[];
  doneTodoIds: string[];
  resultIds: string[];
};

export type SeenMarkerInput = {
  observedAt: string;
  counts: { open: number; blocked: number; done: number | null };
  decisionIds: readonly string[];
  doneTodoIds: readonly string[];
  blockedTodoIds: readonly string[];
  resultIds: readonly string[];
};

export type SinceYouLookedDelta = {
  since: string;
  newlyDone: number;
  newDecisions: number;
  newlyBlocked: number;
  resultsReturned: number;
  material: boolean;
};

function bounded(ids: readonly string[]): string[] {
  return [...new Set(ids)].slice(-seenMarkerIdLimit);
}

export function buildSeenMarker(input: SeenMarkerInput): SeenMarker {
  return {
    schema: seenMarkerSchema,
    observedAt: input.observedAt,
    counts: { open: input.counts.open, blocked: input.counts.blocked, done: input.counts.done },
    decisionIds: bounded(input.decisionIds),
    doneTodoIds: bounded(input.doneTodoIds),
    resultIds: bounded(input.resultIds),
  };
}

/**
 * Compare the current observation with the stored marker. Newly done work is
 * the done ids not in the marker, bounded by the growth of the done count
 * when the owner projects one, so a trimmed marker never inflates it. New
 * decisions and results are ids not seen before. Newly blocked work is the
 * growth of the blocked count. A shrinking queue is not a change to report.
 */
export function compareSeenMarker(previous: SeenMarker, current: SeenMarkerInput): SinceYouLookedDelta {
  const seenDone = new Set(previous.doneTodoIds);
  const seenDecisions = new Set(previous.decisionIds);
  const seenResults = new Set(previous.resultIds);
  const doneById = current.doneTodoIds.filter((id) => !seenDone.has(id)).length;
  const doneByCount = previous.counts.done !== null && current.counts.done !== null
    ? Math.max(0, current.counts.done - previous.counts.done) : doneById;
  const newlyDone = Math.min(doneById, doneByCount) || Math.max(0, doneByCount > 0 && doneById === 0 ? doneByCount : 0);
  const newDecisions = current.decisionIds.filter((id) => !seenDecisions.has(id)).length;
  const newlyBlocked = Math.max(0, current.counts.blocked - previous.counts.blocked);
  const resultsReturned = current.resultIds.filter((id) => !seenResults.has(id)).length;
  return {
    since: previous.observedAt,
    newlyDone, newDecisions, newlyBlocked, resultsReturned,
    material: newlyDone > 0 || newDecisions > 0 || newlyBlocked > 0 || resultsReturned > 0,
  };
}

export function seenMarkerStorageKey(statusSource: string, goalId: string): string {
  return `loopx-pw-seen:${statusSource}:${goalId}`;
}

export function readSeenMarker(storage: Pick<Storage, "getItem">, key: string): SeenMarker | null {
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<SeenMarker> | null;
    if (!value || value.schema !== seenMarkerSchema || typeof value.observedAt !== "string" || !value.counts) return null;
    return {
      schema: seenMarkerSchema, observedAt: value.observedAt,
      counts: { open: Number(value.counts.open ?? 0), blocked: Number(value.counts.blocked ?? 0), done: value.counts.done === null || value.counts.done === undefined ? null : Number(value.counts.done) },
      decisionIds: Array.isArray(value.decisionIds) ? value.decisionIds.filter((id): id is string => typeof id === "string") : [],
      doneTodoIds: Array.isArray(value.doneTodoIds) ? value.doneTodoIds.filter((id): id is string => typeof id === "string") : [],
      resultIds: Array.isArray(value.resultIds) ? value.resultIds.filter((id): id is string => typeof id === "string") : [],
    };
  } catch {
    return null;
  }
}

export function writeSeenMarker(storage: Pick<Storage, "setItem">, key: string, marker: SeenMarker): boolean {
  try {
    storage.setItem(key, JSON.stringify(marker));
    return true;
  } catch {
    return false;
  }
}
