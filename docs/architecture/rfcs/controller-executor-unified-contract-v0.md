# RFC: Controller / Executor Sessions and One Governed Work Contract (v0)

- **RFC status:** Accepted (design acceptance takes effect on merge)
- **Supersedes / closes:** none
- **Delivery maturity:** Proposal; no new runtime, schema or default is shipped by this document.
- **Authors / owners:** LoopX maintainers; control-plane and runtime owners
- **Created:** 2026-10-27
- **Last normative revision:** 2026-10-27
- **Implementation baseline:** `fe2b8dcbcb998647edb4bafb51932988bd7fdaa6`
- **Related contracts:** [Effect interpreter](agent-loop-effect-interpreter-v0.md), [Session execution modes](agent-session-execution-modes-v0.md), [Semantic handoff](capable-manager-semantic-handoff-v0.md), [Overall roadmap](loopx-overall-roadmap-v0.md)
- **Language mirror:** [中文版](controller-executor-unified-contract-v0.zh-CN.md)

## Document map and maintenance contract

The English and Chinese documents are semantic mirrors; a difference is a defect.

Section 4 records source facts at the named baseline. Sections 1–3 and 5–11
define the proposed decision and acceptance; section 12 records unresolved
choices. Before merge this is a review proposal. Merge accepts the design,
not implementation, installation, experiments or default promotion. Historical
evidence belongs in a dated ledger when an implementation first produces it.

## 1. Decision summary

1. Converge quota execution packets and TurnEnvelope into **one versioned
   governed work contract**: one schema, one semantic producer, one capture,
   one delivery/recovery mechanism and one settlement identity. Different hosts
   carry that same contract; permanent quota/Turn compatibility views are not
   the target. Existing domain owners still decide their own facts.
2. In the optional two-session profile, the **controller model session is the
   sole model-facing Core client**. It reads the contract, reasons about work,
   talks to the executor and submits explicit typed Core operations. Core owns
   legal transitions and receipts; the controller is not a second authority.
3. The executor receives a natural-language task conversation, original source
   material and ordinary host tools. It returns findings, artifacts, evidence
   and questions. It neither consumes a second Core packet view nor authors
   quota, Vision, lease or settlement fields. A small machine carrier records
   routing and causality outside the task prose.
4. Full-first delivery, exact differential context and automatic full recovery
   are capabilities of the single contract. Controller and executor sessions
   have independent continuity evidence; one cannot borrow the other's baseline.
5. Unification first qualifies the existing single-session path. Two-session
   execution remains opt-in until matched outcome and complete-cost evidence
   justifies adoption. This RFC launches no benchmark or privileged operation.

## 2. Problem and motivation

A task can enter through App heartbeat, an external worker or `loopx turn`, yet
its context and result obligations are presented differently. Shared decision
facts already exist, but callers still choose packet formats, reconstruct
prompts and adapt model-authored bookkeeping. Adding another controller-specific
packet would multiply these paths.

For example, an executor asked to repair a failing export needs the original
requirements, the failure, permitted workspace and independent acceptance. It
does not need to learn how to encode a Vision delta or debit a LoopX Turn.
Separating that work may reduce distraction and repeated protocol input, but
an extra controller can also lose constraints, add latency or over-coordinate.
These are hypotheses to test, not benefits established by session separation.

### Invariants

- Preserve complete accepted requirements, revisions, authority, unresolved
  reads and evidence provenance; a shorter prompt is not permission to omit them.
- Exactly one current control owner and one admitted executor attempt for the
  selected work. Dialogue, routing ACKs and model completion are not receipts.
- Notifications do not govern execution. A quiet notification result cannot
  cancel admitted work; a message cannot override a genuine stop or budget gate.
- A governed Turn is a bounded work/settlement unit, not a wake, model response
  or controller/executor exchange. Do not charge a new Turn for each message.
- Preserve original identity through retry, source correction and closeout;
  never settle an old result against a newly selected Todo.

## 3. Scope and non-goals

In scope: contract convergence, context delivery, role-specific session binding,
controller/executor communication, shared lifecycle reuse, host adapters,
benchmark adoption, retirement and observable product acceptance.

Non-goals: a new Goal store, workflow DSL, generic effect executor, permission
engine, scheduler, mandatory two-Agent team, automatic host switching or changes
to benchmark scoring. Peer teams retain existing delegation/acceptance contracts.
This proposal does not move business reasoning into deterministic Core rules.

## 4. Current-system contract

