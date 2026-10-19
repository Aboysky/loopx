import type { TrialMeasurement } from './overhead-runner.ts'

export interface ArmSummary {
  readonly trials: number
  readonly cpu_total_ms_median: number
  readonly cpu_total_ms_p95: number
  readonly cpu_ms_per_1k_events_median: number
  readonly rss_delta_bytes_median: number
  readonly ledger_bytes_per_event: number
  readonly append_p50_ms: number
  readonly append_p95_ms: number
  readonly persisted_events_median: number
}

export interface OverheadReportEnvironment {
  readonly node: string
  readonly platform: string
  readonly arch: string
  readonly cpus: number
  readonly total_memory_gib: number
}

export interface OverheadReportConfig {
  readonly events: number
  readonly repeat: number
  readonly buffer_bound: number
  readonly event_mix: string
}

export interface OverheadIntegrity {
  readonly count_conservation: boolean
  readonly outbound_endpoints_empty: boolean
  readonly worker_context_influence_absent: boolean
  readonly scheduler_input_influence_absent: boolean
  readonly observer_failures: number
  readonly persisted_envelopes: number
}

export interface OverheadEventAccounting {
  readonly observed_events_median: number
  readonly accepted_events_median: number
  readonly persisted_events_median: number
  readonly dropped_events_median: number
  readonly rejected_events_median: number
  readonly flush_attempts_median: number
  readonly clock_uncertainty_max_ms_median: number
}

export interface OverheadDelta {
  readonly cpu_ms_per_1k_events: number
  readonly rss_delta_bytes: number
  readonly append_p95_ms: number
}

export interface OverheadReport {
  readonly schema: 'reliability_observer_overhead_report_v0'
  readonly generated_at: string
  readonly environment: OverheadReportEnvironment
  readonly config: OverheadReportConfig
  readonly arms: {
    readonly baseline: { readonly summary: ArmSummary; readonly trials: readonly TrialMeasurement[] }
    readonly observer: { readonly summary: ArmSummary; readonly trials: readonly TrialMeasurement[] }
  }
  readonly delta: OverheadDelta
  readonly integrity: OverheadIntegrity
  readonly event_accounting: OverheadEventAccounting
  readonly limits: readonly string[]
}

export interface OverheadReportInput {
  readonly config: OverheadReportConfig
  readonly baseline: readonly TrialMeasurement[]
  readonly observer: readonly TrialMeasurement[]
  readonly environment: OverheadReportEnvironment
  readonly generatedAt?: string
}

const REPORT_LIMITS = [
  'Synthetic event stream only; this is not a live DSH host, model, or network measurement.',
  'Measures observer component cost (event compaction, envelope construction, JSON serialization, and ledger append); excludes Cordis hook dispatch, DSH scheduling, model, and network.',
  'The synthetic turn cycle has six events per turn and flushes on every turn end; a real long turn flushes less often, so the per-event append cost here is a flush-heavy microbenchmark, not a workload forecast.',
  'Baseline is an empty synthetic driver; the delta is the observer component cost, not a claim about a real worker throughput.',
  'RSS is process-level and may move with GC; use repeats and medians, not a single sample.',
  'A C1 eligibility or P0-exit claim requires a separately authorized live run and maintainer acceptance.',
] as const

export function percentile(values: readonly number[], fraction: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const bounded = Math.min(1, Math.max(0, fraction))
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(bounded * sorted.length) - 1))
  return sorted[index] ?? 0
}

export function median(values: readonly number[]): number {
  return percentile(values, 0.5)
}

