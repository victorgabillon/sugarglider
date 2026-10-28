# Background Nature profiling and bounded preparation reuse

The accepted geographical installation remains unchanged. Physical testing of
83d27e7 confirms an 8 km improvement, but its four-entry cache does not satisfy
the 25 km background gate. The five-entry follow-up below still requires its own
exact-artifact authorization and physical acceptance. Issue #117 stays open.

## Measured working set

The original host replay used eight frozen candidate lines from a 25 km proposal
with seed 35. It was not the exact physical seed-0 portfolio. Four entries reduced
its preparations from 28 to nine, and Nature wall time from 10.9 s to 4.2 s.
This established a computation bottleneck, but underestimated the device fixture's
working set.

The exact physical 8 km fixture visits three partitions containing 1,206,838
positions. A four-entry / 1,500,000-position LRU prepares three rather than 26
partitions. The exact physical 25 km fixture visits five partitions containing
1,741,637 positions. The same LRU reads 47 partitions and prepares 34: its count
and position bounds both force repeated eviction during the five-partition cycle.
These are observed worker request sequences, including woodland proposal queries;
no route coordinates, descriptions or authority are included in profiling.

The follow-up retains at most **five prepared partitions and 2,000,000 positions**.
Replay of that exact access sequence prepares five partitions and records 42 hits.
A three-run Node VM preparation/cache replay measured median wall 75.31 s versus
11.65 s and all-thread CPU 82.32 s versus 13.08 s for four versus five entries.
Maximum retained heap after explicit GC was 153.6 versus 178.2 MiB; maximum sampled
process RSS was 789.3 versus 584.1 MiB. These are host preparation measurements,
not Nature-result timings, OPFS measurements, Android memory peaks or proof of
background completion. The shared engine, source bytes and access sequence were
identical; only cache bounds differed.

Eviction happens before incoming preparation, and visits are serialized, including
direct concurrent callers. Every hit still reads and hashes backing bytes against
the immutable manifest. Only decompression, parsing, validation and reconstruction
of previously validated identical bytes are reused. No source document is retained,
and region replacement or worker closure releases the session.

All intersecting partitions contribute exact intervals to one accumulator under
one unchanged operation budget. Polygon precedence, interval union, authoritative
distance normalization and fail-closed exhaustion are unchanged. Increasing cache
capacity cannot add routing calls, alter geometry or permit a partial Nature score.

## Physical evidence for the four-entry artifact

The installed WebView is 155.0.8059.43. Matched synthetic tests on 83d27e7 retain
the original seed, selected GPX bytes and native/model counts. Returned Nature
metrics agree across matched runs.
The two early attempts that failed before routing/Nature are excluded.

| Fixture / scenario | Nature | Whole operation | Second model hidden | Complete before return |
| --- | ---: | ---: | --- | --- |
| 8 km foreground, two runs | 3.40–3.55 s | 20.95–21.79 s | — | — |
| 8 km Home 180 s, two runs | 12.45–12.69 s | 32.27–32.63 s | yes | yes |
| 8 km Home 60 s | 12.63 s | 31.63 s | yes | yes |
| 8 km Settings switch 180 s | 13.20 s | 33.35 s | yes | yes |
| 25 km foreground, two runs | 21.31–23.45 s | 47.07–51.93 s | — | — |
| 25 km Home 180 s | 165.76 s | 204.15 s | no | no |
| 25 km Home 60 s | 45.91 s | 85.55 s | no | no |
| 25 km Settings switch 180 s | 165.83 s | 204.50 s | no | no |

A separate Home 25 km repetition with scheduler tracing reproduced the delay;
it is diagnostic evidence, excluded from performance statistics. In the first
Home case one synchronous validation span lasted 121.30 s. From approximately
60 to 170 s, the active Nature worker advanced only about 0.10 CPU seconds and
was sleeping at the latter sample. Android reported the renderer unfrozen and
in the foreground scheduling group at the sampled points. The wake lock and
calculation service remained owned. Queue and delivery measurements do not
account for the pause. This supports suspension within execution rather than
continuously expensive validation; it does not identify a particular Chromium
feature, GC mechanism or Android policy. Kernel wait-channel names were not
available to the shell. No hidden WebView evaluations, priority overrides or
unsupported flags were used.

Five-entry physical timing, secure-lock completion and the complete preservation
checks remain required before claiming the product blocker is fixed.

## Timing evidence

Profiling is off by default. The local module API supports an explicit diagnostic
session:

```js
const evidence = await import("/static/regional_performance.js");
evidence.enableRegionalProfiling();
// Run one explicitly started, synthetic-model calculation.
const snapshot = evidence.regionalPerformanceSnapshot();
evidence.enableRegionalProfiling(false);
```