| Existing concept | Actual role / source | Consequence for the target |
| --- | --- | --- |
| Quota packet / TurnEnvelope | [`quota.py`](../../../loopx/cli_commands/quota.py) projects a decided payload through separate ordinary/envelope branches; [`turn_envelope.ts`](../../../loopx/control_plane/quota/turn_envelope.ts) supplies bounded sections and action binding | Migrate both sets of obligations into one schema, then retire both old output paths |
| Work context | [`interaction_contract.ts`](../../../loopx/control_plane/work_items/interaction_contract.ts) carries typed execution/context requirements | Extend the existing owner; do not create a controller decision engine |
| Thin heartbeat | [`task_body.py`](../../../loopx/control_plane/heartbeat/task_body.py) renders product entry instructions with format-dependent branches | Keep the bootstrap/host entry; converge its consumed contract |
| `loopx turn` | [`turn.py`](../../../loopx/cli_commands/turn.py), [`executor.py`](../../../loopx/control_plane/turn_driver/executor.py), [`settlement.py`](../../../loopx/control_plane/turn_driver/settlement.py) implement governed invocation and receipt-bound closeout | Reuse the lifecycle; a CLI entry is not another product runtime |
| Managed Codex | [`codex_agent_session.py`](../../../loopx/control_plane/turn_driver/codex_agent_session.py) and [`codex_sessions.py`](../../../loopx/control_plane/turn_driver/codex_sessions.py) implement native session execution/resume | Runtime adapter, not a competing control plane; current Agent-scoped storage lacks the proposed role distinction |
| Executor result | [`codex_cli.py`](../../../loopx/control_plane/turn_driver/codex_cli.py) asks for a schema-constrained result including delivery and Vision/progress fields | Move Core authoring responsibility to the controller in the two-session profile; preserve validation |
| External worker | [`external_scheduler_worker.py`](../../../scripts/external_scheduler_worker.py) owns outer wake/command transport | Preserve that ownership; remove duplicate semantic orchestration where demonstrated |
| Benchmark runner | [`worker.py`](../../../benchmark/runtime/worker.py) uses the product thin body for heartbeat and public Turn CLI for Turn mode; [`sessions.py`](../../../benchmark/runtime/sessions.py) reuses the native session adapter | Evaluation harness around product profiles, not a separate implementation target |
| Turn Loop Controller | [Stable protocol](../../reference/protocols/turn-loop-controller-v0.md) defines a pure disposition function | Keep it deterministic; it is not the proposed controller model session |

Execution mode (`managed_runtime` / `attached_host`), runtime provider, wake
source, single/two-session organization and evaluation arm are independent
axes. Not every combination is supported. Native/plain benchmark controls may
intentionally have no LoopX Core and must remain uncontaminated controls.

### C1 source audit: shared owners and the remaining split

The source already shares more than the output names suggest. `_emit_quota_result`
captures the complete decision **before** `_project_quota_cli_payload` chooses
ordinary CLI compaction or `buildTurnEnvelope`. The latter delegates to the
TypeScript owner; its Python module is a transport adapter. Both quota capture
and Turn journal capture call `write_decision_capture` in
[`decision_capture.py`](../../../loopx/control_plane/turn_driver/decision_capture.py).
Native context delivery and explicit host handoff also reuse that module and
the existing context-delivery owner. C1 must converge the remaining composition
and consumer assumptions, rather than introduce another capture service or
rewrite already shared delta/native-resume logic.

| Current source / obligation | Present envelope treatment | Required C1 disposition |
| --- | --- | --- |
| `interaction_contract.agent_channel.work_context` and pending required reads | `work_context` plus `required_reads`; identical inline material can be referenced | One complete requirement/evidence source with resolvable references; preserve pending reads and their completion conditions |
| Selected Todo, recommended action, action portfolio and planning horizon | `action`; reference relocation and text compaction occur in `turnActionProjection` | One selected work/action identity; preserve complete actionable clauses and distinguish summaries from executable instructions |
| `interaction_contract.cli_channel.settlement_plan` | Copied into `writeback.settlement_plan`, including original effect identity and conditional steps | Reuse the settlement owner unchanged; neither controller dialogue nor a new capture creates another debit identity |
| User/agent interaction channels, execution policy and task orchestration | Separate `user`, `execution_policy`, `boundary` and orchestration sections | Preserve notification versus execution obligations, authority and stop gates; do not derive them from prose |
| Replan packet, required reads and staged writeback | Dedicated replan projection and deferred writeback | Preserve fact/source access, policy-specific triggers and ordered mutations; no blanket activation of stride behavior |
| Scheduler context and execution ownership | Scheduler projection with caller execution context | Carry the actual host owner and ACK obligations; a common schema does not transfer scheduler authority |
| Complete saved decision, action signature and journal binding | Source hash, projected action hash and captured-decision reference are distinct | Preserve the distinction between semantic integrity, exact transport bytes and receipt identity; no hash substitution |

