# Registered source treatment at the integrated main baseline

Review baseline: `43173c0b8c8761abee4cdddc665f0f0f20f194f7` (2026-10-12).
This refreshes #4447 Stage 2a/2b/2c without changing its scope, scanner enrollment,
budgets or runtime behavior. The [staged scope revision](https://github.com/loopx-project/loopx/pull/4789)
is merged; delivery acceptance and the two named unresolved meanings below are
still open. **26 rows inventoried is not 26 producer proofs or tracker closure.**

The registry still contains 26 entries, including `task_lease_lifecycle_operation`
in place of retired `lease_action`. F1/F2 remain **6/26**: five kernel entries
and the settlement-binding witness. The other twenty cross-runtime entries do
not gain F1/F2 credit from this document or from decoder tests. All owner symbols
and exact admitted values remain in `loopx/semantics/vocabulary_v0.json`; paths
in the second column below are relative to `loopx/control_plane/`.

A runtime witness executes the shipped decision from causal facts. An injected
value witnesses a caller-input/decoder boundary only. Mixed rows retain both
obligations. Legacy acceptance needs a retained reader and an exit condition;
no row is relabeled local-only to avoid a crossing it actually has. These are
bounded source treatments, not whole-program reachability, data-flow or F6 proof.

## Source and compatibility inventory

| Registered entry | Owner / slot | Executed source treatment | Compatibility and remaining boundary |
| --- | --- | --- | --- |
| turn_result_kind | `turn_driver/executor.py`, `transaction.py::_result_kind` → generated result kind | Internal result selection plus caller/Host result input. Driver/executor/transaction tests exercise results and malformed input; the registered fixed decoder witnesses every admitted value. | Host input acceptance is not proof a live Host emitted it; journal/replay readers remain. |
| turn_route | `turn_driver/driver.py`, `loop_controller.py` → plan/envelope route | Internal route selection. Driver and loop-controller tests exercise host-ready, gated, repair, wait and invalid routes; generated route projection is checked. | Keep the three Turn vocabularies and explicit projection; a route is not a stored receipt. |
| loop_disposition | `turn_driver/loop_controller.py::decide_loop_disposition` → disposition | Internal decision from current route/result/iteration facts; loop-controller table and negative/retry tests execute the owner. | Generated controller rules remain distinct from route and result; no spelling-only merge. |
| agent_scope_frontier_action | `agents/agent_scope.py` → frontier action | Internal classification of candidates, dependencies and handoff; agent-scope frontier tests execute exhausted/wait/reassignment/successor branches. | Generated TS binding is a consumer, not another producer; no claim of whole-goal completion from an exhausted lane. |
| effective_action | `quota/decision_summary.py` and registered overlays → final action | Internal decision/overlay output. Quota decision tests execute current paths; the fixed producer scan still has explicit unresolved sites. | The root decision/frontier union and nested replay slots stay distinct. Source treatment does not eliminate scanner unknowns or prove every branch reachable. |
| settlement_binding_kind | `effect_program.ts::settlementIdentity` → binding_kind | Internal normalization of supplied identity. Existing settlement-binding witness executes Todo, autonomous-replan and unbound cases plus contradictions. | Unbound is not a permit to spend; exact identity remains the existing receipt owner’s responsibility. |
| task_lease_lifecycle_operation | `work_items/task_lease_lifecycle_request.ts` → operation | Caller-selected native input; lifecycle tests execute renew/transfer/release, terminal_verify/holder_verify/fence_close, bad input, CAS and retry. | Replaces retired private Python lease_action, not lease behavior. Native persisted fence receipts and omitted legacy optional fields remain readable; no F1/F2 enrollment. |
| settlement_step_kind | `effect_program.ts`, `turn_driver/settlement.ts` → receipts[].step_kind | Mixed internal receipt construction and external envelope input. Stage 2a executes all four steps on committed replay without callbacks, and rejects malformed step input. | Ordered prefixes, effect identity and historical receipts remain; injected steps prove decoding only. |
| settlement_failure_kind | `effect_program.ts`, `quota/settlement_readback.ts`, native lease owners → failure kind | Mixed internal failures and accepted envelope input. Stage 2a now includes all 12 wire values, real unbound-guard readback and native permission denial. | `cancelled` remains the named unresolved source-purpose item below. Lease summaries use failure.step, while Effect envelopes use failure.step_kind; no fabricated wire conversion. |
| receipt_bound_monitor_phase | `quota/settlement_readback.ts` → `settlement_phase.ts` → monitor_phase | Internal derivation from exact monitor commit; Stage 2a executes poll_due/settled, wrong identity and legacy monitor effect id. | settlement_pending is retained consumer compatibility only; real monitor builder does not emit it. Remove only after historical work-lane consumers migrate. |
| receipt_bound_replay_phase | `quota/settlement_readback.ts` → `settlement_phase.ts` → replay_phase | Internal open/pending/settled from isolated receipt files and completion/writeback/spend prefixes; repeated reads and identity negatives execute the bridge. | Terminal-to-replay adapter and original binding stay. Phase projection is not proof all durable writers committed correctly. |
| delivery_workspace_kind | `agents/workspace_guard.py::capture_delivery_workspace` → TS snapshot | Mixed filesystem/Git observation and snapshot input. Real primary/linked/local workspace tests plus TS normalization cover three kinds, contradictions and invalid origins. | Keep v0 Git snapshot normalization; do not turn missing/failed Git evidence into a local-goal grant. |
| delivery_workspace_identity_kind | `agents/workspace_guard.py` → `agents/delivery_workspace.ts` → identity_kind | Mixed observed git_repository/local_goal and validated snapshot input. The same real Git/local tests verify identity, ownership and peer isolation. | Local Goal identity cannot satisfy a peer-independent Git requirement; v0 Git snapshots retain their own migration path. |
| delivery_workspace_requirement | `quota/settlement_workspace_causality.ts` → requirement | Internal required/not_required/unknown from explicit work contract. Causality tests execute repository writes, non-delivery, missing metadata and event readback. | Unknown requires repair. Legacy no-workspace settlement exception needs both exact committed validation/writeback receipts; partial or wrong-Todo evidence fails. |
| todo_completion_continuation | `todos/completion_state.ts::selectTodoCompletionState` → continuation | Internal active_goal/successor/no_followup selected from intent and Todo facts, plus persisted metadata input; whole-owner and malformed-authority tests execute it. | Contradictory successor/no-followup intent rejects; retained metadata normalization remains while retired scalar RPC rejects. |
| todo_completion_recovery | `todos/completion_state.ts` → recovery | Internal same_turn_terminal_closeout/lifecycle_reentry_terminal_closeout from completed Todo, closure intent and identity source; pinned and explicit lifecycle cases execute both. | Recovery does not rewrite the original completion identity or create a successor; nullable non-recovery is distinct. |
| todo_decision_scope_kind | `todos/decision_metadata.ts::normalizeTodoDecisionScope` → kind | Author-declared input, not inferred by a producer. Explicit seven-kind input witnesses, malformed membership, CLI mutation and exact-kind dominance tests execute readers. | `other` authoring purpose remains unresolved below. Input acceptance does not grant authority; legacy standing-scope codec remains. |
| todo_decision_scope_granularity | `todos/decision_metadata.ts` → granularity; `decision_scope.ts` → dominance | Author-declared action/lane/goal/project/global input; explicit domain and unknown/null/numeric tests plus CLI/dominance cases execute consumers. | Broad scope cannot cross kinds or override exact target/recipient conflict; do not infer missing scope from a bounded view. |
| goal_amendment_class | `goals/goal_amendment_proposal.ts` → proposal.amendment_class | Author-declared four classes; RFC classification table, all-class/unknown-class tests and real submit/list CLI provide input and journal evidence. | Admission is retained proposal evidence with canonical_effect=none, not amendment commit or delegated protected authority. |
| goal_amendment_proposal_admission | `goals/goal_amendment_proposal.ts::admissionOutcome` → admission | Internal admitted/needs_rebase from current basis, sequence and digest; equal/stale/future/canonical/Markdown tests execute real TS owner and CLI journal. | Retain stale proposals for rebase; reject fabricated future history. Admitted never means accepted shared change. |
| goal_amendment_proposal_admission_fact | same admission owner → admission_facts[] | Internal four fact codes for sequence behind, digest mismatch, unverifiable basis and superseded basis; combined-condition and basis-transition cases execute branches. | Mixed facts remain together; Markdown or canonical zero sequence is not fabricated event-log freshness. No change to proposal schema or commit authority. |
| scheduler_cadence_transition | `scheduler/state_transition_rules.ts` → cadence transition | Internal six transitions from identity, elapsed interval, acknowledgement and failure facts; Python decision table and TS coarse-transition tests execute the shared owner. | Keep pinned old-Python characterization and state readback; cadence is not permission to execute or spend. |
| scheduler_host_transition | `scheduler/state_transition_rules.ts` → host transition | Internal apply_required/host_match_ack_required/recorded_failure_suppressed/settled; explicit table/negative tests exercise current observations and recorded failures. | Projection is not an actual host update. Current-host ACK must pass #6259’s separate readback gate; no host-success claim from these fixtures. |
| handoff_mode | `coordination/handoff_mode_vocabulary.ts`, authority/mode-plan readers → mode | Mixed configured input and retained legacy/default read. Real show/set CLI, invalid/frontmatter, quiescence, lease and replay tests exercise source and readers. | New configuration targets are soft_claim/hard_lease; legacy remains readable for upgrade/receipts. Mode parsing is not lease authority. |
| delivery_outcome | `work_items/delivery_outcome.ts`, monitor/Host/replan producers → outcome | Mixed caller declaration and machine selection: monitor/Host paths produce surface_only/progress, replan can downgrade to outcome_gap; primary_goal_outcome is an author claim. History, native monitor, executor, replan and diagnostic tests exercise these boundaries. | Decoder/claim validation does not independently verify a primary outcome. Historical contradictory claims are diagnosed, not rewritten as success. |
| delivery_continuity_preemption | `quota/should_run_packet.py::_delivery_preemptions_for_route` → `turn_driver/delivery_continuity.ts` | Internal current guard facts plus typed input: receipt, blocking lane, replan, repair and denied delivery. Continuity route/selection tests execute preemption and subsequent reselection. | Sticky delivery cannot override these facts. Same strings in a different qualifier are not automatically this vocabulary; no old receipt retargeting. |

## Two unresolved meanings requiring owner disposition

- **`settlement_failure_kind.cancelled` — Effect/settlement owner.** The public
  `SettlementResult.failed(...).bind(...)` path admits and short-circuits it, but
  searches of the settlement owners, enum/member uses and callers find no
  internal cancellation producer. Tokens in chat/Host/usage cancellation belong
  to different vocabularies. Decoder acceptance establishes its wire treatment,
  not who may create it or when. The existing unresolved value note is retained.
  Closure requires either an identified cancellation producer/contract with a
  real witness, or an explicitly reviewed reserved/compatibility-only scope and
  retirement condition. This change requests neither an invented producer nor
  automatic acceptance of that exception.
- **`todo_decision_scope_kind.other` — Todo decision-scope owner.** The real parser
  accepts it and exact-kind matching prevents it covering named kinds. No fallback
  converts unknown input to `other`; malformed input rejects. The existing public
  vocabulary reference lists it without an authoring criterion, and the six named
  catalogue authorities do not supply one. Its meaning note remains unresolved.
  Closure requires an explicit authoring contract plus examples, or a reviewed
  compatibility-only retention/migration decision. Membership tests cannot choose
  that product meaning on behalf of the owner.

These are named outstanding decisions, **not approved exceptions**. They keep
Stage 2/3 open; neither blanket source labels nor green tests settle them.

## Evidence and reproduction

Use the intended source checkout, `uv sync --extra test`, qualified Node 22.22.3,
and `npm ci --ignore-scripts --no-audit --no-fund`. Python imports must resolve to
that checkout. Evidence groups are existing tests, not a new acceptance database:

- Foundation: `tests/test_loopx_turn_{driver,executor,transaction}.py`,
  `tests/test_loop_turn_loop_controller.py`,
  `tests/control_plane/test_agent_scope_frontier_contract.py`,
  `tests/control_plane/test_quota_run_decision.py`, and
  `tests/architecture/test_semantic_settlement_binding_witness.py`.
- 2a: `tests/architecture/test_settlement_receipt_source_boundaries.py` and native
  `turn_settlement`, `quota_settlement_readback`, `task_lease_acquire` and
  `task_lease_lifecycle` TS suites. The thin source witness adds no decision rule.
  Its new unbound-guard case executes real synthetic-file readback through TS and
  Python; its excluded-owner case executes real native lease rejection with no
  lease write. The explicit external-failure cases now cover twelve values;
  registry comparison only prevents an added value silently missing its witness.
- 2b: Python `test_delivery_workspace.py`, `test_workspace_git_fact_reads.py`,
  `test_delivery_workspace_causality.py`, `test_task_lease_cli_native.py`,
  `test_todo_decision_scope_{cli_validation,consistency}.py`,
  `test_todo_completion_state_runtime.py`; TS `delivery_workspace`,
  `settlement_workspace_causality`, `todo_completion_state`, `decision_metadata`
  and `decision_scope`. Input cases for every scope kind/granularity are distinct
  from runtime classification and retain the unresolved `other` purpose.
- 2c: Python `test_goal_amendment_proposal{,_cli}.py`,
  `test_scheduler_state_{transition_rules,runtime_integration}.py`,
  `test_goal_handoff_mode_cli.py`, `test_handoff_mode_source.py`,
  `test_delivery_continuity_{selection,runtime}.py`, `test_native_monitor_poll.py`,
  `test_replan_writeback_projection.py`, `test_refresh_state_replan_gate.py`,
  `test_final_outcome_diagnostics.py`; TS `goal_amendment_proposal`,
  `scheduler_state_transition_rules`, `handoff_mode_plan`, `delivery_continuity`
  and `delivery_history`.
- Historical/new-output boundary: Python `test_protocol_packet_history.py` and
  `test_protocol_packet_retirement_cli.py`; generated semantic/Turn bindings
  checked with their existing `--check` commands and full drift smoke.

Run Python files with `uv run --extra test python -m pytest -q ...`; TS suite
names above mean `tests/control_plane_ts/<name>.test.ts`, run with
`node --no-warnings --experimental-sqlite --experimental-strip-types --test ...`.
Do not substitute enum iteration for producer witnesses. Expected observations
come from the accepted contracts and causal cases, not an echo of owner output.

At this source baseline plus the focused witness additions: Stage 2a **66 passed**;
existing Python domain groups **564 passed**, additional real-Git/monitor/replan/
lease groups **82 passed**; native TS groups **421 passed**, no skips. TypeScript
typecheck, focused Ruff, both generators and full semantic drift pass. These are
source/isolated-backend results, not installed or live-model acceptance.
The existing semantic architecture/value-note suite adds **706 passed**; docs
governance and premerge pass. The generated RFC status index reflects the new
ledger entry; it makes no delivery-maturity claim.
The drift readback remains F1/F2 6/26, F3 0/26, F4 4/4, F5 1/1, F6 0/0;
45 producer sites are unresolved, including 17 that cannot supply producer
witnesses. No ceiling or source boundary was relaxed.

Known integration limit, reused from an independently reproduced run on this
same immutable main baseline: three `test_quota_settlement_cli.py` cases fail at
scheduler ACK (standard settlement and both Todo-less replan variants). They
provide no current host observation required by #6259, so the owner returns
`rrule_mismatch` without writing scheduler state. They are not in the passing
source groups above and were not rerun for this documentation batch. This known
full-CLI-suite gap remains open; no rule or assertion is weakened to hide it.


## Integrated state and closure boundary

The main baseline includes #4772/#4777 reporting corrections, #4775 live
composition, #4783 settled replay, #4788 rejected selection, #4786 inbox
composition, overlapping correctness #4764, binding witness #4747 and 2a #4795.
#4794 stopped new `protocol_action_packet` writes while retaining historical
reading/signature projection. The other five legacy fields remain intentionally
visible; all-field retirement is not a closure condition. #5317 supplies the
separate #4743 development-time advisory, so the old “never built/no AGENTS
instruction” claim is obsolete. Advisory findings do not become blocking proof.

The later typed-failure repair #6251 and canonical-selection repair #6268 are open
at this measurement and are not folded into this baseline’s results. #6260 is
merged. They do not expand #4447’s accepted closing scope. Full source disposition,
maintainer acceptance and one final integrated readback still precede closure;
installed frontend/Lark/live-model and general Goal/team qualification are not
claimed by this source-evidence batch. No production provider or persistence
format is changed; raw runtime logs and local Goal state stay outside the repo.
