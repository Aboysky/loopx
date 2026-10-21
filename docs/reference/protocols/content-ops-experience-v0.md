# Content-Ops interactive learning models v0

Content-Ops can retain a finite teaching model and present it in three forms:

- **HTML condition exploration:** keep the policy fixed, change the conditions,
  predict and compare the resulting paths and costs.
- **Game decision practice:** pursue the declared goal, choose successive
  actions and inspect feedback under an effort budget. Spending, goal attainment
  and failure follow the model rules; repeated clicks do not earn points.
- **Mini-World strategy replay:** choose a scenario and a policy for each path,
  run both, then inspect individual decisions with the replay controls. Conditions
  and policy choices remain visible, so a comparison need not imply one variable
  was isolated.

These are local learning-content interactions. The same TypeScript owner
validates and runs all three; Python handles private file I/O and transport.
The model contains explicit states, actions, costs, conditional edges, scenarios
and state-to-action policies. It executes no author JavaScript, network request,
tool call or real Goal transition. Goal/Todo/lease state and permissions are
unaffected. The new vocabulary belongs to this content protocol, not the
control-plane lifecycle.

## Prepare and use

Tell your Agent the mechanism, reader, learning goal, source and assumptions.
It can prepare a model through the native CLI under an existing registered
local Goal:

```bash
loopx content-ops experience prepare --goal-id <goal> \
  --plan-json examples/content-ops-experience/evidence-return.json --format json
loopx content-ops experience list --goal-id <goal> --format json
loopx content-ops experience inspect --goal-id <goal> \
  --experience-id <returned-id> --format json
```

Open **Settings → Capabilities → single Goal → Content production → Interactive
learning**. Select the prepared model and a learning format. The owner does not
need to fill in a second JSON form or activate a video provider. Video production
and source/style references retain their own tabs in the same workbench.

The examples are finite illustrations, with their assumptions in the source:
[`evidence-return.json`](../../../examples/content-ops-experience/evidence-return.json)
and [`service-diagnosis.json`](../../../examples/content-ops-experience/service-diagnosis.json).
They are not observed Agent trajectories or measurements of a running service.

For the equivalent CLI run, save conditions and a policy in `run.json`:

```json
{"scenario_id":"complete","policy_id":"evidence_first"}
```

```bash
loopx content-ops experience run --goal-id <goal> --experience-id <id> \
  --expected-revision 1 --run-json run.json --format json
```

For manual decision replay use `actions`, for example
`{"scenario_id":"complete","actions":["delegate","return","verify"]}`.
Omit both policy and actions, or use an empty action list, to inspect the initial
state. Policies and manual actions cannot be combined in one request. An unknown
state, action, parameter, scenario or extra execution field is rejected.

## Deterministic contract

`content_ops_experience_v0` declares a title, learning goal, source reference,
boundary and assumptions, followed by these bounded fields:

| Field | Contract |
| --- | --- |
| `states` | 2–24 unique IDs, readable labels/descriptions, explicit terminal/goal booleans; a goal is terminal |
| `actions` | 1–16 unique IDs with integer effort costs from 1 to 100 |
| `transitions` | 1–128 edges; from/action/to references must exist; terminal states have no outgoing edges |
| `parameters` | 0–4 parameters, each with 2–4 declared choices and a valid default |
| `when` | Exact parameter selections; overlapping edges for the same state/action are rejected |
| `policies` | 1–8 policies, at most one declared action per state; incomplete coverage stops visibly |
| `scenarios` | 1–8 named parameter overrides; caller overrides take precedence |
| `budget`, `max_steps` | Integer effort budget 1–1000; at most 40 successive decisions |

Validation checks structure and determinism, not the quality or truth of the
author's model. The initial trace frame costs zero. A legal action takes its
declared edge and cost. An unavailable or unaffordable action leaves the state
and spent budget unchanged and returns explicit feedback. Terminal states and
the step limit stop execution; unused requested actions are returned rather
than silently presented as performed. Replay uses the returned trace; reset
evaluates the initial state under the selected conditions.

The canonical plan digest binds the rules, content, source and assumptions.
Identical preparation reuses the same stable artifact identity after a lost
response. Replacing an existing artifact requires its current revision; a
stale explicit revision is rejected even when the content is unchanged. A run
must name its current revision. Corrupt or escaping artifacts fail closed while
other readable models remain available. The browser accepts no filesystem path
or model-creation operation through its read/run API.

## Recording, privacy and recovery

**Record model scene (silent)** records only the model's own Canvas, at a requested
24 fps, for up to two minutes. Stop and download the WebM; export the model and
decision trace alongside it to preserve source and conditions. No microphone,
screen capture, upload or publication is started. A supported browser/WebM codec
is required; when unavailable, model interaction and trace export remain usable.
Recording is a source asset for later editing, not an automatically qualified
complete movie or a listening review.

Predictions, explanations and traces remain in this page's memory until the
owner exports them. Reset starts another model attempt; closing the page loses
unexported observations. No participant answers are automatically collected.
Prepared source artifacts use the existing Goal's private local content
workspace. Publication continues through its separately authorized content-item
workflow. `learning_effect=not_tested` and `publish_authorized=false` remain
explicit on results.

When a model is unreadable or changes during work, reload its source before the
next run. The last valid result remains visible with the failure. Repair a bad
model through `prepare --experience-id <id> --expected-revision <current>`;
restoring older content produces a new revision. Keep exported source snapshots
when an archive of older content is needed; this workspace retains the current model.
For damaged content, preparation requires the known current revision and a valid
replacement source; it does not silently reuse a damaged digest. If the saved JSON
or its identity/revision metadata is unreadable, restore a trusted private backup
first. Other readable models remain available throughout recovery.
Stop recording or leave the workbench to stop using the interaction. There is
no new background service or persistent enablement switch.

中文：Agent 先按原请求准备有来源、目标与假设的有限模型；本人进入既有内容制作工作台，
直接比较条件、在预算内作出决策，或选择环境/策略并逐步回放。三种形式复用同一 TS
规则，不是换皮播放器。当前实现保留模型、规则、失败反馈、重置和操作轨迹，并可显式
录制本图的静音 WebM。模型达成目标、可播放或编码成功，都不等于独立的学习收益或创意
验收。未导出的回答仅在当前页面；不自动上传或发布，不改变真实 Goal 的权限和状态。