This is an owner-and-obligation map, **not an exhaustive field inventory or a
parity result**. Current projections have bounded text, allowlists and relocated
references. Matching their action signatures alone cannot prove preservation of
all source clauses or unknown fields. C1 implementation must enumerate those
fields and callers against its exact base/head; anything unclassified holds
cutover, rather than disappearing into an assumed compatibility view.

A synthetic probe of the named baseline demonstrates the limit: two long
`recommended_action` strings with identical prefixes but different tails produce
the same action-signature document and both report `matches=true`, while their
`source_decision_hash` values differ. An unregistered top-level source field has
the same distinction. Conversely, a complete registered settlement plan survives
projection, and changing its Turn identity changes the action signature. These
observations reject promoting the existing bounded envelope unchanged into the
complete contract. They do **not** establish a current authority-loss bug: the
recommendation is diagnostic, the unknown field is synthetic, and the complete
source commitment still distinguishes both inputs. No model benefit is measured.

## 5. Proposed architecture

### Ownership and one contract

```text
Core owners <-> unified governed work contract <-> controller session
                                                       |
                                      task / findings / artifacts
                                                       |
                                                 executor session
                                                       |
                                              scoped host tools

Host adapters enforce dispatch, session fences, interruption and transport.
Core owners validate operations and commit existing effect/settlement receipts.
```

Use the existing TypeScript interaction/work-context and effect owners. The
composition owner captures their current facts once; it does not reimplement
quota, replan, Todo or lease decisions. Python may collect sources and adapt
native transport. Host-specific execution ownership remains explicit in the
same contract, including delegated scheduler effects and their ACK obligations.

The schema name and exact field migration require the task C1 inventory below.
The following are required semantic groups, **not additional nested protocols**:

| Group | Preserved capabilities |
| --- | --- |
| Identity and current decision | Contract version, capture/revision, Goal/Agent/work/Turn binding, selected action, admission, claim/lease, scope, approvals, cancellation and stop conditions |
| Complete work context | Original intent and requirements, unresolved obligations, accepted evidence, current sources/revisions, required-read completion and authorized detail access |
| Context delivery | Full/delta encoding, exact base/target digests, consumer session/role/epoch and immutable capture recovery |
| Operations and closeout | Available typed operations, action binding/integrity, conditional ordering, validation and writeback/debit identity, scheduler and notification ownership |

There is one semantic instance and one schema across CLI, heartbeat, managed
Turn and evaluation. Full versus delta is an encoding choice for that instance;
pagination is a transport limit. Neither creates a quota schema and a Turn
schema. Native tool wrappers may carry provider-required envelopes without
renaming, omitting or independently deciding contract fields. Human UI read
models remain presentation sinks, not alternate executable contracts.

The composition boundary is **after current domain decisions and host-operation
binding, before immutable capture and context encoding**. All live writers use
that boundary. They must not first compact a quota packet into an envelope and
then label the result the complete unified contract. Required source material
may use authorized detail references, but those references, revisions and read
obligations must be complete and recoverable from that same semantic capture.

“One capture” means one immutable semantic observation for an invocation, not
one file for every purpose. Keep the complete canonical instance, encoded
full/delta/page artifacts and the Turn journal's binding distinguishable. Exact
file-byte digests protect transport; canonical hashes protect semantic content;
the existing effect identity protects once-only settlement. None substitutes
for another or grants current authority. Reserve an identity/location before
serialization when recovery references need it; do not require a document to
contain the digest of its own final bytes. Encoding, pagination, native resume
and recovery derive from the saved instance without another guard. A legitimate
new selection or authority check may produce a new capture; it must not rewrite
an earlier observation or silently rebind an outstanding result.

### Review freshness and recovery

A complete capture proves what was observed; it does not freeze write-time
validity. Keep semantic content identity, review relevance and settlement
identity distinct. A supporting outcome owned by another agent may still
constrain the shared Goal: owner labels alone cannot remove its acceptance or
requirement-status changes from the review basis. Narrow invalidation requires
an explicit dependency-scoping rule and tests for shared constraints, not a
role-name filter or an allowlist inferred from prose.

When the same admitted obligation rejects a stale review, its current typed
owner should return the complete current review basis and applicable control
instructions. The consumer reads and reassesses that basis, then retries the
original writeback with its original identities. Do not send it an unbound
write command or require another guard merely to retrieve facts already used
by the writer. A changed basis still rejects; returning context does not accept
a decision or authorize spending. This recovery belongs to the existing
composition/writeback boundary and must survive the C1 writer transition.
It is not a claim that cross-agent invalidation has been narrowed or that the
complete unified contract is delivered.

