# Background Nature profiling and bounded preparation reuse

The accepted Île-de-France installation remains unchanged. This change addresses
one measured computation cost and adds evidence to separate it from Android
scheduling. Fairphone acceptance of the replacement APK is still required;
desktop replay cannot establish completion during Home or secure lock.

## Confirmed computation cost

Eight distinct retained native candidate lines from the deterministic 25 km
acceptance request intersect two to five Nature partitions each. The original
one-entry cache prepares 28 partitions. In a Node replay, 28 ms was spent reading
files, compared with approximately 5.1 s in projection/topology validation,
1.9 s in JSON parsing and 1.4 s rebuilding spatial indexes. Geometry intersection
took about 0.6 s. Total Nature wall time was 10.9 s.

A deterministic LRU of at most four prepared partitions reduces preparations
to nine and this replay to 4.2 s. Every returned Nature field, including exact
category distances, score and operation count, matches the control. Separate
explicit-GC Node runs measured maximum retained JS heap of 47.8 MiB for one
partition and 154.6 MiB for four. Whole-process peak RSS was approximately
505 MiB and 465 MiB respectively: allocation/GC peaks are distinct from retained
heap, and neither measurement is an Android memory result.

The cache additionally caps retained geometry at 1,500,000 positions. It evicts
before preparing an incoming partition and serializes visits, including direct
concurrent callers. A cache hit still reads and hashes its backing bytes against
the immutable manifest; it skips decompression, parsing, topology validation and
tree reconstruction only for the same fully validated bytes. No source document
is retained. Region replacement and worker closure release the session.

All intersecting partitions still contribute exact intervals to one accumulator
with one unchanged operation budget. Class precedence, interval union, distance
normalization, polygon mathematics and fail-closed exhaustion are unchanged.
There is no averaging, partial score, route-result cache, new routing call,
geographical rebuild or extra copy of the installed dataset.

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
privacy limits, worker cancellation and region replacement. The existing full
adventure browser and Android checks cover model/native call budgets, exact GPX,
context consent, cancellation, account and microphone boundaries and recovery.

For private real-data CPU replay, supply an array of already returned candidate
objects (`geometry`, `distance_m`, `pack_id`); no backend or network is called:

```sh
node --experimental-default-type=module --expose-gc \
  scripts/benchmark_nature_partitions.mjs \
  --region /private/verified-region --routes /private/frozen-candidates.json \
  --cache-partitions 1 --repetitions 3 --output /private/control.json
# Repeat with --cache-partitions 4 and a different output path.
```

Use Node 22 or newer. Compare result hashes across cache sizes, then wall time,
all-thread process CPU, retained heap and process RSS. This benchmark measures
filesystem replay, not OPFS, the WebView renderer or Android background behavior.
Private inputs, output files, traces and screenshots stay outside Git. Issue #117
remains open until the full physical acceptance gate is satisfied.
