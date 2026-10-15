import assert from "node:assert/strict";
import test from "node:test";

import { deriveGoalSuggestions, goalSuggestionLimit } from "./goal-suggestions.ts";

const classes = (overrides = {}) => ({ running_observed: 0, needs_you: 0, waiting_dependency: 0, open: 0, blocked: 0, deferred: 0, done: 0, ...overrides });
const digest = ({ activation = "active", open = 0, done = 0, blocked = 0, blockedIds = [], waiting = 0, oldest = null, needsYouUnavailable = false } = {}) => ({
  lifecycle: { activation, finishingTurn: false },
  work: { open, done, total: open + done, classes: classes({ open, blocked, done }), rows: [], groups: [],
    rail: { needsYou: [], open: [], blocked: blockedIds, done: [] }, coverage: "complete", listedOpen: open, projectedOpen: open },
  needsYou: needsYouUnavailable ? { availability: "unavailable" } : { availability: "ok", blocking: waiting, optional: 0, coverage: "complete", listed: waiting, oldestWaitingSince: oldest },
});
const todos = [{ todoId: "t1", text: "Backfill March exports" }, { todoId: "t2", text: " Reconcile totals " }, { todoId: "t3", text: "Third" }];

test("a stopped Goal invites nothing", () => {
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ activation: "stopped", open: 3, blocked: 1, waiting: 2 }), todos }), []);
});

test("decisions waiting on the owner come first and carry their count and age", () => {
  const [first] = deriveGoalSuggestions({ digest: digest({ open: 4, blocked: 1, blockedIds: ["t1"], waiting: 2, oldest: "2026-10-15T08:00:00Z" }), todos });
  assert.deepEqual(first, { kind: "open_decisions", count: 2, oldestWaitingSince: "2026-10-15T08:00:00Z" });
});

test("blocked work names at most two real task titles from the rail", () => {
  const [blocked] = deriveGoalSuggestions({ digest: digest({ open: 3, blocked: 3, blockedIds: ["t2", "missing", "t1", "t3"] }), todos });
  assert.deepEqual(blocked, { kind: "explain_blocked", count: 3, titles: ["Reconcile totals", "Backfill March exports"] });
});

test("a failing acceptance criterion is cited by its own description", () => {
  const [failing] = deriveGoalSuggestions({ digest: digest({ open: 1 }), todos, criteria: [
    { description: "Totals reconcile", state: "accepted" }, { description: "Backfill matches CSV", state: "failed" }, { description: "Runbook approved", state: "failed" },
  ] });
  assert.deepEqual(failing, { kind: "explain_failed_criterion", criterion: "Backfill matches CSV", failedCount: 2 });
});

test("idle requires an observed idle executor, open work, and nothing waiting on the owner", () => {
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 2 }), todos, execution: { kind: "idle" } }), [{ kind: "continue_idle", open: 2 }]);
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 2 }), todos, execution: { kind: "unknown" } }), [], "unknown is not idle");
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 2 }), todos, execution: { kind: "running" } }), []);
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 2, waiting: 1 }), todos, execution: { kind: "idle" } }).map((row) => row.kind), ["open_decisions"], "the owner is the blocker, not idleness");
});

test("a finished Goal points at its results only when nothing waits or blocks", () => {
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 0, done: 5 }), todos }), [{ kind: "review_results", done: 5 }]);
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 0, done: 5, blocked: 1, blockedIds: ["t1"] }), todos }).map((row) => row.kind), ["explain_blocked"]);
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 0, done: 0 }), todos }), [], "an empty Goal suggests nothing");
});

test("needs-you unavailable is not zero and never suggests decisions", () => {
  assert.deepEqual(deriveGoalSuggestions({ digest: digest({ open: 1, needsYouUnavailable: true }), todos, execution: { kind: "idle" } }), [{ kind: "continue_idle", open: 1 }]);
});

test("at most three suggestions, in owner priority order", () => {
  const rows = deriveGoalSuggestions({ digest: digest({ open: 2, blocked: 1, blockedIds: ["t1"], waiting: 1 }), todos, execution: { kind: "idle" },
    criteria: [{ description: "X", state: "failed" }] });
  assert.equal(rows.length, goalSuggestionLimit);
  assert.deepEqual(rows.map((row) => row.kind), ["open_decisions", "explain_blocked", "explain_failed_criterion"]);
});