### Executor input and output

Choose **natural-language work exchange with runtime-owned metadata**, rather
than an executor-facing Core view or an untracked chat. The controller explains
the objective, relevant facts, boundaries and acceptance in task-appropriate
prose; it can steer, answer questions and revise a request. The host carries
opaque request/revision, attempt, session/generation, causal sequence and
artifact references using existing request/dispatch records. The model need
not reproduce those identifiers in prose. No new independent message ledger
is introduced.

Original requirements and authorized evidence are attached or accessible through
host material readers. Core capture and access checks are performed by the
controller/runtime; the executor does not call Core to retrieve them. Preserve
mandatory source reading through the actual material delivery/read mechanism;
controller paraphrase or a routing ACK is insufficient. Required material that
cannot be delivered blocks dependent execution; independent work may continue.
Untrusted source text never acquires instruction or tool authority.

The executor chooses its local tools and steps within the delegated scope. It
does not ask the controller before every tool use. Tool permission enforcement
belongs to the host/provider, including scoped filesystem/process access:
omitting a Core tool name from the prompt is not isolation. An unrestricted shell
with Core credentials would violate this profile. Unsupported isolation is
reported as unsupported, without silently claiming a qualified two-session mode.

Outputs preserve the requested deliverable, artifact references, observed
validation, failures and uncertainty. The controller interprets these results,
performs or requests independent verification and submits explicit typed Core
commands. Core never infers completion, permission or replan from substrings in
the executor prose. Host termination is not business completion. A failed
validation can lead to feedback and further work within the same admitted scope;
a material scope/revision change needs a newly qualified dispatch.

**Length is language-neutral and task-dependent.** Preserve independently
executable meaning before minimizing size. Initial experimental targets are
200–800 model tokens for an ordinary brief, 800–2000 for a complex handoff and
150–600 for a result summary. These are unvalidated starting points, not schema
limits, defaults, pass criteria or truncation rules. Count with the actual model
tokenizer; record language/content mix. Code, mathematics, tables, source material
and full requested deliverables retain their natural format. Measure summaries,
attachments, rereads and all exchanges together; moving text behind a reference
does not remove its cost. Small same-session corrections carry only the change
when continuity is proven, with no minimum length requirement.

For example, the controller can ask: “Repair the export failure shown in the
attached reproduction; preserve the original ordering requirement and stay in
the assigned workspace. Validate the regression and report remaining gaps.”
The response can explain the change and link the patch and independent test
result. Neither sentence is a substitute for original requirements, a permission
grant or a canonical completion receipt.

### Sessions, lifecycle and recovery

Start with one logical work Agent and two explicitly bound native session
roles. Do not create a second Goal/Todo/quota identity merely to split cognition.
Extend the existing session binding owner with role and generation, separate
ordered queues and separate context baselines; do not write two native IDs into
the current single Agent-scoped slot. One controller owns control dialogue;
at most one executor attempt owns the selected work. The controller role is not
another simultaneous business executor. Peer or parallel execution still needs
its existing independent claim/lease/handoff contract.

1. The existing entrypoint obtains fresh admission or resumes an owed receipt.
   It supplies the captured unified contract to the controller.
2. The controller reasons from the Goal, unmet requirements, results and feasible
   work; Core validates its chosen operation. Replan policy still controls when
   review is required. Fact-first reasoning does not turn a stride-only trigger
   into the default policy or require a gratuitous route change.
3. Before dispatch, the host binds work/request revision, attempt, session role,
   generation, scope and budget. Record intent before invoking the executor.
4. The executor works and returns observations/artifacts. Readback distinguishes
   delivery, execution, result availability, independent validation and accepted
   writeback. Dialogue can span several exchanges without multiple quota debits.
5. The controller proposes acceptance or revision; the existing effect owner
   validates and settles the original Turn exactly once. A fresh decision then
   continues runnable work, waits on the recorded event/time or stops.

| Failure | Required handling |
| --- | --- |
| Controller crashes after dispatch | Recover the persisted attempt and executor state/result before deciding to resend; do not start a duplicate executor |
| Result/settlement response is lost | Read existing receipts by original idempotency identity; retry only the unresolved effect |
| Executor restarts or context is compacted | Fence the old generation, requalify continuity and deliver complete current material if unknown |
| Cancellation, changed requirements, expired lease or late result | Revalidate current authority/revision before every owned dispatch/write; retain evidence, reject stale acceptance and reconcile admitted effects |
| Stop while a tool is running | Host interrupts within its supported contract; report acknowledgement and actual termination separately. Preserve unknown/in-flight effects; never claim physical rollback from a stop receipt |
| Controller is unavailable | Existing host/Core stop and budget mechanisms remain effective; hold dependent work and recover, without asking the executor to become Core owner |

