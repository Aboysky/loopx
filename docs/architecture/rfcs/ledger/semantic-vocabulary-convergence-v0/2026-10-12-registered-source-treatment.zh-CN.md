# 当前集成主线上的登记来源处理

复核基线：`43173c0b8c8761abee4cdddc665f0f0f20f194f7`（2026-10-12）。
本记录推进 #4447 既有 2a/2b/2c，不改变范围、扫描登记、预算或运行时行为。
[分阶段范围修订 #4789](https://github.com/loopx-project/loopx/pull/4789) 已合入，
交付验收及下方两项含义决策仍开放。**列出 26 行不等于 26 项 producer 证明或 tracker 关闭。**

注册表仍为 26 项，已用实际 `task_lease_lifecycle_operation` 替换退休的 `lease_action`。
F1/F2 仍是 **6/26**：五项 kernel 和 settlement-binding witness。其余二十项跨运行时
词表不会因本文件或 decoder 测试获得 F1/F2 分数。精确 owner 符号及允许值仍以
`loopx/semantics/vocabulary_v0.json` 为准；表内 owner 路径相对 `loopx/control_plane/`。

运行时见证从因果输入执行 shipped owner；注入值只证明调用方输入/decoder 边界。
混合来源保留两种义务。兼容项要有实际 reader 和退出条件；不把实际跨界的词表改叫
local-only 来避开责任。本记录不证明全程序可达性、数据流或通用 F6。

## 来源与兼容清单

| 登记词表 | Owner / 槽位 | 已执行来源处理 | 兼容及剩余边界 |
| --- | --- | --- | --- |
| turn_result_kind | `turn_driver/executor.py`, `transaction.py::_result_kind` → generated result kind | 内部选择 + Host/调用方输入。driver/executor/transaction 测试执行结果与拒绝分支；固定 decoder 对每个登记值执行输入见证。 | 接纳 Host 输入不证明真实 Host 产生过该结果；保留 journal/replay 读取。 |
| turn_route | `turn_driver/driver.py`, `loop_controller.py` → plan/envelope route | 内部 route 选择。driver/controller 覆盖可执行、门控、修复、等待和非法 route；生成投影受检查。 | 保留三种 Turn 词表及显式投影；route 不是持久回执。 |
| loop_disposition | `turn_driver/loop_controller.py::decide_loop_disposition` → disposition | 内部决策，由当前 route/result/迭代事实决定；controller 表与失败/重试测试执行 owner。 | 生成 controller 规则与 route/result 分离，不因拼写相似合并。 |
| agent_scope_frontier_action | `agents/agent_scope.py` → frontier action | 内部候选/依赖/handoff 分类；frontier 测试执行耗尽、等待、重新分配和后继分支。 | TS 生成绑定是消费者；lane 耗尽不证明整个 Goal 完成。 |
| effective_action | `quota/decision_summary.py` and registered overlays → final action | 内部 decision/overlay 输出。quota 决策测试执行当前路径，固定 producer 扫描保留明确未知站点。 | 根 decision/frontier 联合与嵌套 replay 槽位分开；不把来源处理当作全部分支可达性证明。 |
| settlement_binding_kind | `effect_program.ts::settlementIdentity` → binding_kind | 对输入身份做内部归一化；既有 binding witness 执行 Todo、replan、unbound 及矛盾组合。 | unbound 不允许扣费；精确身份仍由回执 owner 验证。 |
| task_lease_lifecycle_operation | `work_items/task_lease_lifecycle_request.ts` → operation | 调用方选择的 native 输入。lifecycle 测试执行六种操作、非法输入、CAS 与重试。 | 替换退休的私有 lease_action，不删除租约行为；保留 fence 历史字段缺省，不计入 F1/F2。 |
| settlement_step_kind | `effect_program.ts`, `turn_driver/settlement.ts` → receipts[].step_kind | 内部回执构造 + 外部 envelope 输入。2a 在无 callback 的已提交回放中产生四类 step，并拒绝非法输入。 | 保留顺序前缀、effect 身份与历史回执；注入 step 只证明解码。 |
| settlement_failure_kind | `effect_program.ts`, `quota/settlement_readback.ts`, native lease owners → failure kind | 内部失败 + 接受的 envelope 输入。2a 覆盖 12 个 wire 值、真实 unbound guard 读取及 native 权限拒绝。 | cancelled 的来源用途仍待下方处理。租约摘要使用 failure.step，Effect envelope 使用 failure.step_kind，不能伪造 wire 转换。 |
| receipt_bound_monitor_phase | `quota/settlement_readback.ts` → `settlement_phase.ts` → monitor_phase | 从精确 monitor commit 内部派生；2a 执行 poll_due/settled、错误身份和旧 monitor effect id。 | settlement_pending 仅有 consumer 兼容证据，实际 builder 不产生；迁移历史 work-lane reader 后才可删除。 |
| receipt_bound_replay_phase | `quota/settlement_readback.ts` → `settlement_phase.ts` → replay_phase | 从隔离回执文件和完成/写回/扣费前缀内部派生三种 phase；重复读取与身份负例经过 bridge。 | 保留 terminal-to-replay 适配与原绑定；phase 投影不证明所有持久 writer 正确提交。 |
| delivery_workspace_kind | `agents/workspace_guard.py::capture_delivery_workspace` → TS snapshot | 真实 Git/文件观察 + snapshot 输入；主 checkout、linked worktree、本地 Goal 与 TS normalization 覆盖三类及非法 origin。 | 保留 v0 Git snapshot；不能把 Git 缺失/读取失败转换成本地 Goal 授权。 |
| delivery_workspace_identity_kind | `agents/workspace_guard.py` → `agents/delivery_workspace.ts` → identity_kind | 观察 git_repository/local_goal 并验证 snapshot；同组真实 Git/local 测试验证身份、归属与 peer 隔离。 | local Goal 身份不能满足独立 Git 工作区要求；v0 snapshot 保留迁移读取。 |
| delivery_workspace_requirement | `quota/settlement_workspace_causality.ts` → requirement | 根据明确工作合同内部派生 required/not_required/unknown；覆盖写入、非交付、缺元数据和事件读取。 | unknown 必须修复；无工作区的旧结算例外需要精确且完整的 validation/writeback 回执，部分或错 Todo 不通过。 |
| todo_completion_continuation | `todos/completion_state.ts::selectTodoCompletionState` → continuation | 根据 intent/Todo 内部选择 active_goal/successor/no_followup，同时读取持久 metadata；完整 owner 与非法 authority 测试执行。 | 后继与 no_followup 矛盾时拒绝；保留 metadata normalization，退休的标量 RPC 仍拒绝。 |
| todo_completion_recovery | `todos/completion_state.ts` → recovery | 根据已完成 Todo、关闭 intent 和 identity source 派生两类 terminal recovery；固定及显式 lifecycle 用例覆盖。 | 不重写原完成身份、不创建后继；null 表示没有恢复，与恢复类别分开。 |
| todo_decision_scope_kind | `todos/decision_metadata.ts::normalizeTodoDecisionScope` → kind | 作者声明输入，无自动分类 producer。七类输入见证、非法值、真实 CLI 和精确 kind dominance 测试执行 reader。 | other 作者何时选择仍待下方处理。接纳不授予权限；保留旧 standing-scope codec。 |
| todo_decision_scope_granularity | `todos/decision_metadata.ts` → granularity; `decision_scope.ts` → dominance | 作者声明五级输入，显式 domain 与未知/null/数字负例，加 CLI/dominance 用例。 | 更宽 scope 不能跨 kind 或覆盖精确目标/接收者冲突；不由有界视图推断缺失 scope。 |
| goal_amendment_class | `goals/goal_amendment_proposal.ts` → proposal.amendment_class | 作者按 RFC 声明四类；全类别/未知类别测试与真实 submit/list CLI 提供输入和 journal 证据。 | admission 是 canonical_effect=none 的提案事实，不是共享变更提交或 protected authority 委托。 |
| goal_amendment_proposal_admission | `goals/goal_amendment_proposal.ts::admissionOutcome` → admission | 根据当前 basis、sequence、digest 内部产生 admitted/needs_rebase；相等/过期/未来/canonical/Markdown 情况经过 TS 与 CLI journal。 | 保留过期提案供 rebase，拒绝虚构未来历史；admitted 不等于变更获准。 |
| goal_amendment_proposal_admission_fact | same admission owner → admission_facts[] | 内部产生四类 basis/sequence/digest 事实；组合条件和 basis 转换用例执行对应分支。 | 并存事实不能删减；Markdown/canonical 的零序号不是 event-log 新鲜度，不改变提案格式或提交权限。 |
| scheduler_cadence_transition | `scheduler/state_transition_rules.ts` → cadence transition | 由 identity、间隔、ACK 和失败事实内部产生六种 transition；Python 独立表与 TS coarse owner 用例执行。 | 保留旧 Python characterization 和状态读取；cadence 不授予执行/扣费权限。 |
| scheduler_host_transition | `scheduler/state_transition_rules.ts` → host transition | 内部产生 apply/host-match-ack/failure-suppressed/settled 四类；独立表与负例覆盖当前观察和历史失败。 | 投影不是实际宿主更新；ACK 仍须满足 #6259 当前宿主读回门，不从 fixture 推断宿主更新成功。 |
| handoff_mode | `coordination/handoff_mode_vocabulary.ts`, authority/mode-plan readers → mode | 配置输入 + legacy/default 兼容读取；真实 show/set、非法 frontmatter、quiescence、lease/replay 测试覆盖。 | 新配置仅 soft_claim/hard_lease，legacy 留作升级/回执读取；解析 mode 不等于租约权限。 |
| delivery_outcome | `work_items/delivery_outcome.ts`, monitor/Host/replan producers → outcome | 作者声明 + 机器选择：monitor/Host 产生 surface_only/progress，replan 可降级 outcome_gap；primary_goal_outcome 是作者主张。history/monitor/executor/replan/diagnostic 测试覆盖。 | decoder/claim 检查不独立证明主目标已实现；历史矛盾主张被诊断，不改写为成功。 |
| delivery_continuity_preemption | `quota/should_run_packet.py::_delivery_preemptions_for_route` → `turn_driver/delivery_continuity.ts` | guard 内部事实 + typed 输入：回执、阻塞 lane、replan、repair、拒绝交付；continuity route/selection 测试覆盖抢占与后续重选。 | 继续旧交付不能覆盖当前抢占；其他 qualifier 的同形字符串不自动归此词表，不改绑旧回执。 |

## 两项待 owner 处置的含义

- **`settlement_failure_kind.cancelled`：Effect/settlement owner。** 公开的
  `SettlementResult.failed(...).bind(...)` 接受它并短路后续步骤，但核对 settlement
  owner、枚举成员引用和调用方，仍没有内部取消 producer。chat/Host/usage 中的
  cancellation 属于不同词表。decoder 证明 wire 处理，不回答谁可在何时产生。
  保留现有 unresolved value note。关闭需要找到具体取消合同/producer 并执行见证，
  或单独评审明确的 reserved/compatibility-only 范围和退出条件；本批不虚构 producer，
  也不自动批准这个例外。
- **`todo_decision_scope_kind.other`：Todo decision-scope owner。** 真实 parser 接受它，
  精确 kind 匹配阻止它覆盖具名 kind；没有把未知输入转成 other 的 fallback，非法值被拒绝。
  现有公开协议只列枚举，没有作者选择准则，catalog 的六类 authority 也不能补出含义。
  保留 unresolved note。关闭需要明确的作者使用合同/例子，或获评审的兼容保留/迁移决定；
  membership 测试不能代替 owner 决定产品含义。

以上是**未解决且未获批准的例外**，继续阻止 Stage 2/3 关闭。不能用统一来源标签或
绿色测试替代这两个决定。

## 证据与复跑

使用目标源码 checkout、`uv sync --extra test`、合格 Node 22.22.3 及
`npm ci --ignore-scripts --no-audit --no-fund`。确认 Python 导入来自该源码。
[英文同版](2026-10-12-registered-source-treatment.md#evidence-and-reproduction)
逐组列出精确测试文件：基础 Turn/frontier/quota/binding；2a settlement/readback/lease；
2b workspace/completion/decision-scope；2c proposal/scheduler/handoff/outcome/continuity；
历史 packet 及生成物。这里复用既有证据，不创建新验收数据库。

Python 命令为 `uv run --extra test python -m pytest -q <所列文件>`；TS 命令为
`node --no-warnings --experimental-sqlite --experimental-strip-types --test <所列文件>`。
2a 新增的 unbound guard 通过真实临时文件读取、TS owner 和 Python bridge；排除 owner
用例执行真实 native lease 拒绝并验证无租约写入。外部失败输入现在显式覆盖 12 值，
registry 对比只防止新值遗漏其 witness，不把枚举遍历升级为 producer 证明。
新增 scope kind/granularity 输入用例也不解决 other 的作者含义。预期来自接受的合同和
独立因果场景，而非回显 owner 结果。

该源码基线加本批聚焦见证：2a **66 passed**，既有 Python 领域组 **564 passed**，
补充真实 Git/monitor/replan/lease 组 **82 passed**，native TS 组 **421 passed**、无 skip。
TS typecheck、聚焦 Ruff、两个生成器及完整 semantic drift 通过。以上是源码/隔离后端
证据，不是安装端或真实模型验收。drift 仍为 F1/F2 6/26、F3 0/26、F4 4/4、F5 1/1、
F6 0/0；45 个 producer site 未解析，其中 17 个无法提供 producer 见证。
没有放宽任何上限或扫描边界。既有 semantic architecture/value-note 组另有
**706 passed**，docs governance 和 premerge 通过。RFC status 索引仅更新 ledger
条目数，不据此改变交付成熟度。

已知集成边界：复用同一不可变主线上的独立复现结果，`test_quota_settlement_cli.py`
的三个用例（普通结算及两种 Todo-less replan）在 scheduler ACK 失败。fixture 没有
#6259 要求的当前宿主观察，owner 返回 `rrule_mismatch` 且不写 scheduler 状态。
它们不在上述通过组中，本次文档批次未重跑；完整 CLI suite 的这个缺口仍开放，
不通过放宽规则或断言消除。

## 集成状态与关闭边界

此主线已包含 #4772/#4777 的事实修正、#4775 live composition、#4783 settled replay、
#4788 rejected selection、#4786 inbox composition、交叠正确性 #4764、binding witness
#4747 与 2a #4795。#4794 已停止新 `protocol_action_packet` 写入，保留历史读取和签名
投影；其余五个旧字段继续可见，全字段退休不是关闭前提。#5317 已交付独立 #4743 的
开发期 advisory，因此旧“从未实现/AGENTS 没有指引”说法过期；advisory 仍不阻断或证明语义。

本次测量时，后续 typed-failure 修复 #6251 与 canonical-selection 修复 #6268 尚未合入，
不能算入该基线；#6260 已合入。它们不扩大 #4447 原关闭范围。完整来源处置、维护者验收
及最终单一集成版本读回仍是关闭前提。本批不声称安装前端/Lark、真实模型或完整 Goal/团队
验收；不改变生产 provider/持久格式，原始日志及本地 Goal 状态不进入仓库。
