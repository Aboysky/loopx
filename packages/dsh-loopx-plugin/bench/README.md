# Observer overhead bench

Measure the DSH shadow observer's component cost on a deterministic synthetic
event stream. This is a development tool for the P0 "measured overhead" gap in
[#5211](https://github.com/loopx-project/loopx/issues/5211); it is not a live
DSH host, model, or C1 qualification.

## What it measures

- **Two arms**: the same event stream with the observer disabled (baseline) and
  enabled (observer).
- **CPU**: `process.cpuUsage()` user + system delta.
- **RSS**: process RSS before/after each trial.
- **Ledger append**: p50/p95 latency and bytes written per persisted envelope.
- **Event accounting**: observed, accepted, persisted, dropped, rejected, peak
  buffer, and flush attempts. Counts must satisfy
  `observed = accepted + rejected + dropped`.
- **Integrity**: no outbound endpoints, no worker-context influence, and no
  scheduler-input influence.

The report is public-safe: it contains aggregate numbers, the Node/platform
version, and limits. It does not contain goal ids, session ids, ledger paths, or
raw event content.

## Run

From `packages/dsh-loopx-plugin`:

```bash
node --experimental-strip-types bench/observer-overhead.ts \
  --events 10000 --repeat 5 --buffer-bound 256 \
  --json ../../.local/observer-overhead.json \
  --markdown ../../.local/observer-overhead.md
```

Defaults are 5,000 events, 3 repeats, and a buffer bound of 256. The tool runs a
short warmup, then alternates baseline and observer trials. Use `--json -` or
`--markdown -` to print a report to stdout.

Example output from one Windows/Node 26 run (numbers are machine-specific and
are not a qualification):

```text
| Metric | Baseline | Observer | Delta |
| --- | ---: | ---: | ---: |
| CPU total, median (ms) | 0.0 | 609.0 | 609.0 |
| CPU, median (ms / 1k events) | 0.0 | 121.9 | 121.9 |
| RSS delta, median | 204.0 KiB | 8.2 MiB | 8.0 MiB |
| Ledger append p95 (ms) | n/a | 2.68 | n/a |
| Ledger bytes / persisted event | n/a | 521.6 | n/a |
| Persisted envelopes, median | n/a | 5,000 | n/a |
```

The synthetic turn cycle has six events per turn and flushes on every turn
end, so it is deliberately flush-heavy. A real long turn flushes less often;
use the per-event numbers as a bound/signal, not a workload forecast.


## What it deliberately does not measure

- Cordis hook dispatch or DSH scheduling;
- model, network, or tool latency;
- a real session's worker outcome;
- C1 eligibility or P0 exit.

Those require a separately authorized live run and maintainer acceptance. See
the [capability README](../../../loopx/capabilities/reliability_diagnostics/README.md)
and the [RFC](../../../docs/architecture/rfcs/long-running-agent-reliability-diagnostics-governed-delivery-v0.md).

## Test

```bash
pnpm test -- observer-overhead
```

The test covers the event-plan shape, percentile boundaries, count
conservation, append-failure accounting, and public-safe report rendering.