### Differential context

Reuse the existing context-delivery owner and immutable capture mechanism.
Deliver complete context first. Send exact registered-subtree deltas only with
proven complete delivery and retained context in the exact consumer session,
role, epoch, schema and source capture. Preserve deletion, array order, null,
empty values and complete strings. Unknown fields remain fully delivered until
their reuse semantics are registered; send full if delta plus metadata is larger.

Current authority, admission, cancellation, unresolved-read, settlement and
scheduler facts stay fresh and inline even if unchanged. A warm transport never
relaxes the underlying instructions. Missing/out-of-order deltas, truncation,
compaction, corrupt or unknown baselines select full recovery from the same
capture automatically, without another admission/debit. Execution still checks
current source validity and authority; recovering an old capture cannot revive
cancelled work. The executor's task conversation is a separate consumer of
semantic material, not a relabeled delta of the controller's Core packet.

## 6. Alternatives and design choices

| Alternative | Disposition |
| --- | --- |
| Keep quota and TurnEnvelope as permanent compatible views | Reject as the end state: duplicate selection/rendering and field-drift remain; retain only bounded migration decoders |
| Give the executor a compact Core packet view | Reject as the default two-session design: it retains protocol authoring load and two model-facing Core clients |
| Pure natural-language chat with no runtime binding | Reject: stale/duplicate results, cancellation and restart cannot be reliably reconciled |
| Always use two sessions | Reject: controller cost, latency and lossy delegation may exceed the benefit; keep a qualified single-session profile |
| One universal runtime/effect executor | Reject: host, scheduler, transaction and provider permissions differ; share semantics and receipts, not ownership |

## 7. Safety, privacy and compatibility

Controller reasoning grants no extra authority. Runtime credentials and Core
write capabilities remain inaccessible to the executor; scoped work artifacts
are delivered under current access rules. Permission revocation and cancellation
are enforced outside model memory. Sensitive source material stays within its
authorized audience and retention boundary, including model-provider selection.

Existing single-session behavior and optional-capability-off behavior need
parity. Unsupported profiles fail explicitly. Old persisted captures and receipts
retain their original version/signature and replay identity; never rewrite them
to resemble the new schema. Mixed-version live writers are fenced, not merged
by best-effort prose conversion. Schema removal requires the exact field inventory,
lossless mapping and explicit maintainer approval required by the RFC index.

## 8. Migration and rollback

### C1 wire-layout recommendation

The proposed starting layout evolves the existing Turn-envelope version into
one complete contract, retaining complete decision fields at their current root
paths. Add actual host-operation binding and integrity metadata through their
existing owners; do not wrap a second complete `facts` document beside a compact
`action` projection. This is a migration recommendation, not a registered wire
version or a claim that today's quota payload is already the final protocol.

| Source or concern | Candidate mapping and qualification |
| --- | --- |
| Complete current decision fields | Preserve path and value, including optional mode-specific fields; enumerate all modes before cutover. Do not copy only one observed packet's keys. |
| Work context, required reads and settlement | Keep their existing `interaction_contract` paths and owners. Existing root-relative references retain their meaning; any intentional relocation requires explicit reference and reader migration. Never rewrite prose or command strings by pattern. |
| Host-operation binding | Compose from the actual caller execution context. Validate consistency with source authority; reject conflicting bindings rather than choosing whichever representation is convenient. |
| Content and transport integrity | Commit the entire semantic instance independently of the former compact action digest. Preserve exact capture-byte verification and original settlement identity as separate checks; changing a transport encoding does not create a new effect. |
| Historical receipts and readers | Decode the recorded version for outstanding work. A temporary internal adapter may serve an existing effect interpreter, but must not become a second emitted contract or a compact replacement for the model's required input. |

A synthetic layout probe used real isolated File/SQLite quota captures and the
existing TypeScript context codec. Preserving source paths permitted warm delta
encoding; moving all facts under a new `facts` key while retaining the old
`quota_packet` surface fell back to full with `delta_not_smaller`. Both layouts
reconstructed exactly, and an epoch change required full delivery. Retention was
synthetically asserted; this measures codec behavior, not host observation,
model comprehension or outcome/cost benefit. It rejects **unmapped root relocation
under the existing surface**, not nesting in general. A redesigned nested layout
remains possible if its mapping and consumers justify the migration cost.