The client and serialized production worker measure submission, queue waiting,
execution and delivery separately. Worker stages measure partition reads,
SHA-256 verification, bounded decompression, JSON parsing, partition validation,
topology/projection, index construction, intersections and final scoring.
Counters include preparations, cache hits and retained positions/partitions.
Main-thread events mark native route completion and the optional second model
submission. Clocks use time-origin-based epoch milliseconds for correlation.

Only fixed stage names, numeric counters/times and optional heap sizes are
accepted. There are no route coordinates, descriptions, account identifiers,
tokens, arbitrary exception messages or operation identifiers. At most 128
records are retained, in memory only. No polling or heartbeat is introduced.
Worker heap is explicitly unavailable where the runtime provides no heap API.
Wall time, especially asynchronous I/O wall time, must not be reported as CPU.
Each capture reset advances a generation. Late worker replies still deliver
their operation results, but cannot add timing records to a newer capture.

The opt-in Android calculation test runner accepts `-e nature_profile true`.
It collects the same bounded worker evidence after return, actual renderer
priority policy, and sparse main-process CPU/PSS samples at existing phase
boundaries. Model-start receipts carry wall and elapsed-realtime clocks. These
main-process samples are not renderer CPU or an aggregate app memory peak.
The runner does not evaluate the WebView during hidden intervals, modify
renderer policy, extend the existing service/wake-lock bounds or change OAuth,
microphone, cancellation and explicit process-death recovery rules.

## Scheduling evidence and remaining acceptance

Android's [renderer priority policy](https://developer.android.com/reference/android/webkit/WebView#setRendererPriorityPolicy(int,boolean))
controls OOM importance; its default is important regardless of visibility.
It is not a promise about worker task dispatch. Chromium separately has
[throttleable worker posted-message queues](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/platform/scheduler/worker/worker_scheduler_impl.cc)
and [conditional worker CPU/wakeup budgets](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/platform/scheduler/worker/worker_thread_scheduler.cc).
Those sources support a scheduling hypothesis, not proof that a particular
feature is enabled in the installed Fairphone WebView. No priority override,
Chromium flag, fake audio, invisible overlay or battery bypass is added.

For each exact accepted 8 km and 25 km fixture, repeat foreground, Home 60 s,
Home 180 s, app switch and secure lock 180 s. Use the existing socket-free
synthetic transport and identical request/seed. Preserve every account, route,
region and original GPX through the existing private acceptance procedure.
Installation and execution require authorization for the exact new APK and helper.

Record second model start and service completion before Activity return, GPX
hash, route/model counts, every Nature field and cancellation/interruption
outcomes. Correlate the profile with sparse renderer CPU/scheduling and memory
observations taken externally while hidden, without WebView evaluation. A long
submission/queue/delivery delay differs from CPU-heavy preparation; an async
stage's wall time alone cannot distinguish I/O wait from suspension. Do not
claim a root cause or guaranteed 180-second completion without those results.

Playwright enables focus emulation by default. A desktop scheduling experiment
must disable it through CDP, remove its background-throttling overrides and
assert genuine document visibility transitions. A completed calculation with a
still-visible document is invalid hidden-execution evidence. Browser events
assigned by test code and desktop tab tests are not Android lifecycle proof.

A separate real-OPFS desktop Chrome run with genuine tab visibility measured
11.0 s foreground / 41.2 s hidden for the one-entry control and 4.4 s foreground /
19.8 s hidden with four entries. All eight Nature results matched exactly.
Submission/queue/delivery totaled under 10 ms per run; most of this desktop
slowdown occurred within synchronous validation/projection. These are Nature-only
replays, not whole adventures or second-model invocations. Both finished during
their 180-second hidden interval. This single matched run needs repetition and
does not identify the Fairphone's much larger observed delay.

## Repeatable checks

`make check` and `tests/browser/nature_performance_acceptance.cjs` cover synthetic
geometry, cached/uncached exact equivalence, corruption after reuse, eviction,
shared operation exhaustion, concurrent visits, production OPFS worker profiling,
privacy limits, the five-partition cyclic working set, worker cancellation and region replacement. The existing full
adventure browser and Android checks cover model/native call budgets, exact GPX,
context consent, cancellation, account and microphone boundaries and recovery.

For private real-data CPU replay, supply an array of already returned candidate
objects (`geometry`, `distance_m`, `pack_id`); no backend or network is called:

```sh
node --experimental-default-type=module --expose-gc \
  scripts/benchmark_nature_partitions.mjs \
  --region /private/verified-region --routes /private/frozen-candidates.json \
  --cache-partitions 1 --repetitions 3 --output /private/control.json
# Repeat with --cache-partitions 5 and a different output path.
```

Use Node 22 or newer. Compare result hashes across cache sizes, then wall time,
all-thread process CPU, retained heap and process RSS. This benchmark measures
filesystem replay, not OPFS, the WebView renderer or Android background behavior.
Private inputs, output files, traces and screenshots stay outside Git. Issue #117
remains open until the full physical acceptance gate is satisfied.
