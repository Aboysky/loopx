# 长时执行、探索与纠偏的衔接

[English](long-running-execution-exploration-and-correction.md)

长时任务既需要连续推进，也需要在合适时机改变方向。有效的集成让 Host
连续完成有意义的工作片段，把新证据送回既有 LoopX 决策边界，再验证后续工作，
避免每个工具结果都引发一次完整规划。

本文是实现地图与集成指南，基于 LoopX 源码
`17bc011b3c5fcd30b879442cb21d734ac5d8ab69`，外部源码快照核验于 2026-10-13。
它衔接现有 RFC，不创建新策略、schema、调度器、默认行为或执行授权。
源码存在、安装后的行为、模型采用和实测收益分别成立。

## 现有归属与已连接的路径

[整体路线图](rfcs/loopx-overall-roadmap-v0.zh-CN.md)保留优先级：S3 规划与协作、
S4 Host、S6 证据、S7 调度与成本，以及 S10–S11 可靠性与评测。
各项决策继续由以下文档负责：

| 边界 | 现有归属 | 集成要回答的问题 |
| --- | --- | --- |
| 工具反馈、交付结算、权限变化 | [分层步幅](rfcs/hierarchical-agent-stride-control-v0.zh-CN.md) §5–7 | 遇到重要反馈或权限边界之前，可以连续完成多大的有意义工作？ |
| 长任务结果与唤醒 | Stride §7.5；既有 Host/provider 与 monitor | 哪个确切结果版本值得再次判断，丢失通知后怎样恢复？ |
| 探索与路线选择 | [研究探索](rfcs/research-exploration-control-plane-v0.zh-CN.md) §11.5–11.6；[Explore](../../loopx/capabilities/explore/README.zh-CN.md) | 哪个未知可能改变下一步，什么证据能区分候选方案？ |
| 原始要求与来源变化 | [共享 Goal 对齐](rfcs/shared-goal-alignment-and-governed-amendment-v0.zh-CN.md) §3.3、§3.7–3.8 | 新路径是否保留当前要求、证据范围及其他 Agent 的工作？ |
| 纠正、交接与原会话返回 | [协调员运行契约](rfcs/capable-manager-semantic-handoff-v0.zh-CN.md) §10；[团队工作区](rfcs/live-team-workspace-v0.zh-CN.md) §9 | 纠正是否被接收、采用、执行、独立检查，并返回原入口？ |
| 恢复与性能 | [故障控制](agent-failure-containment-and-recovery.zh-CN.md)；[优化指南](../development/testing-and-quality.md#roadmap-aligned-optimization) | 哪个原操作可以继续，实际成本发生在哪里？ |

源码中的控制链如下。分支按条件进入，不要求额外模型调用依次走完全部步骤：

```text
当前 Goal、要求、权限与证据
  → 既有 quota / Todo 准入
  → Host 连续执行一个有意义的工作片段
  → 实际结果与持久回写
       → 合格的接续工作：继续推进
       → 相关未知或反证：探索后重新判断
       → 已准入复核：履行既有来源绑定义务
       → 候选完成：执行所属验收检查
       → 等待 / 中断 / 停止：沿既有生命周期处理
  → 被接受的决定与之后工作进入下一次复盘
```

| 源码连接 | 此基线已有行为 | 尚不能证明 |
| --- | --- | --- |
| [`projectReplanHistory`](../../loopx/control_plane/work_items/replan_history.ts) → [`build_replan_context`](../../loopx/control_plane/goals/goal_frontier/__init__.py) → action packet / [TurnEnvelope](../reference/protocols/turn-envelope-v0.md) | 进度、monitor 与复核事实经已有 quota/Host 调用进入 Agent | 模型读过、理解并遵循了每条指令 |
| [`strideReviewMismatch`](../../loopx/control_plane/work_items/stride_policy.ts) 与 [`replan_semantics`](../../loopx/control_plane/work_items/replan_semantics.ts) → Vision/ACK 结算 | 已开启的结构化路径复核绑定当前义务、上一决定及投递证据 | Agent 声明为真，或原 Turn 未结算时就能执行后继任务 |
| [`evaluateDeliveryRoute`](../../loopx/control_plane/turn_driver/delivery_continuity.ts) → 下一段合格工作 | 合格且被接受的 replan 后继可以优先于普通接续 | 模型确实采用新方法，或整个 Goal 已完成 |
| [`decisionFollowthrough`](../../loopx/control_plane/work_items/replan_context.ts) → 下一次复核 | 上次 accepted path 与随后记录的进度保持关联 | 执行与 Goal 收益；投影明确保留 `unknown` |
| [Explore 结果回写](../../loopx/capabilities/explore/result_writeback.py) → [turn context](../../loopx/capabilities/explore/turn_context.py) | 显式 finding 随普通 Todo/Turn 回写返回并影响后续判断输入 | 技能报告自动入库、科学结论为真，或完整前端附件提交/重试流程 |

[Goal Vision/replan 契约](../reference/protocols/goal-vision-replan-contract-v0.md)
定义启用方式与当前结算规则。`evidence_conditioned_v1` 可选且默认关闭，关闭时仍有
普通复核。此基线的结构化 fresh-path 检查，不意味着所有合法周期复核出口都强制同一
附件。边界变化时遵循所属契约；优化不能绕过已准入复核、quota 结算、权限、lease
或版本检查。

## 借鉴机制及其限制

以下是实现参考，不是性能对比结论；固定源码版本不代表安装版本。
借鉴职责、触发条件与失败场景，再适配现有归属。

| 公开源码快照 | 值得借鉴的机制 | LoopX 落点与限制 |
| --- | --- | --- |
| Grok Build `2bdd1d6a`：[Goal 循环](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/session/acp_session_impl/goal.rs)、[策略顾问](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-shell/src/session/goal_strategist.rs) | Host-owned Goal 路径在工作轮结束后评估，候选完成时复核，反复未达成时进行建议性的策略调查 | 沿已有 owner 区分继续、验收与方法调查；不照搬固定评审人数，也不假设额外模型调用改善质量或成本 |
| Codex `9167a0b2`：[工具与输入循环](https://github.com/openai/codex/blob/9167a0b2d4a74d44a4d388057d304682e47313c6/codex-rs/core/src/session/turn.rs)、[Goal 接续](https://github.com/openai/codex/blob/9167a0b2d4a74d44a4d388057d304682e47313c6/codex-rs/ext/goal/src/runtime.rs) | 工具结果和待处理输入驱动当前回合，生命周期扩展在空闲时启动合格 Goal 工作 | 复用 Host 执行与上下文维护；明确接续责任，避免原生 Goal 与外部 heartbeat 分别启动同一 attempt |
| OpenCode `be674e31`：[inbox](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/inbox.ts)、[执行协调器](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/run-coordinator.ts)、[子任务返回](https://github.com/anomalyco/opencode/blob/be674e3158abb5f1b0c16b2bdeb3a9ba2b072774/packages/core/src/session/subagent-completion.ts) | 当前工作纠正与排队任务分离；pending-wake 合并通知，覆盖 drain 到 idle 的竞态；子任务完成成为输入 | 扩展既有 inbox/session/Turn 投递；进程内单执行者不能替代跨主机 claim、lease 与采用证据 |
| Pi `e6220e13`：[Agent 循环](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/agent/src/agent-loop.ts)、[skills](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/coding-agent/docs/skills.md)、[subagent 扩展示例](https://github.com/earendil-works/pi/blob/e6220e1316f86af818a0ccbfe1c09d7e918b41cf/packages/coding-agent/examples/extensions/subagent/README.md) | 内层处理工具/steering，外层处理 follow-up；技能与复杂流程按需加载 | 普通工作不必依赖完整研究流程；扩展示例不等于默认产品支持、安全隔离或跨 Host 验收 |

Grok Build 新旧 Goal 路径的失败语义不同，旧路径包含基础设施失败时放行完成的行为，
不应作为 LoopX 验收的候选方案。不同项目相似的 Goal/turn 流程也不是独立实验验证：
Grok 的[第三方声明](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-tools/THIRD_PARTY_NOTICES.md)
明确有来自 Codex/OpenCode 的工具移植，但不能据此认定 Goal 循环同源。
这些客户端源码不能证明所有托管服务的实现，也不能保证任意外部操作恰好执行一次。

## 将探索接回执行，避免每项任务都变成研究

初始未知、新机会、用户方向或反例都可以触发探索。重复失败只是信号之一，不是前提，
也不自动要求换方法。选择技能或并行工作前，先说明调查可能改变什么决定。

| 未知 | 合适的工作 | 有用的返回 |
| --- | --- | --- |
| 现有实现及约束 | 定向源码阅读技能 | 已证实行为、可复用边界与限制 |
| 替代方法或外部依据 | 研究/搜索技能 | 候选、一手来源、适用条件与反证 |
| 候选是否适配项目 | 源码与研究结合的分析，或有界实验 | 能区分方案的结果、集成成本与采用条件 |

这些是工作方法分类，不是必装技能包或新路由 enum。选择能回答问题的最小方法。
子 Agent 在假设或信息来源不同时才有明确分工价值，摘要保留来源引用和未决问题。
研究报告本身可以完成研究任务，不必制造代码工作。

用 Explore 现有 `evidence` 模式保留发现，多候选分支确需只读选择支持时再用 `planning`。
模式不授予 claim、spawn 或执行权限。验证后可复用的发现通过既有 `explore_result`
附件或 `--explore-result-json` 随普通任务回写，包含测试输入版本、适用范围、观察、
解释和证据。兼容的 `path_delta` 可复用已有附件形式，避免重复同一叙述。
普通工作没有新发现时不需要填空 finding。

下一轮 context 和 `explore_review` 让 Agent 说明哪个发现支持换路、继续原路或合理复验。
反证限定在已测试条件内，保留当前最有依据的成果。输入不可读或测量未得出结论，都不
构成反驳。实际任务步骤、产物版本和独立验证才能支持采用声明，只有来源绑定还不够。

## 控制常态开销

先沿[优化证据指南](../development/testing-and-quality.md#roadmap-aligned-optimization)
测真实消费者，再选择抽象：

- 分开测重复调用、历史读取、序列化/跨语言成本、provider IO 和模型工作。
  返回短文本仍可能扫描完整来源；Explore 的有界 turn context 不承诺历史 IO 有界。
- 只在已证明的快照边界内复用事实，在所属准入/写入边界重新检查权限和版本。
  缓存不能成为另一个 writer；先消除已测到的重复读取/复制，再考虑缓存服务。
- 默认上下文保留决策所需事实与详情入口，相关时再读技能指令、完整证据和诊断。
  精简文案仍须保留顺序、来源、验收及停止义务。
- 暂态传输重试、上下文压缩、方法调整由各自 owner 处理。
  耗时或新标识不能证明进展；恢复沿原操作，未知效果先查询再重试。
- 总成本包含探索、评估、评审、压缩与 observer CPU/IO。
  可见响应更快不一定意味着总成本更低。

对受支持的长任务 profile，Stride §7.5 提议先进行无推理调用的观察，再由确切、
经过验证的结果推进现有 monitor generation，观察期限负责发现丢失事件。
不支持的 Host 保留当前路径并说明限制；本文不隐式抑制模型准入或修改 heartbeat 默认。

## 一次连贯的验收场景

选择一个受支持的 Host/profile 和隔离仓库任务：改进实现，同时保留约定命令和兼容合同。
整个场景保持原验收不变：

1. 开始有效工作，然后纠正实现方法但不弱化原要求；分别确认收到纠正和实际应用。
2. 调查一个相关未知，结果随普通回写返回。下一段已准入工作采用候选，或解释保留原方案
   的理由；检查实际产物与结果。
3. 将确切后台结果交给现有 monitor/resume owner。注入重复、乱序通知，以及消费者即将
   空闲时到达的通知。
4. 在结果已提交但尚未确认时中断，恢复原操作与当前 Goal 依据。覆盖来源版本变化、
   证据缺失及用户停止；旧结果不得重新启动已停止工作。
5. 独立验收后返回原会话。打包前端与 CLI 分开显示 queued、delivered、adopted、validated
   事实，缺失或陈旧证据不能保留成功标记。

现有[纠偏证据视图](../../apps/presentation/dashboard/src/features/personal-workspace/goal-team-episode.tsx)
可以核验显式产物/复核/修订/采用关系，不是所有 stride decision 的通用可视历史。
缺少前端附件提交/重试或决定到产物的连接时，仍是所属交付片段的配套工作；只有 CLI
的前置实现应说明为部分交付。

| 交付片段 | 既有归属与决定性证据 |
| --- | --- |
| 移除一处实测开销 | S2/S7/S10 与优化指南：同负载 base/head 比较，保留要求的语义、重放与真实后端检查 |
| 一次探索影响后续工作 | Explore 与 Stride §7.6：真实模型判断、当前证据、可归因产物和独立结果，也允许明确不换路 |
| 恢复一条 provider 结果/唤醒路径 | Stride §7.5、Host 与 monitor：受支持产品入口覆盖重复/丢失/迟到事件、重启、停止、来源变化及原操作回读 |

这些片段沿用现有路线图和 RFC 里程碑，不创建新任务账本，也不要求先完成无关迁移。
实现前核对相关当前工作：周期继承与复核约束、纠正重试身份、已有 codec/Explore
性能修复可能已覆盖部分范围。

测量验收质量、遗漏要求、总时间/tokens/成本、纠正到行动的延迟、恢复损失、重复效果
和用户注意力。固定源码、Host/model、任务/输入、权限、验收器和预算；保留失败及
未完成样本，区分冷/热路径和历史规模。评价候选前确定阈值。合成 fixture 验证机械链，
真实采用和对比收益需要各自证据；开销下降但验收或恢复变差，不算优化成功。

保持行为的常规性能修复可沿现有合同推进。改变默认准入、复核、保留、权限或结算，
则在所属 RFC/契约中说明兼容和回滚。可选策略在完成资格验证前保持有界；关闭策略
保留历史证据，不取消已准入工作，也不抹除恢复义务。
