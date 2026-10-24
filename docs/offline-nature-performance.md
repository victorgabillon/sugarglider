# Bounded offline nature analysis

The offline analyzer retains the existing four-million-operation limit. It now
skips polygon parts and boundary blocks that cannot affect the routed edge,
point-in-polygon ray or 100 m water-proximity overlay.

Preparation adds polygon bounds and bounds for consecutive blocks of 64 segments
in rings longer than 64 segments. These records reference the existing projected
coordinates. Small rings keep the direct scan. The existing feature tree remains
unchanged; there is no route-result cache or second production analysis engine.
Water interiors are calculated once and reused for the primary class and overlay.

## Correctness and resource limits

Bounds are a conservative broad phase. Segment intersections, ray parity,
point-on-boundary predicates, exact circle/rectangle capsule intervals, hole
handling, interval unions, class priority, distance normalization and score
weights retain their existing mathematics. Contiguous blocks preserve segment
order. Bounds include the existing geometric predicates' numerical tolerance;
short edges also include their near-collinearity strip. The padding never changes
an exact predicate or expands the 100 m classification distance.

Every tested polygon/block bound and exact segment still consumes the shared
analysis budget. Exhaustion discards the whole result, leaving full unknown
distance and no score or overlays. The feature, position and topology-validation
limits are unchanged.

The validated two-million-position limit bounds construction and storage:

- A ring has at least four positions, bounding the number of ring/polygon records.
- Only rings with more than 64 segments receive blocks. There are fewer than
  62,500 blocks per region.
- Polygon/block bounds calculations visit at most three times the position
  limit, including shared block endpoints; they require no sorting or recursive
  construction.
- Index records belong only to the loaded regional analysis closure. No global
  cache, query cache or cross-region owner is introduced. Places-only sessions
  keep their independent name-search closure.

Installation validation does not build this planning-only index. Runtime loading
and analysis continue in the existing regional module worker. Closing a worker
rejects pending operations and releases its heap; loading another identity
replaces its analysis data. No new cancellation or lifecycle protocol is added.

## Regression coverage

Run the ordinary Python checks and the standalone browser acceptance:

```sh
uv run --offline make check
node tests/browser/nature_performance_acceptance.cjs
```

Provision Playwright/Chromium separately, as in `docs/development.md`.
`PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` can select existing installations.
The acceptance runs synthetic fixtures and real module-worker/OPFS operations;
it requires no map data, routing service, Android device or external network.

The test-only `nature_scan_reference.js` preserves the original full-ring
calculation from `d894ef7`. It is never imported by production or packaged into
Android. Fourteen synthetic cases demand exactly equal partitions, scores and
warnings in the same JavaScript engine, without loosening numerical tolerances.
They include dense woodland, complex water, holes, multipolygons, overlapping
priority classes, crossings, boundary following, exact water-distance tangencies,
outside coverage, 20,000 vertices, repeated segments and extremely short edges.
Existing independent Python golden tests remain unchanged.

Further cases reject malformed geometry, enforce fail-closed exhaustion under
pathological overlap, and check actual worker cancellation by closing, restart,
identity switching and removal. Explicit garbage collection verifies that a
retained Places-only session does not retain the analysis owner or nature
component. The existing PR40 stress fixture now repeatedly crosses the full
complex boundary: its former small interior oscillation became cheap after
pruning and no longer exercised exhaustion.

Private real-data replay inputs, coordinates, timings and memory evidence remain
outside Git. Replays compare frozen geometry without rerouting or rebuilding a
region. A complete full-scan oracle may exceed the runtime cap solely to establish
expected results for previously exhausted cases; the application and committed
regression reference both retain the four-million limit.
