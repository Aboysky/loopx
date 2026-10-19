import { describe, expect, it } from 'vitest'
import {
  buildEventPlan,
  normalizeEventCount,
  runBaselineTrial,
  runObserverTrial,
} from '../bench/overhead-runner.ts'
import type { PlannedEvent } from '../bench/overhead-runner.ts'
import {
  buildOverheadReport,
  percentile,
  renderMarkdown,
  summarizeTrials,
} from '../bench/overhead-report.ts'

const environment = {
  node: 'v-test',
  platform: 'test',
  arch: 'test',
  cpus: 1,
  total_memory_gib: 1,
}

describe('observer overhead event plan', () => {
  it('normalizes to whole turn cycles and pins the stream shape', () => {
    expect(normalizeEventCount(0)).toBe(6)
    expect(normalizeEventCount(10)).toBe(6)
    expect(normalizeEventCount(13)).toBe(12)
    const plan = buildEventPlan(12)
    expect(plan).toHaveLength(14)
    expect(plan[0]?.kind).toBe('created')
    expect(plan.at(-1)?.kind).toBe('disposed')
    const eventTypes = plan
      .filter((planned): planned is Extract<PlannedEvent, { kind: 'event' }> => planned.kind === 'event')
      .map(planned => planned.event.type)
    expect(eventTypes).toEqual([
      'turn/start', 'step/start', 'tool/call', 'tool/result', 'step/end', 'turn/end',
      'turn/start', 'step/start', 'tool/call', 'tool/result', 'step/end', 'turn/end',
    ])
  })

  it('keeps percentile boundaries deterministic', () => {
    expect(percentile([], 0.5)).toBe(0)
    expect(percentile([1, 2, 3, 4], 0.5)).toBe(2)
    expect(percentile([1, 2, 3, 4], 0.95)).toBe(4)
    expect(percentile([4, 1, 3, 2], 0.5)).toBe(2)
  })
})

describe('observer overhead trials', () => {
  it('measures observer component cost with full denominators', async () => {
    const trial = await runObserverTrial({ inputEvents: 60, bufferBound: 8 })
    expect(trial.workloadEvents).toBe(60)
    expect(trial.observedEvents).toBe(62)
    expect(trial.observedEvents).toBe(
      trial.acceptedEvents + trial.rejectedEvents + trial.droppedEvents,
    )
    expect(trial.persistedEvents).toBeGreaterThan(0)
    expect(trial.ledgerBytes).toBeGreaterThan(0)
    expect(trial.clockUncertaintyMaxMs).toBe(50)
    expect(trial.appendLatenciesMs.length).toBeGreaterThan(0)
    expect(trial.outboundEndpoints).toBe(0)
    expect(trial.workerContextInfluence).toBe(false)
    expect(trial.schedulerInputInfluence).toBe(false)
  })

  it('counts append failures without throwing or persisting controls', async () => {
    const trial = await runObserverTrial({
      inputEvents: 12,
      bufferBound: 4,
      failAppend: true,
    })
    expect(trial.observerFailures).toBeGreaterThan(0)
    expect(trial.persistedEvents).toBe(0)
    expect(trial.observedEvents).toBe(
      trial.acceptedEvents + trial.rejectedEvents + trial.droppedEvents,
    )
    expect(trial.outboundEndpoints).toBe(0)
  })

  it('renders a public-safe report with both arms and integrity status', async () => {
    const baseline = [runBaselineTrial({ inputEvents: 12, bufferBound: 8 })]
    const observer = [await runObserverTrial({ inputEvents: 12, bufferBound: 8 })]
    expect(summarizeTrials(baseline).trials).toBe(1)
    expect(summarizeTrials(observer).trials).toBe(1)
    const report = buildOverheadReport({
      config: { events: 12, repeat: 1, buffer_bound: 8, event_mix: 'turn-cycle-v1' },
      baseline,
      observer,
      environment,
      generatedAt: '2026-10-19T00:00:00.000Z',
    })
    expect(report.schema).toBe('reliability_observer_overhead_report_v0')
    expect(report.integrity.count_conservation).toBe(true)
    expect(report.integrity.outbound_endpoints_empty).toBe(true)
    expect(report.integrity.worker_context_influence_absent).toBe(true)
    expect(report.integrity.scheduler_input_influence_absent).toBe(true)
    expect(report.event_accounting.observed_events_median).toBe(14)
    expect(report.event_accounting.clock_uncertainty_max_ms_median).toBe(50)
    expect(Number.isFinite(report.delta.cpu_ms_per_1k_events)).toBe(true)
    expect(Number.isFinite(report.delta.rss_delta_bytes)).toBe(true)
    const markdown = renderMarkdown(report)
    expect(markdown).toContain('Observer overhead')
    expect(markdown).toContain('Count conservation: passed')
    expect(markdown).not.toContain('session-observer-overhead-fixture')
    expect(markdown).not.toContain('goal-observer-overhead-fixture')
    expect(JSON.stringify(report)).not.toContain('session-observer-overhead-fixture')
    expect(JSON.stringify(report)).not.toContain('goal-observer-overhead-fixture')
  })
})