export function summarizeTrials(trials: readonly TrialMeasurement[]): ArmSummary {
  if (trials.length === 0) {
    return {
      trials: 0,
      cpu_total_ms_median: 0,
      cpu_total_ms_p95: 0,
      cpu_ms_per_1k_events_median: 0,
      rss_delta_bytes_median: 0,
      ledger_bytes_per_event: 0,
      append_p50_ms: 0,
      append_p95_ms: 0,
      persisted_events_median: 0,
    }
  }
  const cpuPer1k = trials.map(trial => trial.workloadEvents === 0
    ? 0
    : (trial.cpuTotalMs / trial.workloadEvents) * 1_000)
  const appendLatencies = trials.flatMap(trial => trial.appendLatenciesMs)
  const totalLedgerBytes = trials.reduce((sum, trial) => sum + trial.ledgerBytes, 0)
  const totalPersisted = trials.reduce((sum, trial) => sum + trial.persistedEvents, 0)
  return {
    trials: trials.length,
    cpu_total_ms_median: median(trials.map(trial => trial.cpuTotalMs)),
    cpu_total_ms_p95: percentile(trials.map(trial => trial.cpuTotalMs), 0.95),
    cpu_ms_per_1k_events_median: median(cpuPer1k),
    rss_delta_bytes_median: median(trials.map(trial => trial.rssDeltaBytes)),
    ledger_bytes_per_event: totalPersisted === 0 ? 0 : totalLedgerBytes / totalPersisted,
    append_p50_ms: percentile(appendLatencies, 0.5),
    append_p95_ms: percentile(appendLatencies, 0.95),
    persisted_events_median: median(trials.map(trial => trial.persistedEvents)),
  }
}

export function buildOverheadReport(input: OverheadReportInput): OverheadReport {
  const baselineSummary = summarizeTrials(input.baseline)
  const observerSummary = summarizeTrials(input.observer)
  return {
    schema: 'reliability_observer_overhead_report_v0',
    generated_at: input.generatedAt ?? new Date().toISOString(),
    environment: input.environment,
    config: input.config,
    arms: {
      baseline: { summary: baselineSummary, trials: input.baseline },
      observer: { summary: observerSummary, trials: input.observer },
    },
    delta: {
      cpu_ms_per_1k_events: observerSummary.cpu_ms_per_1k_events_median
        - baselineSummary.cpu_ms_per_1k_events_median,
      rss_delta_bytes: observerSummary.rss_delta_bytes_median
        - baselineSummary.rss_delta_bytes_median,
      append_p95_ms: observerSummary.append_p95_ms - baselineSummary.append_p95_ms,
    },
    integrity: {
      count_conservation: input.observer.every(trial => trial.observedEvents
        === trial.acceptedEvents + trial.rejectedEvents + trial.droppedEvents),
      outbound_endpoints_empty: input.observer.every(trial => trial.outboundEndpoints === 0),
      worker_context_influence_absent: input.observer.every(trial => !trial.workerContextInfluence),
      scheduler_input_influence_absent: input.observer.every(trial => !trial.schedulerInputInfluence),
      observer_failures: input.observer.reduce((sum, trial) => sum + trial.observerFailures, 0),
      persisted_envelopes: input.observer.reduce((sum, trial) => sum + trial.persistedEvents, 0),
    },
    event_accounting: {
      observed_events_median: median(input.observer.map(trial => trial.observedEvents)),
      accepted_events_median: median(input.observer.map(trial => trial.acceptedEvents)),
      persisted_events_median: median(input.observer.map(trial => trial.persistedEvents)),
      dropped_events_median: median(input.observer.map(trial => trial.droppedEvents)),
      rejected_events_median: median(input.observer.map(trial => trial.rejectedEvents)),
      flush_attempts_median: median(input.observer.map(trial => trial.flushAttempts)),
      clock_uncertainty_max_ms_median: median(input.observer.map(trial => trial.clockUncertaintyMaxMs)),
    },
    limits: REPORT_LIMITS,
  }
}

function formatNumber(value: number, digits = 2): string {
  return Number.isFinite(value) ? value.toFixed(digits) : 'n/a'
}

function formatInteger(value: number): string {
  return Number.isFinite(value) ? Math.round(value).toLocaleString('en-US') : 'n/a'
}

