import assert from "node:assert/strict";
import test from "node:test";
import {mkdtemp, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {Pool} from "pg";
import {randomUUID} from "node:crypto";
import type {JsonObject} from "../../loopx/control_plane/effect_program.ts";
import {FileAuthorityStore} from "../../loopx/control_plane/coordination/file_authority_store.ts";
import {SqliteAuthorityStore} from "../../loopx/control_plane/coordination/sqlite_authority_store.ts";
import {PostgreSqlAuthorityStore, installPostgreSqlAuthorityStoreSchema} from "../../loopx/control_plane/coordination/postgresql_authority_store.ts";
import {refineGoalOutcome} from "../../loopx/control_plane/goals/outcome_requirements.ts";
import {inspectGoalAcceptance, refineGoalAcceptanceOutcome} from "../../loopx/control_plane/goals/acceptance_authority.ts";
import {authorityProjectionFixture} from "./authority_projection_fixture.ts";

const goal = "outcome-capacity";
const bytes = (value: unknown) => Buffer.byteLength(JSON.stringify(value), "utf8");
function crowded() {
  const state = {schema_version: "loopx_goal_outcomes_v0", goal_id: goal, goal_ref: null, revision: 1,
    outcomes: Array.from({length: 20}, (_, i) => ({id: `outcome-${i}`, owner_agent_id: "author", objective: `Deliver result ${i}`,
      revision: 1, requirements: Array.from({length: 5}, (_, r) => ({id: `r${r}`, description: `Retain requirement ${r}`})),
      todo_ids: [], sources: [{ref: `origin-${i}`, summary: `Owner requested result ${i}`}]}))};
  for (let i = 0; bytes(state) < 130400; i++) {
    state.outcomes[i % 20].sources.push({ref: `source-${i}`, summary: `Retained origin ${i}: ${"x".repeat(480)}`});
  }
  // Leave less room than even one complete review, while keeping the legacy
  // declaration valid and every source's independently bounded original text.
  const source = {ref: "boundary", summary: "x"};
  state.outcomes[0].sources.push(source);
  const available = 131000 - bytes(state);
  assert.ok(available >= 0 && available < 512);
  source.summary += "x".repeat(available);
  assert.equal(bytes(state), 131000);
  return authorityProjectionFixture(goal, [], [], "native", {goal_outcomes: state});
}
const review = {outcome_id: "outcome-19", review: Array.from({length: 5}, (_, i) => ({id: `r${i}`,
  conclusion: "uncertain", evidence_refs: ["artifact:current-check"], note: "Independent acceptance is still pending."}))};

test("a full retained declaration can receive a complete review without losing origins", () => {
  const head = crowded(), original = structuredClone(head);
  const state = refineGoalOutcome(head, goal, null, "author", review);
  assert.ok(bytes(state) > 131072, "reproduces the previous combined-cap rejection");
  assert.ok(bytes(state) <= 262144, "declarations and reviews remain bounded together");
  const before = (original.goal_outcomes as JsonObject).outcomes as JsonObject[];
  for (const item of state.outcomes) {
    const prior = before.find(row => row.id === item.id)!;
    for (const field of ["objective", "owner_agent_id", "requirements", "todo_ids", "sources"]) assert.deepEqual(item[field], prior[field]);
  }
  assert.deepEqual(state.outcomes.find(o => o.id === review.outcome_id)!.review!.items, review.review);
  assert.deepEqual(head, original, "pure refinement never mutates its input");
  assert.throws(() => refineGoalOutcome({...head, goal_outcomes: state}, goal, null, "author", {
    outcome_id: "outcome-0", source: {ref: "overflow", summary: "x".repeat(512)},
  }), /declaration capacity exceeded/, "review allowance cannot expand declaration capacity");
});

test("review capacity measures UTF-8 bytes across all retained reviews", () => {
  let head = authorityProjectionFixture(goal, [], [], "native");
  const fullReview = Array.from({length: 32}, (_, i) => ({id: `r${i}`, conclusion: "uncertain", evidence_refs: [], note: "界".repeat(512)}));
  for (let i = 0; i < 3; i++) {
    head = {...head, goal_outcomes: refineGoalOutcome(head, goal, null, "author", {
      outcome_id: `outcome-${i}`, owner_agent_id: "author", objective: `Deliver result ${i}`,
      requirements: fullReview.map(({id}) => ({id, description: `Keep ${id}`})), source: {ref: `origin-${i}`, summary: "Original request"},
    })};
  }
  for (let i = 0; i < 2; i++) head = {...head, goal_outcomes: refineGoalOutcome(head, goal, null, "author", {outcome_id: `outcome-${i}`, review: fullReview})};
  const before = structuredClone(head);
  assert.throws(() => refineGoalOutcome(head, goal, null, "author", {outcome_id: "outcome-2", review: fullReview}), /review capacity exceeded/);
  assert.deepEqual(head, before);
  // Replacing current evidence retains the original declarations and journal
  // semantics; the current-review budget is not an append-only history budget.
  const small = fullReview.map(row => ({...row, note: "Uncertain"}));
  head = {...head, goal_outcomes: refineGoalOutcome(head, goal, null, "author", {outcome_id: "outcome-0", review: small})};
  assert.equal(refineGoalOutcome(head, goal, null, "author", {outcome_id: "outcome-2", review: fullReview}).outcomes.length, 3);
});

for (const provider of ["file", "sqlite", "postgresql"] as const) test(`${provider}: crowded review survives restart and replay; overflow is atomic`,
  {skip: provider === "postgresql" && !process.env.LOOPX_TEST_POSTGRES_URL}, async t => {
  const root = await mkdtemp(join(tmpdir(), "outcome-capacity-")); t.after(() => rm(root, {recursive: true, force: true}));
  const pool = provider === "postgresql" ? new Pool({connectionString: process.env.LOOPX_TEST_POSTGRES_URL, max: 2}) : null;
  if (pool) t.after(() => pool.end());
  const database = pool ? {connect: async () => {
    const client = await pool.connect();
    return {query: async (sql: string, values?: readonly unknown[]) => client.query(sql, values ? [...values] : undefined),
      release: () => client.release()};
  }} : null;
  if (database) await installPostgreSqlAuthorityStoreSchema(database, `postgresql:${"b".repeat(32)}`);
  const scope = {tenant_id: `outcome-capacity-${randomUUID()}`, goal_id: goal};
  const open = () => database ? new PostgreSqlAuthorityStore(database, scope)
    : provider === "file" ? new FileAuthorityStore(root, goal) : new SqliteAuthorityStore(root, goal);
  const store = open(), head = crowded();
  await store.commitAuthority({operation_id: "seed", expected_provider_revision: null, next_projection: head, events: [], receipts: []});
  const prior = await inspectGoalAcceptance(store, goal);
  const request = {goal_id: goal, actor_agent_id: "author", operation_id: "review", expected_provider_revision: prior.provider_revision, refinement: review};
  const preview = await refineGoalAcceptanceOutcome(store, {...request, dry_run: true});
  assert.equal(preview.status, "planned");
  assert.deepEqual(await inspectGoalAcceptance(store, goal), prior);
  assert.equal((await refineGoalAcceptanceOutcome(store, request)).status, "applied");
  const after = await inspectGoalAcceptance(open(), goal);
  const outcomes = (after.goal_acceptance_contract as JsonObject).outcome_requirements as JsonObject;
  const rows = outcomes.outcomes as JsonObject[];
  assert.equal(rows.length, 20);
  const current = rows.find(row => row.id === review.outcome_id)!;
  assert.ok((current.requirements as JsonObject[]).every(r => r.status === "unverified" && r.planning_satisfied === false));
  assert.equal((await refineGoalAcceptanceOutcome(open(), request)).status, "replayed");
  assert.deepEqual(await inspectGoalAcceptance(open(), goal), after);
  assert.equal((await refineGoalAcceptanceOutcome(store, {...request, operation_id: "stale"})).status, "conflict");
  await assert.rejects(() => refineGoalAcceptanceOutcome(store, {...request, operation_id: "overflow", expected_provider_revision: after.provider_revision,
    refinement: {outcome_id: "outcome-0", source: {ref: "overflow", summary: "x".repeat(512)}}}), /declaration capacity exceeded/);
  assert.deepEqual(await inspectGoalAcceptance(open(), goal), after);
  const loaded = await open().loadAuthority(); assert.equal(loaded.status, "loaded");
  if (loaded.status === "loaded") {
    const original = (head.goal_outcomes as JsonObject).outcomes as JsonObject[];
    for (const row of (loaded.head.goal_outcomes as JsonObject).outcomes as JsonObject[]) {
      assert.deepEqual(row.sources, original.find(o => o.id === row.id)!.sources);
    }
  }
});
