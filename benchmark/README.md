# Benchmark research workspace

This is LoopX's workspace for active benchmark practice, narrow runner
examples, and explicitly identified immutable experiment archives. Its authority is the
[Long-Horizon Harness Benchmark and Research Program v0](../docs/architecture/rfcs/long-horizon-harness-benchmark-research-program-v0.md).

The workspace follows three rules:

1. benchmark-native task, runner, verifier, and score semantics remain
   authoritative;
2. current real-run practice outranks legacy LoopX benchmark abstractions;
3. active work admits only generalized code and public-safe conclusions;
   immutable historical experiment snapshots may also be stored here under
   the archive placement rules below, without becoming active practice.

Reusable product policy stays in
[`benchmark-toolkit`](../loopx/capabilities/benchmark_toolkit/README.md). The
toolkit owns provider-neutral permission, artifact, and integrity boundaries.
This directory may contain thin examples and practice notes, but it is not
installed as a second LoopX Python package and does not grant execution or
publication authority.

## Engineering build map

The canonical engineering plan is [Section 11 of the English research
RFC](../docs/architecture/rfcs/long-horizon-harness-benchmark-research-program-v0.md#11-engineering-construction-plan)
and [中文第 11 节](../docs/architecture/rfcs/long-horizon-harness-benchmark-research-program-v0.zh-CN.md#11-工程建设计划).
It separates repository readiness from benchmark claims:

- **E0--E1:** typed contracts, public/private boundaries, native runner
  preflight, and one conformance slice;
- **E2:** experiment-board lifecycle, concurrency admission, exact runtime
  observation, continuity, reconciliation, and safe closeout;
- **E3:** preregistered matched arms, treatment fidelity, integrity,
  countability, and uncertainty;
- **E4:** cross-benchmark replication and non-benchmark product qualification.

The active workspace should keep benchmark-family launch, verifier, scoring, and
failure semantics in adapters while reusable permission, integrity, lifecycle,
and public-safe projection rules stay in
[`benchmark-toolkit`](../loopx/capabilities/benchmark_toolkit/README.md).
Contributors should start with a bounded synthetic fixture or conformance seam;
live tasks, hidden evaluation, credentials, raw trajectories, submissions, and
unpublished comparisons remain maintainer-owned. Engineering readiness does not
by itself establish a C2 uplift claim.

## Current work

- **LHTB result highlight:** GPT-5.6 Sol + LoopX 1.0.3 Heartbeat reaches
  **0.4948 mean reward** on 46 tasks: **+17.3% vs Plain Codex** and
  **+10.6% vs native Codex Goal**. Strict solves are 7/46, matching Plain and
  above Goal's 4/46. At the supplementary post-hoc threshold ≥0.80, LoopX /
  Plain / Goal reach **15/46 / 12/46 / 14/46** (32.6% / 26.1% / 30.4%);
  no score equals 0.80 in this study. One effective trial per task-arm, designated replacements
  and unequal execution budgets make this an exploratory system comparison,
  not an equal-budget efficiency or isolated causal result.
  [Full comparison and limits](LHTB/studies/five-arm-gpt56sol-max/README.md)
  · [Interactive brief](https://loopx-project.github.io/loopx/benchmarks/lhtb/)
  · [LHTB official website](https://zli12321.github.io/LHTB/index.html).
- [`swe-marathon/README.md`](swe-marathon/README.md) links the published
  [SWE-Marathon research brief](https://huangruiteng.github.io/loopx/benchmarks/swe-marathon/).
- [`LHTB/studies/five-arm-gpt56sol-max/README.md`](LHTB/studies/five-arm-gpt56sol-max/README.md)
  documents the public-safe aggregate behind the bilingual
  [LHTB research brief](https://huangruiteng.github.io/loopx/benchmarks/lhtb/).
- [`deepswe/behavior-discovery/README.md`](deepswe/behavior-discovery/README.md)
  links the standalone
  [DeepSWE behavior-discovery article](https://huangruiteng.github.io/loopx/benchmarks/deepswe/behavior-discovery/).
  It publishes scoped exploratory findings and permitted duration comparisons,
  not the complete study outcome table.
- [`deepswe/README.md`](deepswe/README.md) records the current public-safe
  DeepSWE method: frozen selection, matched-arm authority, native Goal proof,
  independent verification, invalid-run replacement, and compact evidence.
- [`native_codex_goal.py`](native_codex_goal.py) is a compatibility import for
  the benchmark toolkit's installed native Goal runtime. The runnable
  [`deepswe/run_native_codex_goal.py`](deepswe/run_native_codex_goal.py) example
  connects that runtime to a real `codex app-server`. Benchmark-family adapters
  should import the installed runtime and its formal isolated profile helper,
  then retain only their isolation, environment bridge, verifier, and scoring
  concerns. The profile helper renders the real Goal prompt with its installed
  CLI and proves that the prompt, discovered skills, and release-snapshot CLI
  belong to one pinned product path.

## Archive placement

This section owns benchmark archive placement. Two kinds of archive have
different homes:

- The retired benchmark implementation, legacy abstractions, and standalone
  dated research packets belong under
  [`deprecate/benchmark-legacy/`](../deprecate/benchmark-legacy/README.md).
- A named, immutable experiment snapshot may live in a versioned directory
  under `benchmark/` when its exact source bytes are needed to inspect a
  historical result. This is a historical reference, not an active runner,
  reusable implementation, or entry in the Current work list.

An experiment snapshot stored here must meet all of these conditions:

1. Its files are public-safe: no credentials, private configuration, raw task
   text, trajectories, or private evidence.
2. Companion documentation outside the frozen tree identifies its version,
   provenance and provenance limits, runtime dependencies, and known defects.
   Applicable withdrawn-result notices appear at the beginning of that document.
3. A pinned content hash and a read-only check verify the preserved bytes and
   executable modes. The check states its coverage; identity or syntax checks
   do not prove runtime correctness or validate historical scores.
4. The snapshot remains inert: no product imports, automatic task/model
   execution, or active CI benchmark runs. Later execution fixes require a
   separately identified change and must not overwrite the historical bytes
   or inherit their result attribution.

The [DeepSWE GPT xhigh v1 archive note](deepswe-gptxhigh-versions.md) registers
`deepswe-gptxhigh-v1/` under this rule. Its original files and result table are
preserved for inspection; the companion notice governs their current evidence
status. Neither archive category is the architecture for new work or grants
runner, verifier, submission, or publication authority.

## Inert checkpoint capture

This is a developer prerequisite for the [research checkpoint contract](../docs/architecture/rfcs/hierarchical-agent-stride-control-v0.md#77-research-state-branching-and-matched-continuation),
not a qualified research continuation. The programmatic `BenchmarkCodex` and
heartbeat `SForgeWorker` adapters accept an explicit `checkpoint_request_path`
to a normalized absolute **guest** JSON file. Stage that file through the existing
environment transport. Ambient host variables do not enable capture; omitting
the option disables the hook. The EdgeBench CLI does not expose this option yet.

The request contains exactly these fields; select only authorized private
artifacts and exclude credentials and hidden evaluation material:

```json
{
  "destination": "/logs/agent/checkpoints/research-point",
  "components": [
    {"id": "code", "source_path": "/workspace/solution.py"},
    {"id": "evidence", "source_path": "/control/source-evidence.json"}
  ],
  "point_metadata": {"purpose": "inert source capture"}
}
```

The destination must be a new direct child of the trial log owner's
`checkpoints` directory. Capture runs after a successful execute wake's original
settlement, before the next wake. It uses the remaining phase budget with a
30-second capture ceiling, preserves SQLite's committed WAL through the existing
backup owner, rejects observed source changes/symlinks and never overwrites a
destination. Capture failures are recorded separately in the wake receipt;
they do not replay work or change its settled outcome. The ceiling bounds
publication eligibility and RPC waits, not an operating-system I/O cancellation
guarantee. Capture cost remains part of the trial's elapsed time.

For readback, call the existing `effect_runtime_result` adapter with method
`runtime.checkpoint_artifacts`, action `verify`, the captured `root` and the
receipt's `expected_sha256`. Action `materialize` with those fields and a new
`destination` verifies and copies the unit into isolation. Neither action adopts
state or starts execution. The new `loopx_checkpoint_artifact_set_v0` manifest
is an internal artifact contract; `point_metadata` is unverified evidence.
`research_point_qualified`, `execution_authority_granted` and `privacy_certified`
remain false. Integrity checks cover the declared members and observed stable
source boundary, not adversarial filesystem mutation or a cross-owner transaction.
Native session reconstruction, effect reconciliation, fresh authority admission
and evaluator cooldown/opportunity inheritance must pass before matched continuation.

这是研究 checkpoint 的开发前置切片。仅 programmatic adapter 的显式 guest
请求路径会开启捕获，省略该参数即关闭；当前 EdgeBench CLI 尚无此选项。产物
验证和隔离物化不授予执行权，不代表研究点已资格化。请求中的 metadata 只是
证据，不能代替会话、效果、状态采用及评测机会的联合验收。