Therefore C1/C2 must explicitly version the context surface and its fresh/reuse
paths with the wire transition. Do not relabel an old surface or inherit its
baseline by Turn identity. The first delivery after transition is full; reuse
requires a verified compatible retained baseline. Qualification includes fields
outside the old action projection, missing baselines, session/epoch changes and
same-capture recovery. This resolves a concrete layout risk; shared writer and
final-consumer replacement remain the next implementation, not another layout
framework or a declaration that C1 is delivered.

### C1 caller replacement and cutover unit

The cutover unit is a supported entrypoint **and its downstream consumers**,
not an output flag. Source inspection at `99921829f2c5` identifies the following
live seams. This supplements the earlier baseline audit; it is a migration
design, not a claim that these paths have changed.

| Live seam | Concrete replacement and retained owner |
| --- | --- |
| `quota.py::_emit_quota_result` / `_project_quota_cli_payload` | Compose the complete contract before capture; replace the ordinary/envelope execution-format branch. Retain admission, capability hooks, capture IO and host poll receipts with their current owners. A diagnostic status view is not an executable contract. |
| `turn.py` after `build_fresh_turn_decision_owner().resolve()` | Call the same composition owner with the actual scheduler execution context. This entry calls `build_turn_envelope` directly; changing quota CLI emission alone does not migrate Turn. Retain the Turn plan, journal and receipt executor. |
| `heartbeat/task_body.py::render_thin_heartbeat_task_body` | Replace the `captured_envelope` instruction split with one contract-reading instruction. Preserve exact selection/reentry transport, notification independence, required reads and original settlement. The saved bootstrap still resolves current instructions on wake. |
| `turn_driver/codex_cli.py::_prompt` and `host_candidate.py::extract_turn_authority` / `render_prompt` | Replace format-specific model inputs at the actual prompt boundary. Today ordinary Codex receives the envelope, staged replan uses extracted authority, and structured hosts use extracted authority. Shared source bytes or signatures do not prove these final inputs preserve the same obligations. Keep provider result encoding and outer effect ownership. |
| `turn_driver/decision_capture.py` and `cli_commands/quota_capture.py` | Reuse immutable capture, validated readers and full/delta delivery. Fresh delivery and saved-capture recovery must reconstruct the same contract; do not reuse a continuity baseline for a different projection merely because its Turn identity matches. |
| `benchmark/runtime/worker.py`, `benchmark/runtime/sessions.py` and `scripts/external_scheduler_worker.py` | Migrate the product entry they actually invoke. Keep evaluation setup and outer wake ownership; do not add benchmark-only conversion or count a managed-host test as attached-host acceptance. |

Before replacing any seam, its implementation PR records source path, field or
instruction clause, current readers, target owner, representation, recovery and
retirement condition. Relocation must include reference resolution; an omitted
diagnostic needs evidence that it carries no action, authority, required read or
acceptance obligation. Unknown data cannot silently disappear. Unknown required
execution semantics cannot be made safe merely by forwarding their JSON: the
dependent operation stays unavailable until a compatible consumer understands
them. Do not classify obligations by substring matching.

Use **one explicit version transition**, not automatic format negotiation per
wake. New admission for a migrated binding requires compatible composition,
delivery and consuming readers. An unsupported consumer receives an actionable
unavailable result before dispatch, without creating a second live writer.
Already admitted work continues its recorded version and original receipts;
retain its historical decoder until that work and the supported recovery window
are reconciled. Rollback likewise separates outstanding work from new admission.
A version transition does not rewrite saved prompts, journals or source hashes
as if they had always used the new contract.

The first C1 PR must include the two production composition callsites above and
at least one complete producer-to-final-input journey, with an explicit list of
remaining readers. Qualifying that bounded slice does not enable the new writer
for an unqualified host or close C1. The final cutover removes active format
choice only after all supported readers qualify. Temporary decoders have named
callers and removal conditions; they are not user-facing compatibility views.

For each normal, selection, replan, wait, recovery and capability-off fixture,
check independently authored obligations at **three boundaries**: composed
contract, reconstructed delivery, and final model input plus required material
reads. Include a source change outside the old action signature, a missing
required source, an incompatible consumer and a lost settlement response.
Reconstruction equality alone misses prompt-layer omission; a complete prompt
alone misses stale authority or a duplicate debit. These are integration
requirements, not authorization to run a model or launch an experiment.

1. Inventory actual producers, readers, writers, saved prompts, captures and
   external integrations. Map each old field and prose obligation to its retained
   owner/field, authoritative derivation or explicitly approved removal. No
   blanket claim of “same facts” suffices. Keep original failure fixtures.
