# RFC：Goal Direction Baseline（目标方向基线）v0

- **RFC 状态：** 已接受
- **替代 / 关闭：** 无
- **交付成熟度：** Partial（M1 纯构建器；M2 producer 与 consumer 未验收）
- **作者 / 负责人：** LoopX 维护者与贡献者
- **创建日期：** 2026-09-10
- **最后规范修订：** 2026-10-12
- **实现基线：** `41a95d9`
- **跟踪 Issue：** [#2831](https://github.com/huangruiteng/loopx/issues/2831)
- **相关契约：**
  [Agent Material Frontier](../../reference/protocols/agent-material-frontier-v0.md)、
  [Goal Vision and Replan](../../reference/protocols/goal-vision-replan-contract-v0.md)
  与
  [Shared Goal Alignment and Governed Amendment](./shared-goal-alignment-and-governed-amendment-v0.md)
- **语言镜像：**
  [English](./goal-direction-baseline-v0.md)；中英文语义差异均属于缺陷

## 文档地图与维护契约

第 1-10 节是持久设计与验收契约。第 11 节是规范性交付计划。第 12 节
记录运行时交付前必须决定的问题，其中的建议不等于批准。附录记录非规范性的
执行、决策、证据与 fixture 计划。

RFC 成熟度与交付成熟度互相独立。M1 TypeScript builder 已基于传入的完整 canonical
输入实现 `goal_direction_baseline_v0`。生产 receipt writer、声明编写命令与运行时
consumer 尚未交付；schema 合法的合成回执不证明真实阅读。

独立的[验收合同 v0](../../reference/goal-acceptance-observations.md#owner-authorized-contract-v0)
不实现本 RFC 的材料声明或使用回执。#2831 的下一切片是**方向材料版本与验收基线关联**，
通过下面的同 Agent/当前版本 fixture 验证。

---

## 1. 决策摘要

本 RFC 提议一个 provider-neutral、只读的 `goal_direction_baseline_v0`
投影。显式启用该能力的 Goal 声明哪些 owner-controlled 材料和 topic 定义其
方向。投影面向单个 Agent，通过现有 canonical Goal authority registry 解析
声明，并验证同一 Agent 是否针对每个当前材料 revision 持有匹配的
`material_usage_receipt_v0`。

材料 revision 变化只产生 Agent-scoped 方向复核信号。它不会重写 Agent
Vision、创建工作、改变共享路线或修订 Goal intent。如果复核实际改变 Agent
路线，现有 `goal_path_delta_v0` 仍是唯一的路线变更记录。authority 缺失、
材料不可访问、未读、receipt 过期以及冲突全部 fail closed。

Repository owner 文档只是可选的材料 provider 之一。它不会成为写 authority，
repository 路径也不是协议。私有 wiki、外部文档系统或其他已注册 provider
可以在不暴露原始内容的情况下满足同一个契约。

M1 只提供纯 read model，不引入 writer、scheduler、状态 authority、自动 Vision
更新或运行时 gate。M2 保留独立的 consumer 与恢复验收。

## 2. 问题与动机

LoopX 当前可以检测执行漂移：过期 Todo basis、已耗尽 frontier、未关闭的
replan obligation 与 lease 冲突。现有 Agent Material Frontier 也能证明某个
Agent 是否读取了已注册材料的某个 revision。但这两类事实尚未被连接成对以下
问题的显式回答：

> 当前 Agent 的方向是否建立在 Goal owner 现在指定为权威的材料 revision
> 之上？

例如，维护者可能已经修订 architecture contract，但 Agent 仍依据旧理解继续。
此时 Todo graph 可以仍然有效，也无需出现 lease 冲突，但 Agent 路线可能已发生
语义偏离。相反，把 repository 文本当作可执行命令会让最后修改文档的人在无意
中成为 Goal authority。

因此最小有用边界是可审计的 read model。它绑定 Goal-owned 声明、当前
provider-neutral 材料元数据与当前 Agent 自己的 usage receipt，只暴露 drift，
而不决定 Agent 应该如何响应。

### 不变量

1. Goal authority 始终是 material id、topic 绑定、boundary、gate、freshness、
   conflict 与 revision 的唯一 owner。
2. Provider 只解析已注册材料，不授予 Goal authority，也不写 Agent Vision。
3. 只有同一 Goal、Agent、material 和 required revision 的 receipt 才能让材料
   成为 current；peer receipt 永不转移。
4. 缺失、不可访问、未读、过期、歧义或冲突输入永远不能投影出 current 方向
   基线。
5. Revision drift 是 Agent-scoped 的观察结果，本身不会创建 Todo、lease、
   scheduler wake、Goal amendment 或 Vision rewrite。
6. 实际路线变化继续使用 `goal_path_delta_v0`；canonical Goal 变化继续使用
   现有 governed authority 路径。
7. 投影与 fixture 不包含原始文档正文、prompt、reasoning、transcript、
   trajectory、credential、private URL 或本地绝对路径。
8. 未显式启用的 Goal 保持当前行为不变。

## 3. 范围与非目标

### 范围内

- Goal-owned 方向 material id 与 topic 声明；
- 经 `authority_registry.project_materials` 和
  `authority_registry.topic_authority` 的确定性解析；
- 单 Agent 作用域的只读 baseline 投影；
- typed current、re-evaluation-required 与 blocked 结果；
- 与现有 Agent material usage receipt 的 exact-revision 匹配；
- 与 Agent Vision、`goal_path_delta_v0` 及 shared Goal amendment 的关系；
- public-safe synthetic drift fixture 计划。

### 非目标

- 把文档文本解析为 Goal intent 或可执行指令；
- 让 repository、wiki、connector 或 provider 自身成为 authority；
- 引入文档 writer、crawler、cache、scheduler 或第二套 material registry；
- 把原始正文或 provider locator 复制进 control-plane state；
- 从 chat、run log、evidence row 或其他 Agent 的 receipt 推断当前 Agent 已阅读；
- 自动 patch Vision、创建 Todo、重排工作或提交 Goal amendment；
- 替代 `agent_material_frontier_v0`、`goal_path_delta_v0` 或 governed Goal
  amendment 契约。

## 4. 当前系统契约

实现基线已有以下相关 owner：

- `authority_registry.project_materials` 持有 canonical material metadata；
- `authority_registry.topic_authority` 把 topic 解析到 material id；
- `agent_material_frontier_v0` 把 Goal authority、Agent/Todo/Vision/handoff
  requirement、boundary、gate 与 `material_usage_receipt_v0` 组合成只读
  Agent 投影；
- 匹配 receipt 具有 Agent 作用域，并在适用时具有 Todo 作用域；handoff 只转移
  有界 material ref，从不转移 predecessor receipt；
- 当 Agent 实际执行路线变化时，`goal_path_delta_v0` 记录 retained、changed
  与 stopped 事实；
- 当前 `shared_goal_alignment_v0` 绑定的是 event-log 或 canonical Todo
  projection 事实，并非 typed canonical Goal-intent revision。

M1 builder 已将声明的方向材料与单个 Agent 的传入回执绑定。生产声明编写与回执
provenance 仍属于 M2 依赖，不能用 shared-alignment source digest 或 Markdown
state 代替真实阅读来源。

## 5. 提议架构

### 5.1 Ownership 与 authority

显式启用的 Goal 增加 `authority_registry.goal_direction_requirements`。这是
现有 Goal-owned authority registry 的逻辑字段，不是新 registry。它只能通过
authority owner 已有的 governed write boundary 写入。Provider 不能把自己加入
声明。

每条声明包含：

- `requirement_id`：在 Goal 内稳定；
- `material_id` 或 `topic` 二选一且仅有一个；
- `purpose`：说明该来源为何约束方向的有界 public-safe 上下文；
- `required`：布尔值，默认为 `true`。

直接 `material_id` 在 `project_materials` 中解析；`topic` 先通过
`topic_authority` 解析，再把所有引用 id 解析到 `project_materials`。解析得到
按 `material_id` 排序的确定性并集；重复 id 保留全部 `bound_by` requirement
ref。registry 缺失或畸形、id 缺失、空 topic mapping 与矛盾绑定全部 fail
closed。紧凑 authority summary 永远不够。

材料元数据继续由现有 registry 持有。Baseline 只读取以下 public-safe 字段：

- 稳定 `material_id` 与解析出的 topic；
- `role`、`owner_status` 与 `conflict_rule`；
- `boundary` 与 `gate_status`；
- `freshness`；
- 不透明 `revision`。

Revision 是 provider-neutral identity，不是可排序计数器。Provider 可以从
commit、ETag、version id 或 content digest 派生它，但 provider-specific 形式
不进入 core 语义。没有非空 canonical revision 的方向材料不能成为 current。

### 5.2 Read model

提议的投影具有 Agent 作用域：

```json
{
  "schema_version": "goal_direction_baseline_v0",
  "goal_id": "example-goal",
  "agent_id": "agent-reviewer",
  "generated_at": "2026-09-10T00:00:00Z",
  "baseline_digest": "sha256:<canonical-resolution-digest>",
  "direction_state": "re_evaluation_required",
  "reason_codes": ["material_revision_changed"],
  "summary": {
    "required_count": 2,
    "current_count": 1,
    "stale_count": 1,
    "blocked_count": 0
  },
  "items": [
    {
      "material_id": "architecture-owner-contract",
      "bound_by": ["direction:architecture"],
      "required_revision": "rev-7",
      "observed_revision": "rev-6",
      "state": "stale",
      "receipt_ref": "material_receipt:receipt-17"
    }
  ],
  "advisory": {
    "kind": "agent_vision_re_evaluation",
    "creates_work": false,
    "rewrites_vision": false,
    "changes_goal_route": false
  },
  "truth_contract": {
    "authority_is_goal_owned": true,
    "projection_is_read_only": true,
    "receipt_is_agent_scoped": true,
    "provider_is_not_write_authority": true,
    "raw_source_body_recorded": false
  }
}
```

`baseline_digest` 是对 schema version、Goal id、排序后的 requirement binding
与投影使用的排序后 authority-owned metadata 计算的确定性 SHA-256。它排除
`agent_id`、receipt、timestamp、source body 与 provider locator。因此，读取
相同 Goal authority 的两个 Agent 可以共享 baseline identity，同时保留独立
receipt state。该 digest 只证明 basis 相同，不证明语义正确或内容已被使用。

每个 item 复用 Agent Material Frontier 的状态词汇：

1. 声明目标或 revision 缺失：`missing`；
2. boundary 不允许、gate 阻塞或 unavailable receipt：`inaccessible`；
3. 当前 Agent 没有匹配 receipt：`required_unread`；
4. authority freshness 过期、ownership 冲突或 revision 不匹配：`stale`；
5. authority 可访问且无冲突，并存在 exact-revision matching receipt：
   `current`。

当值 public-safe 时，投影可以包含紧凑的 `role`、`owner_status`、
`conflict_rule`、`boundary`、`gate_status` 与 `freshness`，但绝不包含原始
locator、正文、摘录、diff 或展开的 receipt event。

### 5.3 聚合 drift signal

`direction_state` 按以下优先级派生：

1. 任一 required item 为 `missing`、`inaccessible`、`required_unread`、
   freshness-stale、ambiguous 或 conflicted 时为 `blocked`；
2. 没有 blocked item，且至少一份 receipt 的 observed revision 与当前
   authority revision 不同时为 `re_evaluation_required`；
3. 仅当所有 required item 均为 `current` 时为 `current`。

Optional requirement 可以被报告，但不能让 required baseline 变为 current。
未知 state 与未知 conflict policy 按 `blocked` fail closed。`reason_codes` 是
typed token，例如 `authority_registry_missing`、
`direction_requirement_unresolved`、`authority_revision_missing`、
`material_inaccessible`、`material_required_unread`、
`material_revision_changed` 与 `authority_conflict`。消费者不能解析 prose
来判断 drift。

Revision mismatch 是 v0 中唯一会发出 `agent_vision_re_evaluation` advisory
kind 的条件。信号属于所选 `agent_id`，并不表示 peer 已过期。该 Agent 后续
写入 exact-revision receipt 后，新投影可以恢复 current。Receipt replay 继续
遵循现有 receipt identity，且不能在 Agent 之间复制。

### 5.4 与 Vision 和路线变化的关系

Baseline 是 review 输入，不是 Vision writer。未来消费者可以把 advisory 信号
呈现为 Agent-scoped Vision acceptance gap，但不能自动生成 patch，也不能因
scheduler activity 而把 gap 标记为 resolved。Agent 要么记录符合现有契约的
Vision checkpoint，要么通过当前 Vision write boundary 写有界 Vision patch。

读取变更 revision 后仍保留同一路线，无需 path delta。如果 review 改变路线，
写入必须包含现有 `goal_path_delta_v0`，并携带 prior assumption、observed
reality、retained/changed/stopped 事实与 public-safe evidence ref。方向
baseline 不内嵌也不替代该记录。

如果材料揭示 canonical shared Goal intent 本身必须改变，Agent 可以提交现有
governed Goal-amendment proposal。Baseline 不能批准或提交它。

### 5.5 Provider 契约

Core 消费 canonical authority metadata 与 receipt，而不是 provider API。
Provider profile 可以说明如何获得稳定 revision 和判断 availability，但必须
返回相同逻辑字段，并遵守相同 boundary 与 gate 决策。

Repository 文档因此只是一个 profile：

- repository owner 注册稳定 material id 与 topic mapping；
- profile 解析 commit/blob 派生的不透明 revision；
- 在接受 receipt 前判断访问权限；
- 投影既不存 checkout path，也不存文档正文。

相同模型适用于 private wiki 或外部文档服务。Provider 失败时，不得回退到无关
本地文件、Markdown status、chat text 或缓存 prose 后仍报告 `current`。

## 6. 替代方案与设计选择

### 直接解析 repository owner 文档

拒绝。文件路径和 Markdown 约定会成为意外 authority，私有布局会泄露进 core，
非 repository provider 也需要特例。

### 在 Agent Vision 中保存方向文本副本

拒绝。副本会独立漂移、扩大 hot path，并让 owner material 与最新 Agent writer
之间的 authority 归属不清。

### 所有 Agent 共享一份 receipt

拒绝。一个 Agent 的阅读不能证明另一个 Agent 消费了相同 revision，handoff
也不能静默转移理解和权限。

### Revision 变化时自动重写 Vision

拒绝。Revision identity 只证明发生变化，不证明其语义后果。自动重写会把观察
契约变成 planner 与 write authority。

### 复用 shared-alignment source digest 作为方向 identity

拒绝。它们当前标识 event-log 或 Todo projection 事实，不标识 Goal owner 指定
的语义材料。

## 7. 安全、隐私与兼容性

- 能力按 Goal 显式启用。没有声明就不产生 baseline 投影，并保持当前行为。
- Builder 纯函数且只读，不授予 permission、material access、claim、lease、
  scheduler budget 或 amendment authority。
- 在接受 receipt currency 前完成 boundary 与 gate 检查。Boundary 缺失表示
  inaccessible，而不是 public。
- 仅可输出 public-safe id、metadata、digest、typed state 与紧凑 receipt ref。
  排除 source body、locator、本地路径、credential、prompt、reasoning、
  transcript、trajectory 与 raw run log。
- Mixed-version reader 必须忽略缺失的 optional projection。旧 reader 省略
  baseline 时，writer 不得因此创建或修改 baseline state。
- 未知 schema version、state、conflict rule 或畸形 receipt 字段全部 fail
  closed，绝不能被强制转换为 `current`。

## 8. 迁移与回滚

M0 只改文档，不需要数据迁移；回滚只需 revert 文档。

未来实现必须保持 default-off，并经现有 Goal authority owner 引入声明。启用投影
前，admission 必须依据完整 canonical registry read 校验每条 requirement。
回滚同时禁用 reader 与声明 authoring，但不得删除 registry material 或
receipt。因为投影不持有 canonical state，禁用它不能回滚或重写 Agent Vision、
Todo、lease 或 Goal intent。

在证明 mixed-version 行为与 provider failure 能够 fail closed 且不改变默认
scheduler/quota path 之前，任何实现 milestone 都不能 promotion。

## 9. 验证与验收

| 声明 | 测试或证据 | 必须结果 | 边界 / 排除项 |
| --- | --- | --- | --- |
| 提案 public-safe 且内部一致。 | `loopx check --scan-path docs/architecture/rfcs --scan-path docs/development/contributor-tasks.md` | 通过，且无 private-data 或 contract finding。 | 不证明运行时行为。 |
| Exact current revision 具有 Agent 作用域。 | 附录 D 的 synthetic case F1、F3。 | 只有所选 Agent 的匹配 receipt 得到 `current`。 | 不允许 cross-Agent receipt transfer。 |
| Revision 变化暴露 drift 且不修改状态。 | Synthetic case F2。 | `re_evaluation_required`；input、Vision、Todo、lease 与 Goal route byte-identical。 | 不自动解释语义。 |
| 缺失和不可访问 authority fail closed。 | Synthetic case F4、F5。 | `blocked`，含 typed reason code 且零 mutation。 | Provider availability 为模拟值。 |
| 聚合状态确定。 | Synthetic case F6、F7。 | 一个 stale required item 压过 current item；输入不变则结果稳定。 | 不做性能 qualification。 |
| 路线变更仍由现有契约持有。 | Synthetic case F8；未来实现还需 Goal Vision contract tests。 | 路线不变时无 `goal_path_delta_v0`；实际路线变化只经现有契约接受。 | 不批准路线变更本身。 |
| 不投影原始 source material。 | Fixture key allowlist 与 public-boundary scan。 | 无 body、locator、URL、本地路径、prompt、reasoning、transcript、trajectory、credential 或 run-log 字段。 | 允许不透明 id 与 digest。 |

未实现或 skip 的行不算绿色。Live provider qualification 与 production
promotion 不在本 RFC 当前交付成熟度内。

## 10. 运行契约

M0 没有运行时 operational surface。未来实现只能暴露紧凑
`direction_state`、typed reason code、count、baseline digest 与有界 item
ref。Provider error 必须成为 typed blocked reason，不能被吞掉，也不能展开成
source content。Operator 可以重试 read 或修复 canonical authority，但不能
通过修改投影来覆盖 drift。

Read model 大小必须有界。未来 schema 在实现前必须定义最大 requirement 和输出
item 数。Overflow 必须以 typed capacity reason fail closed，不能静默截断
required material。

## 11. 规范性交付计划

| Milestone | 交付行为 | 进入 gate | 退出证据 | 回滚 |
| --- | --- | --- | --- | --- |
| M0 | 仅双语 public design note 与 synthetic fixture 计划。 | #2831 上维护者批准的 helper scope。 | 文档检查与 F1-F8 评审。 | Revert 文档。 |
| M1 | 基于完整 Goal authority 和 receipt 的 optional pure builder；无 consumer 或 writer。 | 批准第 12 节决策与 schema 限制。 | 确定性 fixture、mutation check；若双 runtime 消费则做 Python/TypeScript parity；public-boundary scan。 | 移除 default-off builder 与 projection。 |
| M2 | 一个只读 Agent-scoped Vision-gap consumer。 | M1 conformance，并由维护者显式批准 consumer 与 recovery UX。 | 端到端证明 drift 可见、同 revision replay 安静且不修改 Vision/Todo/route。 | 禁用 consumer；保留 canonical registry 与 receipt。 |

M1 实现在 [`direction_baseline.ts`](../../../loopx/control_plane/goals/direction_baseline.ts)。
现有 [F2 smoke](../../../examples/goal-direction-baseline-f2-smoke.py) 已改为执行真实
TypeScript 测试与两项源码 mutation，删除原 fixture-local reducer。没有 CLI、
persistence、consumer、scheduler 或 quota 路径调用这个 builder。M2 保持独立。

## 12. 实现决策与剩余验收

M1 采用 [#6289](https://github.com/loopx-project/loopx/pull/6289) 中的具体候选包络。
这些实现选择不代表生产容量 promotion，也不批准 M2 consumer。

1. **容量。** 独立限制 64 条输入声明（去重前）、256 个解析后的不同材料（含可选项）、
   4,096 条输入回执（去重前）、2 MiB 完整 compact UTF-8 JSON 输入、256 KiB 完整
   compact UTF-8 JSON 输出。各最大值不能保证同时满足。不得截断。超限返回
   `blocked` / `direction_capacity_exceeded`、空 items、null digest；计数不是部分
   authority 摘要。文本宽度沿用 frontier：id/revision 180 个 Unicode 字符，topic 120，
   purpose 220，显式可用 boundary 80。
2. **回执选择。** 在选择 scope 前验证所有输入行：准确 v0 schema、identity、
   `read`/`used`/`verified` 或 `unavailable`、revision 与带时区时间戳。`unavailable`
   可无 revision。必须同 Goal、Agent 与准确 Todo scope；Todo 回执不满足 Goal-wide
   read。相同 replay id 去重，冲突 id 拒绝。按纳秒精度选择最新时间；并列观察必须
   outcome/revision 相同，再确定性选择最小 receipt id。非法/未知行或矛盾并列观察
   返回完整 blocked 拒绝，不能恢复较老成功。不回显原始输入、部分 items 或 digest。
   调用者 identity/time 无效时抛出类型化输入错误，因为无法构成有 scope 的投影。
3. **Authority 元数据。** 登记字段目前允许 prose，M1 不解释自然语言：只有
   `owner_status=reviewed`、`conflict_rule=owner_wins`、`freshness=current` 与
   `gate_status=ready|registered|readable` 可以通过；缺失/未知值阻塞。这是有界 reader
   profile，不重写登记策略。role 仅提供信息。public/public_safe 或显式传入的 available
   boundary 允许本次读取；传入 envelope 本身不授予访问权限。缺失 boundary 不可访问。
   要求完整 `project_materials` 与 `topic_authority`；map/list identity 与重复声明必须一致。
   可选项保留可见，聚合计数与原因仅计算 required 项，可选成功不能遮蔽必需项失败。
   完整输入中的非法行即使可选或属于 peer，也会拒绝整个投影。
4. **首个 consumer 仍待交付。** 复用显式 Goal/Agent management cold read 与打包 Goal
   detail，不接入普通 polling/quota/scheduler。M2 必须验证真实授权读取 → 精确版本回执
   → 同 Agent 刷新，并通过既有 Goal-instance lifetime 与 acceptance owner 绑定。
   drift、不可访问、错误 Agent、reload 与 retry 必须可见，Vision/Todo/lease/route 不变。
   材料基线 current 不能让整 Goal 验收变绿。Lark 单独保持未验收。不新增 v0 receipt
   字段、第二个 receipt store 或伪造 provenance。

---

## 附录 A：执行账本（非规范性）

### 2026-09-10 — M0 提案

- **基线：** `41a95d9`
- **交付：** 双语 RFC 与 synthetic fixture 计划
- **证据：** 文档与 public-boundary check 等待 PR 验证
- **已知缺口：** 无 schema 实现、writer、consumer 或 live provider
  qualification
- **对规范设计的影响：** 初始提案

### 2026-10-04 — F2 synthetic fixture（M1 前）

- **基线：** `99839ae`
- **交付：** 附录 D 的 F2 行以 checked-in public-safe smoke 及其 mutation
  arm 落地（`examples/goal-direction-baseline-f2-smoke.py`）；第 11 节附注
  记录了 M1 保持关闭的原因
- **证据：** smoke 本地通过；`loopx check --scan-path
  docs/architecture/rfcs` 干净；等待 PR 验证
- **已知缺口：** 无 runtime builder、writer 或 consumer；F1 与 F3-F8 仍未
  checked-in
- **对规范设计的影响：** 无 —— 仅固定附录 D 的 F2

## 附录 B：决策日志

| 日期 | 决策 | Owner / 批准 | 替代方案 | 修改的规范章节 |
| --- | --- | --- | --- | --- |
| 2026-09-10 | 接受 M0 为仅文档 helper scope；repository 文档只是一个 provider，revision drift 保持 advisory。 | [#2831](https://github.com/huangruiteng/loopx/issues/2831#issuecomment-5224703471) 上的维护者 scope | Runtime 实现或 repository-specific writer | 初始第 1-12 节 |

## 附录 C：证据注册表

| Evidence id | 声明 | 基线 / 环境 | Artifact 或命令 | 结果 | 隐私 / 有效性边界 |
| --- | --- | --- | --- | --- | --- |
| E1 | 已审计当前 Material Frontier 语义。 | `41a95d9` | [Agent Material Frontier](../../reference/protocols/agent-material-frontier-v0.md) | documented | 仅 public contract；无 live material。 |
| E2 | 路线变更 ownership 保持现有契约。 | `41a95d9` | [Goal Vision and Replan](../../reference/protocols/goal-vision-replan-contract-v0.md) | documented | 不证明 proposed baseline。 |
| E3 | M0 repository 文档保持 public-safe。 | PR validation | `loopx check --scan-path docs/architecture/rfcs --scan-path docs/development/contributor-tasks.md` | pending | 仅文档 scope。 |
| E4 | F2 revision-drift 不变量可执行且带 mutation 检查。 | `99839ae` | `python3 examples/goal-direction-baseline-f2-smoke.py` | 等待 PR 验证 | 仅虚构 id；无 runtime builder 或 live material。 |

## 附录 D：Synthetic drift fixture 计划

所有 fixture 使用虚构 id 与 revision。Harness deep-copy 输入，运行 pure
builder，并断言输入 byte-for-byte 不变，同时不存在任何 Vision、Todo、lease、
scheduler、Goal-amendment 或 route-write effect。

| Case | 输入变化 | 预期投影 | 独立 negative assertion |
| --- | --- | --- | --- |
| F1 exact Agent receipt | 两个 required material；所选 Agent 均有 exact-revision receipt。 | `current`；digest 稳定；两项均 current。 | Goal、Agent、material 或 revision 不同的 receipt 均不能满足任何 item。 |
| F2 revision drift | Agent receipt 之后，一个 authority revision 发生变化。 | `re_evaluation_required`；`material_revision_changed`；变化项 stale。 | 不发出 Vision patch、Todo、wake、lease、amendment 或 path delta。 |
| F3 peer receipt | 只有另一个 Agent 持有新 revision receipt。 | 所选 Agent item 为 `required_unread`，或因自身旧 receipt 保持 stale；aggregate 按优先级为 blocked 或 re-evaluation-required。 | 投影不包含 peer receipt ref。 |
| F4 missing authority | 完整 `project_materials` 缺失、声明 id 缺失或 revision 为空。 | `blocked`，含精确 missing reason。 | 紧凑 count/summary 不能被当成空或 current registry。 |
| F5 inaccessible material | Boundary 不可用或 gate blocked。 | `blocked`；item inaccessible。 | matching revision receipt 不能覆盖 boundary/gate。 |
| F6 mixed required set | 一项 current，一项 exact revision-mismatch。 | `re_evaluation_required`；count 确定。 | Current item 不能遮蔽 required material 的 revision drift。 |
| F7 replay stability | 相同 canonical input 与 receipt 改序并投影两次。 | 除显式 `generated_at` 外，normalized item、digest、state 与 reason code 相同。 | Receipt 顺序与重复 declaration 不能制造 churn。 |
| F8 route ownership | Agent 读取变更 revision 后保持或改变路线。 | 新 receipt 让 baseline 恢复 current。 | 保持路线不产生 path delta；改变路线只有携带有效现有 `goal_path_delta_v0` 才能接受。 |

真实 builder 的 [TypeScript suite](../../../tests/control_plane_ts/direction_baseline.test.ts)
覆盖 F1–F8 read-model 断言与容量边界。现有 F2 smoke 在隔离副本中改变实际 revision
与 Agent 匹配，要求独立测试以断言错误拒绝 mutation。F8 写侧路线验证仍由
`vision_checkpoint.test.ts` 负责；纯 read model 不能证明 Agent 的真实路线变化或阅读。

## 附录 E：拒绝或已取代方案

第 6 节记录当前拒绝设计。若证据表明某 provider-specific owner 能保持相同
authority、privacy 与 no-mutation 不变量，可以新增 profile，但不能分叉 core
contract。

## M1 源码检查点

可选 TypeScript 纯构建器取代原合成 decision owner。验证覆盖完整 registry 解析、
准确 Agent/Todo/revision、冲突、时间顺序、输入不可变、输入/输出限额与 public-safe
投影。用 Node >=22.22.3 执行
`node --experimental-strip-types --test tests/control_plane_ts/direction_baseline.test.ts`
与 `uv run --extra test python examples/goal-direction-baseline-f2-smoke.py`；既有
`vision_checkpoint.test.ts` 验证路线 authority。没有新增平行 Python reducer 或
Python/TypeScript 双消费路径。生产回执真实性、instance-bound storage、live provider、
生产容量冻结和 M2 CLI/frontend/Lark 流程仍未验收。回退只移除尚未接入消费者的 builder，
无需迁移 canonical state。
