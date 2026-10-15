import assert from "node:assert/strict";
import test from "node:test";

import { buildSeenMarker, compareSeenMarker, readSeenMarker, seenMarkerIdLimit, seenMarkerStorageKey, writeSeenMarker } from "./since-you-looked.ts";

const input = (overrides = {}) => ({ observedAt: "2026-10-15T08:00:00Z", counts: { open: 5, blocked: 1, done: 20 }, decisionIds: ["d1"], doneTodoIds: ["a", "b"], blockedTodoIds: ["x"], resultIds: ["r1"], ...overrides });

test("a marker keeps typed counts and ids only, bounded", () => {
  const marker = buildSeenMarker(input({ doneTodoIds: Array.from({ length: seenMarkerIdLimit + 50 }, (_, i) => `t${i}`) }));
  assert.equal(marker.schema, "goal_seen_marker_v0");
  assert.equal(marker.doneTodoIds.length, seenMarkerIdLimit, "done ids are bounded to the newest");
  assert.equal(marker.doneTodoIds[0], "t50");
  assert.deepEqual(Object.keys(marker).sort(), ["counts", "decisionIds", "doneTodoIds", "observedAt", "resultIds", "schema"], "no titles, text or cost");
});

test("a no-change pair stays silent", () => {
  const marker = buildSeenMarker(input());
  const delta = compareSeenMarker(marker, input({ observedAt: "2026-10-15T09:00:00Z" }));
  assert.equal(delta.material, false);
  assert.deepEqual([delta.newlyDone, delta.newDecisions, delta.newlyBlocked, delta.resultsReturned], [0, 0, 0, 0]);
  assert.equal(delta.since, "2026-10-15T08:00:00Z");
});

test("known work, decision, blocked and result changes are counted since the marker", () => {
  const marker = buildSeenMarker(input());
  const delta = compareSeenMarker(marker, input({ counts: { open: 4, blocked: 2, done: 22 }, decisionIds: ["d1", "d2"], doneTodoIds: ["a", "b", "c", "d"], resultIds: ["r1", "r2"] }));
  assert.deepEqual([delta.newlyDone, delta.newDecisions, delta.newlyBlocked, delta.resultsReturned], [2, 1, 1, 1]);
  assert.equal(delta.material, true);
});

test("a shrinking queue or a resolved decision is not reported as new", () => {
  const marker = buildSeenMarker(input({ decisionIds: ["d1", "d2"], counts: { open: 5, blocked: 3, done: 20 } }));
  const delta = compareSeenMarker(marker, input({ decisionIds: [], counts: { open: 5, blocked: 1, done: 20 } }));
  assert.equal(delta.material, false);
});

test("a trimmed marker cannot inflate newly done beyond the done-count growth", () => {
  const many = Array.from({ length: seenMarkerIdLimit + 10 }, (_, i) => `t${i}`);
  const marker = buildSeenMarker(input({ doneTodoIds: many, counts: { open: 5, blocked: 0, done: many.length } }));
  const delta = compareSeenMarker(marker, input({ doneTodoIds: [...many, "new"], counts: { open: 4, blocked: 0, done: many.length + 1 } }));
  assert.equal(delta.newlyDone, 1, "the ten ids trimmed from the marker are old work, not new");
});

test("without a projected done count the ids alone decide", () => {
  const marker = buildSeenMarker(input({ counts: { open: 5, blocked: 0, done: null } }));
  const delta = compareSeenMarker(marker, input({ counts: { open: 5, blocked: 0, done: null }, doneTodoIds: ["a", "b", "c"] }));
  assert.equal(delta.newlyDone, 1);
});

test("storage round-trips per source and Goal and tolerates garbage", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => { store.set(k, v); } };
  const key = seenMarkerStorageKey("/status.json", "g1");
  assert.notEqual(key, seenMarkerStorageKey("http://remote/status.json", "g1"), "sources keep separate markers");
  const marker = buildSeenMarker(input());
  assert.equal(writeSeenMarker(storage, key, marker), true);
  assert.deepEqual(readSeenMarker(storage, key), marker);
  store.set(key, "{not json");
  assert.equal(readSeenMarker(storage, key), null);
  store.set(key, JSON.stringify({ schema: "other" }));
  assert.equal(readSeenMarker(storage, key), null);
  const throwing = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(readSeenMarker(throwing, key), null);
  assert.equal(writeSeenMarker(throwing, key, marker), false);
});