2. Qualify the unified contract in single-session execution through real quota,
   thin-heartbeat and Turn entrypoints. Switch one writer per binding; old
   readers are explicit version-pinned migration adapters with an identified
   caller and removal condition. They do not become permanent product views.
3. Add role-aware sessions, shared lifecycle reuse and the opt-in two-session
   profile. Reuse existing same-session/native-resume and effect recovery code.
4. Adopt the shared product profile in benchmark workers and the packaged App
   heartbeat journey. Each host proves its own observation, stop and recovery
   boundaries. Neither a CLI test nor a model simulation qualifies installed App.
5. Remove old producers, format selectors, duplicate renderers and dual-format
   tests after the last supported active reader migrates. Keep only historical
   version decoders for supported receipt replay. End-state acceptance requires
   one emitted contract and no choice between quota and Turn packet formats.

Rollback disables new admission for the affected profile, drains or interrupts
its attempts, reconciles receipts and restores the prior qualified profile on
the next admitted work. Do not silently replace native sessions or reinterpret
pending receipts. Before field/decoder removal, demonstrate export, old-version
readback and downgrade behavior; retain the old reader until the supported
retention/upgrade boundary is satisfied. No destructive migration is authorized
by this document alone.

## 9. Validation and acceptance

| Claim | Evidence and required result | Boundary |
| --- | --- | --- |
| One complete contract | Field/clause inventory; same captured normal, replan, wait, recovery and capability-off workloads through all active entrypoints; identical reconstructed semantic instance | One serializer unit test is insufficient; malformed/unsupported versions fail explicitly |
| Lossless context delivery | Full/delta/recovery equivalence, missing/late/truncated pages, role/session mismatch and real native compaction/resume | Include all read/recovery costs; no second admission or spend |
| Role isolation and recovery | Controller/executor crash windows, duplicate dispatch, late result, revision change, lease expiry and stop under actual host tools | No executor Core access; no stale result adoption or hidden business executor |
| Semantic adoption | Original requirements → controller decision → actual executor work → independent verification → accepted result and original-audience return | Read receipt, valid JSON or successful replan alone cannot pass |
| Shared production paths | Real CLI and supported File/SQLite paths; real isolated PostgreSQL suite when authority persistence changes; packaged App heartbeat and benchmark worker reuse | No live Goal corruption; unsupported/unrun hosts stay unqualified |
| Outcome and cost benefit | Matched current single-session, unified single-session and unified two-session arms with fixed task/model/policy/budget/evaluator | Report uncertainty, failures and counterexamples; no claim from prompt bytes alone |

