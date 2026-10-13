# Long-running execution, exploration and correction

[中文版](long-running-execution-exploration-and-correction.zh-CN.md)

Long-running work needs both continuity and opportunities to change direction.
A useful integration lets a Host execute coherent work, brings new evidence
back to the existing LoopX decision boundary, and verifies the resulting work
without turning every tool result into another planning cycle.

This is an implementation map and integration guide, based on LoopX source
`17bc011b3c5fcd30b879442cb21d734ac5d8ab69`. External source snapshots were
inspected on 2026-10-13. It connects existing RFCs; it creates no policy,
schema, scheduler, default change or execution grant. Source presence,
installed behavior, model adoption and measured benefit remain separate.

## Existing owners and the connected path

The [overall roadmap](rfcs/loopx-overall-roadmap-v0.md) retains priorities:
S3 planning/collaboration, S4 Hosts, S6 evidence, S7 scheduling/cost and S10–S11
reliability/evaluation. The following documents own the decisions:

| Boundary | Existing owner | Integration question |
| --- | --- | --- |
| Tool feedback, delivery settlement, authority changes | [Hierarchical stride](rfcs/hierarchical-agent-stride-control-v0.md), §§5–7 | How much coherent work can continue before relevant feedback or an authority boundary? |
| Long-job result and wakeup | Stride §7.5; existing Host/provider and monitor owners | Which exact result revision justifies another decision, and how is a lost notification recovered? |
| Exploration and route selection | [Research exploration](rfcs/research-exploration-control-plane-v0.md), §§11.5–11.6; [Explore](../../loopx/capabilities/explore/README.md) | What uncertainty can change the next action, and what evidence distinguishes alternatives? |
| Original requirements and source changes | [Shared Goal alignment](rfcs/shared-goal-alignment-and-governed-amendment-v0.md), §§3.3, 3.7–3.8 | Does the revised path retain current requirements, evidence scope and other Agents' work? |
| Corrections, handoff and original-route return | [Manager operational contract](rfcs/capable-manager-semantic-handoff-v0.md), §10; [live team workspace](rfcs/live-team-workspace-v0.md), §9 | Was a correction received, adopted, executed, independently checked and returned? |
| Recovery and performance | [Failure containment](agent-failure-containment-and-recovery.md); [optimization guide](../development/testing-and-quality.md#roadmap-aligned-optimization) | Which original operation can resume, and where is the demonstrated cost? |

The source has the following control path. Branches are conditional; they are
not a mandatory sequence of extra model calls:

```text
Current Goal, requirements, authority and evidence
  -> existing quota / Todo admission
  -> Host executes one coherent work slice
  -> observed result and durable writeback
       -> eligible continuation: keep useful work moving
       -> relevant unknown or counterevidence: explore, then reconsider
       -> admitted review: satisfy its existing source-bound obligation
       -> candidate completion: run the owning acceptance checks
       -> wait / interruption / stop: use the existing lifecycle
  -> accepted decision and later work feed the next review
```

| Source connection | What exists at this baseline | What it does not establish |
| --- | --- | --- |
| [`projectReplanHistory`](../../loopx/control_plane/work_items/replan_history.ts) → [`build_replan_context`](../../loopx/control_plane/goals/goal_frontier/__init__.py) → action packet / [TurnEnvelope](../reference/protocols/turn-envelope-v0.md) | Progress, monitor and review facts reach the Agent through existing quota/Host callers | That the model read, understood or followed every instruction |
| [`strideReviewMismatch`](../../loopx/control_plane/work_items/stride_policy.ts) and [`replan_semantics`](../../loopx/control_plane/work_items/replan_semantics.ts) → Vision/ACK settlement | Enabled structured path reviews bind the current obligation, previous decision and delivered evidence | Truth of Agent claims or permission to execute a successor inside the original Turn's outstanding settlement |
| [`evaluateDeliveryRoute`](../../loopx/control_plane/turn_driver/delivery_continuity.ts) → next eligible work | A qualifying accepted replan successor can take precedence over ordinary continuation | Semantic adoption of the proposed method or Goal completion |
| [`decisionFollowthrough`](../../loopx/control_plane/work_items/replan_context.ts) → next review | Prior accepted path and subsequent recorded progress remain connected | Execution and Goal gain: the projection explicitly retains `unknown` |
| [Explore result writeback](../../loopx/capabilities/explore/result_writeback.py) → [turn context](../../loopx/capabilities/explore/turn_context.py) | Explicit findings can return through ordinary Todo/Turn writeback and inform later work | Automatic skill-report ingestion, scientific truth or a complete frontend attachment/retry journey |

The [Goal Vision/replan contract](../reference/protocols/goal-vision-replan-contract-v0.md)
defines activation and current settlement rules. `evidence_conditioned_v1` is
optional and default-off; ordinary review remains available when it is off.
The baseline's structured fresh-path checks are not a claim that every legal
periodic-review exit requires the same attachment. Follow the owning contract
when that boundary changes; efficiency work must not bypass admitted review,
quota settlement, permission, lease or revision checks.

## Transfer mechanisms, with their limits

These are implementation references, not comparative performance results.
Their checked versions do not identify an installed release. Adapt ownership,
trigger conditions and failure cases rather than copying whole runtimes.

| Public source snapshot | Mechanism worth transferring | LoopX placement and limit |
| --- | --- | --- |
| Grok Build `2bdd1d6a`: [Goal loop](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/session/acp_session_impl/goal.rs), [strategist](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/session/goal_strategist.rs) | The Host-owned Goal path evaluates round results, verifies candidate completion, and invokes advisory strategy investigation after repeated non-achievement | Separate continuation, acceptance and method investigation through existing owners. Do not copy a fixed reviewer count or assume extra model calls improve quality/cost |
| Codex `9167a0b2`: [tool/input loop](https://github.com/openai/codex/blob/9167a0b2d4a74d44a4d388057d304682e47313c6/codex-rs/core/src/session/turn.rs), [Goal continuation](https://github.com/openai/codex/blob/9167a0b2d4a74d44a4d388057d304682e47313c6/codex-rs/ext/goal/src/runtime.rs) | Tool results and pending input continue the current turn; a lifecycle extension starts eligible Goal work when idle | Reuse Host execution and context management. Make the continuation owner explicit so native Goal and external heartbeat do not independently launch the same attempt |
| OpenCode `be674e31`: [inbox](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/inbox.ts), [run coordinator](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/run-coordinator.ts), [child return](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/subagent-completion.ts) | Current-work steering and queued work differ; a pending-wake signal coalesces notifications across the drain-to-idle race; child completion returns as input | Extend existing inbox/session/Turn delivery. A process-local single executor cannot replace distributed claims, leases or adoption evidence |
| Pi `e6220e13`: [agent loop](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/agent/src/agent-loop.ts), [skills](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/coding-agent/docs/skills.md), [subagent extension example](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/coding-agent/examples/extensions/subagent/README.md) | Inner tool/steering and outer follow-up loops; skills and richer workflows load when needed | Keep ordinary work independent of a full research workflow. An extension example is not default product support, isolation or cross-Host qualification |

Grok Build's new and legacy Goal paths have different failure behavior; its
legacy path includes infrastructure fail-open completion. That behavior is not
a candidate for LoopX acceptance. Public Goal/turn similarities are not
independent experimental evidence: Grok's
[third-party notice](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-tools/THIRD_PARTY_NOTICES.md)
also identifies tool code ported from Codex/OpenCode. This does not establish
shared Goal-loop history. None of these client sources proves how every hosted
service operates, or that an external effect executes exactly once.

## Integrate exploration without making every task research

An initial unknown, a new opportunity, user direction or a counterexample may
justify exploration. Repeated failure is one signal, not a prerequisite or an
automatic command to switch methods. Ask what decision the investigation can
change before choosing a skill or parallel work.

| Unknown | Suitable work | Useful return |
| --- | --- | --- |
| Existing implementation and constraints | Focused source-reading skill | Proven behavior, reusable seams and limitations |
| Alternative methods or external evidence | Research/search skill | Candidates, primary sources, applicability and counterevidence |
| Whether a candidate fits the project | Combined source/research analysis or a bounded experiment | A discriminating result, integration cost and adoption criterion |

These are workflow categories, not required skill packages or a new routing
enum. Choose the smallest method that answers the question. Independent
subagents are useful when their hypotheses or information sources differ;
their summaries retain source references and unresolved points. A research
report can itself satisfy a research task. It need not manufacture code work.

Use Explore's existing `evidence` mode to retain findings; use `planning` when
several candidate branches need its read-only selection support. These modes
grant no claim, spawn or execution authority. Validated reusable findings enter
the existing `explore_result` attachment or `--explore-result-json` writeback,
with tested input revision, applicability, observation, interpretation and
evidence. A compatible `path_delta` can supply the existing attachment form
instead of duplicating the same narrative. Routine work needs no empty finding.

Next-turn context and `explore_review` let the Agent explain which finding
supports changing the route, continuing it or performing a justified
replication. Keep negative evidence scoped to its tested conditions and retain
the best qualified artifact. Unavailable input and an inconclusive measurement
do not establish refutation. Actual task steps, artifact versions and independent
validation must support a claim of adoption; source bindings alone cannot.

## Keep ordinary operation bounded

Apply the existing [optimization evidence guide](../development/testing-and-quality.md#roadmap-aligned-optimization)
to the real consumer before selecting an abstraction:

- Measure repeated calls, history reads, serialization/bridge work, provider IO
  and model work separately. A short rendered response can still require a
  full source scan. Explore's bounded turn context does not claim bounded
  history IO.
- Reuse facts within a proved snapshot boundary; refresh authority and revision
  at the owning admission/write boundary. A cache cannot become another writer.
  Prefer removing a demonstrated duplicate read/copy before adding cache services.
- Keep decision-essential facts and detail routes in default context. Load
  skill instructions, verbose evidence and diagnostics when relevant. Preserve
  ordering, provenance, acceptance and stop obligations when shortening prose.
- Handle transient transport retry, context compaction and method revision at
  their respective owners. Neither elapsed time nor a fresh identifier proves
  progress. Resume from the original operation; query unknown effects before retry.
- Count exploration, evaluators, reviewers, compaction and observer CPU/IO in
  total cost. Faster visible responses can still cost more overall.

For a supported long-job profile, Stride §7.5 proposes observing without a
reasoning call, then advancing the existing monitor generation only for an
exact validated result. A deadline catches missed events. Unsupported Hosts
retain their current path with an explicit limitation; this guide does not
silently suppress model admission or change heartbeat defaults.

## One connected qualification episode

Use one supported Host/profile and an isolated repository task: improve an
implementation while retaining a declared command and compatibility contract.
Preserve that acceptance contract throughout this episode:

1. Begin useful work, then introduce a method correction without weakening the
   original requirement. Verify reception separately from its application.
2. Investigate one relevant unknown, return evidence through ordinary writeback,
   and let the next admitted work adopt a candidate or explain why the incumbent
   remains appropriate. Check the actual artifact and result.
3. Return an exact background result through the existing monitor/resume owner.
   Deliver duplicate and out-of-order notifications, including one arriving
   just as the consumer becomes idle.
4. Interrupt after a committed result but before acknowledgement. Recover the
   same operation and current Goal basis. Test source revision changes, missing
   evidence and owner stop; stale results cannot relaunch stopped work.
5. Independently verify the result and return it to the original conversation.
   Packaged frontend and CLI should distinguish queued, delivered, adopted and
   validated facts, and expose missing/stale evidence without a success badge.

The existing [correction evidence view](../../apps/presentation/dashboard/src/features/personal-workspace/goal-team-episode.tsx)
can inspect explicit artifact/review/revision/adoption relationships. It is not
a universal visual history of every stride decision. A missing frontend
attachment/retry or decision-to-artifact connection remains companion work in
the owning slice; a CLI-only prerequisite should be described as partial.

| Delivery slice | Existing owner and decisive evidence |
| --- | --- |
| Remove one measured overhead | S2/S7/S10 and optimization guide: same-workload base/head comparison with required semantic, replay and real-backend checks |
| One exploration affects subsequent work | Explore and Stride §7.6: actual model decision, current evidence, attributable artifact and independent outcome; preserve an explicit no-change choice |
| Recover one provider-result/wakeup path | Stride §7.5, Host and monitor owners: duplicate/lost/late event, restart, stop, source-change and original-operation readback through the supported product entry |

These slices reuse the existing roadmap and RFC milestones. They are not a
new task ledger or a requirement to finish unrelated migrations first. Review
current related changes before implementing: cadence inheritance and review
enforcement, correction retry identity, and existing codec/Explore performance
repairs may already cover parts of the intended slice.

Measure accepted-outcome quality, omitted requirements, total time/tokens/cost,
correction-to-action delay, recovery loss, duplicate effects and user attention.
Pin source, Host/model, task/input, authority, evaluator and budget; retain
failed and incomplete samples and distinguish cold/warm paths and history sizes.
Choose evaluation thresholds before assessing a candidate. Synthetic fixtures
qualify mechanical behavior; live adoption and comparative benefit need their
own evidence. Lower overhead with worse acceptance or recovery is not success.

Ordinary behavior-preserving cost repairs can proceed under existing contracts.
Changes to default admission, review, retention, authority or settlement belong
in the owning RFC/contract with compatibility and rollback evidence. Keep optional
strategies scoped until qualified; disabling a strategy preserves historical
evidence and does not cancel admitted work or erase recovery obligations.