function formatBytes(value: number): string {
  const sign = value < 0 ? '-' : ''
  const absolute = Math.abs(value)
  if (absolute < 1_024) return `${sign}${absolute.toFixed(0)} B`
  if (absolute < 1_024 ** 2) return `${sign}${(absolute / 1_024).toFixed(1)} KiB`
  return `${sign}${(absolute / 1_024 ** 2).toFixed(1)} MiB`
}

function status(value: boolean): string {
  return value ? 'passed' : 'failed'
}

export function renderMarkdown(report: OverheadReport): string {
  const baseline = report.arms.baseline.summary
  const observer = report.arms.observer.summary
  return `# Observer overhead (synthetic DSH session)

- Generated: ${report.generated_at}
- Node: ${report.environment.node}
- Platform: ${report.environment.platform}/${report.environment.arch}
- CPUs: ${report.environment.cpus}
- Memory: ${formatNumber(report.environment.total_memory_gib, 1)} GiB
- Events per trial: ${formatInteger(report.config.events)}
- Repeats per arm: ${formatInteger(report.config.repeat)}
- Buffer bound: ${formatInteger(report.config.buffer_bound)}
- Event mix: ${report.config.event_mix}

| Metric | Baseline | Observer | Delta |
| --- | ---: | ---: | ---: |
| CPU total, median (ms) | ${formatNumber(baseline.cpu_total_ms_median)} | ${formatNumber(observer.cpu_total_ms_median)} | ${formatNumber(observer.cpu_total_ms_median - baseline.cpu_total_ms_median)} |
| CPU, median (ms / 1k events) | ${formatNumber(baseline.cpu_ms_per_1k_events_median)} | ${formatNumber(observer.cpu_ms_per_1k_events_median)} | ${formatNumber(report.delta.cpu_ms_per_1k_events)} |
| RSS delta, median | ${formatBytes(baseline.rss_delta_bytes_median)} | ${formatBytes(observer.rss_delta_bytes_median)} | ${formatBytes(report.delta.rss_delta_bytes)} |
| Ledger append p50 (ms) | n/a | ${formatNumber(observer.append_p50_ms)} | n/a |
| Ledger append p95 (ms) | n/a | ${formatNumber(observer.append_p95_ms)} | n/a |
| Ledger bytes / persisted event | n/a | ${formatNumber(observer.ledger_bytes_per_event)} | n/a |
| Persisted envelopes, median | n/a | ${formatInteger(observer.persisted_events_median)} | n/a |
| Clock uncertainty max, median (ms) | n/a | ${formatNumber(report.event_accounting.clock_uncertainty_max_ms_median)} | n/a |

## Event accounting (observer, median)

| Observed | Accepted | Persisted | Dropped | Rejected | Flush attempts |
| ---: | ---: | ---: | ---: | ---: | ---: |
| ${formatInteger(report.event_accounting.observed_events_median)} | ${formatInteger(report.event_accounting.accepted_events_median)} | ${formatInteger(report.event_accounting.persisted_events_median)} | ${formatInteger(report.event_accounting.dropped_events_median)} | ${formatInteger(report.event_accounting.rejected_events_median)} | ${formatInteger(report.event_accounting.flush_attempts_median)} |

## Integrity

- Count conservation: ${status(report.integrity.count_conservation)}
- Outbound endpoints empty: ${status(report.integrity.outbound_endpoints_empty)}
- Worker-context influence absent: ${status(report.integrity.worker_context_influence_absent)}
- Scheduler-input influence absent: ${status(report.integrity.scheduler_input_influence_absent)}
- Observer failures: ${formatInteger(report.integrity.observer_failures)}
- Persisted envelopes: ${formatInteger(report.integrity.persisted_envelopes)}

## Limits

${report.limits.map(limit => `- ${limit}`).join('\n')}
`
}