Use the [existing measurement model](long-horizon-harness-benchmark-research-program-v0.md#6-measurement-model).
Include both sessions' input/output/cached tokens, tool and material reads,
planning/replan/recovery, wall time, verification, human attention and provider
cost; unknown usage is not zero. Persist causal attribution without duplicating
cost when an artifact is forwarded. Compare accepted outcomes under comparable
budgets, not only replan counts or executor speed. Freeze criteria before any
separately authorized experiment; this RFC specifies no automatic winner.

## 10. Operational contract

Existing Goal Chat, settings and work readback must expose the selected profile,
actual controller/executor availability, current work, meaningful progress,
unavailable/error state, scope of Stop and returned artifact. Avoid exposing
internal packet selection as a user task. Reuse shared typed projections and
configuration precedence; do not create an independent controller console or
duplicate provider/model settings.

Observe captures, request/attempt/role/generation, current revisions, effect
receipts and cost coverage in existing diagnostics. Give operators actionable
recovery without raw private transcripts. Notifications remain separate from
work continuation; event/time waits and backoff use the current scheduler owner.
No model busy-polling loop or new recurring automation follows from this RFC.

## 11. Normative delivery plan and refactor tasks

These tasks extend roadmap S2/S4/S6/S7/S11 and the effect interpreter's existing
convergence work, not a new roadmap. Reconcile related active tasks/PRs before
claiming; reuse qualified fixes rather than reimplementing them. Task IDs below
are stable design references, not claims that a canonical Todo is complete.

| Task / dependency | Owner and concrete replacement | Decisive exit / rollback |
| --- | --- | --- |
| **C1 — Unified contract; first** | Interaction/work-context + quota/Turn owners: inventory fields and instruction clauses, capture one schema, migrate actual ordinary quota/Turn producers and thin renderer | Single-session real-entry parity with complete requirements, action binding and once-only settlement; retain version-pinned readers until cutover qualifies |
| **C2 — One context-delivery pipeline; C1** | Context owner + host observers: absorb full/delta/detail/recovery into the canonical contract; remove packet-format branches and duplicate context copies | Same-capture recovery and exact role/session continuity through normal/replan/resume; full fallback without a new admission; rollback encoding to full |
| **C3 — Session binding and native lifecycle; C1** | Session/runtime owner: extend existing binding for role/generation; reuse native create/resume/observe/interrupt and ordered queues | Two roles cannot overwrite the Agent native ID, cross-read baselines or race execution; recovery observes existing attempts before retry; disable new role admission to roll back |
| **C4 — Shared governed lifecycle; C1** | Effect/Turn owner + outer worker adapters: converge duplicated prepare/dispatch/observe/validate/writeback/settle orchestration around existing typed operations and receipts | App/Turn/external worker agree on admission, original result and single debit under partial failure; scheduler effects retain their true host owner; switch callers back only after receipt reconciliation |
| **C5 — Replan and result authoring boundary; C1** | Goal/Vision and interaction owners: expose current facts and typed controller operations; remove ordinary executor obligations to manufacture Core writeback fields in the two-session profile | Fact-first decision preserves default/stride policy differences, all evidence and required validation; invalid proposed writes reject; single-session authoring remains qualified during rollout |
| **C6 — Controller/executor exchange; C2–C5** | Manager/request + host owners: reuse versioned semantic requests and result return; replace schema-constrained executor work with natural-language work/material exchange | Complete source delivery, local executor autonomy, enforced Core isolation, corrective exchange and independently accepted outcome; return to qualified single-session profile for new work on rollback |
| **C7 — Benchmark reuse and full-cost attribution; C4/C6** | Benchmark toolkit/execution owner: thin adapters select the same product profiles; consolidate duplicated launch/session settings and track both sessions without changing frozen trials | Native/plain controls unchanged; matched-arm configuration/replay and complete cost coverage; no jobs launched merely by merging helpers |
| **C8 — Product configuration and operational readback; C3/C6** | Existing App/settings/Chat projections: one effective configuration owner, role-aware activity, failure/recovery, Stop and artifact return | Packaged managed and supported attached heartbeat journeys, including unavailable host and late results; installed qualification separate; no new packet-format toggle |
| **C9 — Retire old paths and qualify adoption; C1–C8** | Contract/runtime maintainers: remove superseded producers, format switches, duplicated prompts and tests; update protocols, guides and RFC delivery facts | Caller/field/decoder retirement inventory, historical replay and rollback evidence; App + benchmark acceptance and matched benefit before any default promotion |

C1's inventory is part of its usable replacement, not a standalone architecture
framework. C3/C4/C5 can proceed independently once C1's contract is stable;
C7 can prepare measurements before C6 but cannot claim two-session outcomes.
Implementation PRs must name the replaced caller, remaining gap, actual tests
and rollback. No full language migration or unrelated manager rewrite is a
prerequisite. No task is complete merely because a new abstraction compiles.

For C1, the first implementation slice pairs the complete field/clause migration
with a real single-session producer and consumer replacement. Start at the
shared quota emission boundary and trace both attached heartbeat delivery and
the Turn adapter; retain their actual host ownership. Do not build an unused
third serializer while both active writers keep their own semantics. Existing
`test_quota_decision_capture.py` and `test_turn_host_decision_capture.py` provide
capture/recovery coverage to extend, not proof of the proposed schema. Qualify
normal work, selection, replan, wait, unsettled-Turn recovery, unavailable detail
and capability-off behavior through the real entries on isolated fixtures.
Each case must check complete obligations and original settlement identity as
well as reconstructed data. The oracle must include source-different but
projection-equal cases; comparing two outputs of the same projection is circular
evidence for completeness. Native-resume/context work remains with its existing
owner; adopt its qualified changes and add only the integration coverage missing
at the new composition boundary. Keep C1 open until the replacement works and
the remaining supported readers have explicit cutover/retirement conditions.

## 12. Open decisions

1. **Exact wire name and field mapping — contract owner, before C1 cutover.**
   Prefer evolving one existing registered vocabulary/version over a parallel
   protocol family. Section 8 recommends preserving source-root paths; finalize
   the version and host-binding mapping after the complete producer/reader/field inventory;
   maintainer approval is required for removal, not for preserving old meaning.
2. **First qualified two-session host — runtime owner, before C6 dispatch.**
   Choose from actual session control and isolation capabilities. Managed Codex
   may be an implementation vehicle; App heartbeat is a required product
   qualification. Neither entry is presumed to prove the other or benchmark use.
3. **Resource allocation and default — product/evaluation owners, after C7–C8.**
   Test same-model controller/executor first to isolate architecture effects;
   cheaper controller models and different budgets are separate experiments.
   Keep the profile opt-in until full outcome/cost evidence supports a decision.
