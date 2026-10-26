# AI Adventure woodland quality — 26 October 2026

Strong woodland preferences now change both bounded exploration and measured
selection. In the latest-place Marly fixture, best retained woodland rises from
20.8% to **54.2%**, with a **50.7% woodland variant visiting three checked places**.
The variant shares its forest loop; it is not counted as another independent
family. The primary route-quality criterion is satisfied on actual native lines
in four matched forest cases. Three predominantly wooded historical loops are
not established, and some fixtures trade visits for woodland.

This continues PR #110 from `88bdb8c`, preserving the existing Android, account,
speech, research, publication, GPX and recovery architecture. The Fairphone and
connected ChatGPT account were **not accessed** for this work. The installed
ea746cf staging build and original 23.172 km route remain untouched. Historical
physical evidence remains in the [Fairphone report](ai-adventure-fairphone-stabilization-acceptance.md).

## What the retained evidence establishes

The private inventory recovered 248 native receipts, 51 unique native lines and
99 retained candidate instances. All receipts decoded without a native error.
Where geometry survives, the audit recomputes authoritative distance, geometry
identity, loop metrics, Nature partition, visits and retention matches. Later
physical runs retained sanitized summaries rather than every intermediate line;
their missing stages cannot be reconstructed exactly.

The earlier 54.8% line is recoverable in `finish-search-3.json`, including its
native receipt: 36.455 km, one checked Château de Marly approach, 54.775% woodland,
23.149% urban, 17.477% unknown and loop penalty 1.134. It is within that fixture's
35 km ±3 km tolerance, neither degenerate nor a severe out-and-back. It was an
actual retained exploratory candidate, not proof that the latest model proposal
could reproduce it. Neither its coordinates nor its route identity seed the new
search.

Baseline instrumentation on the same private graph pinpoints these losses:

| Stage | Evidence and cause |
| --- | --- |
| Before Nature | The curated 35 km fixture's valid 36.222 km control has 46.2% woodland when audited afterward, but the control/optional shortlist omits it before Nature. Another 36.787 km control with 41.5% is omitted in round two. |
| Diversity/shortlist | Baseline filtering compares sampled native lines before Nature and caps the enriched pool at five. Private traces record 17 diversity omissions across the six baseline runs; the split between similarity and shortlist reasons is inferred from the logged pool and original predicates, not an invented old physical event log. |
| Final candidate selection | Exact floating loop penalty precedes every measured wish. A modest shape difference can defeat a large woodland gain. The no-POI comparison also occupies a requested alternative slot. |
| Publication | Search omissions are already irreversible. The publisher preserves its existing no-POI promotion gate; no evidence showed it independently inventing a woodland rejection. Its adventure cap could also crowd out an extra useful variant. |
| Comparing rounds | In the latest-place fixture, round two's 34.3% best woodland loses to a round containing a 12.0% line with better shape. In the curated fixture, round one's 43.1%/46.6% set loses to round two's 15.6%/17.5%/42.0% set. The comparator chooses a round by its best assessed line, with shape ahead of woodland. |

The separate original physical observation was 20.8%/15.8%/19.8%, followed by a
rejected 34.3%/32.2%/21.1% round. Those numbers remain physical evidence; the new
deterministic fixture is not falsely presented as its exact replay.

## Small, bounded changes

Only an explicit high/hard woodland maximize/prefer wish, or a high/hard woodland
target of at least 50%, activates this behavior. Ordinary adventure wishes and
manual ranking keep their existing path.

1. Hard validity, exact locations, distance eligibility and outside-tolerance
   error remain first. Degenerate and severe out-and-back loops lose to useful
   loops before woodland is compared. Among eligible useful loops, the small
   cost is `-woodland_percentage + 0.25 × urban_percentage + 2 × loop_penalty
   + 10 × distance_error / max(1000, route_distance)`. A percentage target uses
   absolute percentage error instead of negative woodland. Only common measured
   fields contribute. Existing shape, wish, distance and identity ties remain
   deterministic. Unknown coverage never becomes woodland.
2. Keep the original no-POI control and its bounded native-distance correction.
   Use that actual distance to size additional headings. Existing local Nature
   polygons classify up to 128 proposal points in the regional worker, under a
   two-million-operation limit. These point hints guide geographical exploration;
   they never establish a route, distance or forest share. Missing guidance is
   explicitly unavailable and does not prevent routing.
3. Reserve at least three of each eight-call round for optional-stop attempts;
   forest controls use at most five. Every complete native line is arrival- and
   loop-validated before Nature. Measured woodland then influences beam retention,
   insertion-parent choice and final selection. Temporary insertion estimates
   receive no Nature analysis. The existing request-wide cache bounds unique
   full-route Nature analyses by the 16 native replies, each under the unchanged
   four-million-operation bound. No extra native budget, index or service exists.
4. Retain a forest tradeoff, a useful checked-place alternative and further
   genuinely distinct measured lines when available. A worthwhile history detour
   may survive as an explicit comparison variant. Expose the no-POI comparison
   independently, with at most five published lines. Preserve existing geometric
   family diagnostics and the no-POI promotion gate: without exact repetition
   evidence, the comparison still leads within its tolerance class.
5. Use the same measured rule for round comparison. Keep original wishes and
   mandatory intent; never merge routes from different canonical requests. A
   failed revision still preserves round one. The existing two-model-call limit
   and optional stories-only second pass are unchanged.

UI labels describe supported differences only: “Forest-focused” needs at least
50% mapped woodland and a five-percentage-point contrast; below that it says
“Most mapped woodland found.” Historical labels use checked local categories,
not unverified anecdote claims. No third category is manufactured. Unmet woodland,
unacceptable shape, unknown landcover and shared-family variants remain explicit.

## Matched real-graph acceptance

Each before/after pair uses the same Start, `trail_run`, seed, target, tolerance,
place proposals, private Yvelines graph and 8+8 native allowance. Baseline is the
archived `88bdb8c` runtime. The real pinned Valhalla 3.9.1 actor runs on the host
with networking disabled and regional data mounted read-only. Actual continuous
native geometry, local Places/Nature and existing IGN-derived elevation are used.
Nature executes in a dedicated browser worker. All 11 manifest component hashes
remain unchanged; no region is regenerated.

Inference is a deterministic fixture, never a new account call. The latest-place
case reconstructs the eight proposed and four finally reached OSM identities from
the latest physical receipt; exact proposal priorities were not retained, so it
uses equal curated priorities. The retained-proposal cases use the earlier saved
parsed ChatGPT proposals. The curated case preserves the earlier geographical
experiment. A stories-only fixture returns an empty stories array, not invented
research evidence. Results do not establish live model or Android latency.

“Best evaluated” below includes both routing rounds' complete, within-tolerance,
nondegenerate/nonsevere lines, including those the baseline later discards.
Woodland lists follow canonical publication order; the comparison is first.

| Case; target ± tolerance | Best evaluated woodland, before → after | Retained woodland, before → after | Maximum checked visits, before → after | Families + variants, before → after | Native calls | Host time |
| --- | --- | --- | --- | --- | --- | --- |
| Latest-place identities; 35 ±3.5 km | 34.3 → 54.2% | 20.8/12.0/13.3 → 32.4/54.2/50.7/44.6% | 1 → 3 | 3+0 → 3+1 | 16 → 16 | 3.258 → 3.508 s |
| Retained proposals; 35 ±3.5 km | 37.3 → 46.5% | 34.3/37.3/21.0 → 31.3/46.5/30.7/33.8% | 4 → 1 | 2+1 → 3+1 | 16 → 16 | 2.217 → 3.758 s |
| Curated fixture; 35 ±3 km | 46.6 → 54.6% | 15.6/17.5/42.0 → 42.9/54.6/46.2% | 3 → 1 | 2+1 → 3+0 | 16 → 8 | 2.243 → 1.440 s |
| Retained proposals; 25 ±2.5 km | 30.5 → 65.6% | 21.5/25.2/30.5 → 41.6/65.6/36.4% | 3 → 1 | 3+0 → 3+0 | 16 → 8 | 2.177 → 1.407 s |
| History only; 35 ±3.5 km | 37.3 → 37.3% | 34.3/37.3/21.0 → identical | 4 → 4 | 2+1 → 2+1 | 16 → 16 | 2.630 → 2.791 s |
| Distance only; 35 ±3.5 km | 37.3 → 37.3% | 34.3/37.3/21.0 → identical | 4 → 4 | 2+1 → 2+1 | 16 → 16 | 2.798 → 2.550 s |

The last two cases preserve candidate objects and GPX bytes exactly. In the two
eight-call cases, the existing controller accepts the measured first route set;
the second fixture call is stories-only and does not route again.

The latest-place optimized set has these actual tradeoffs:

| Line | Distance / absolute error | Checked visits | Woodland / urban / unknown | Loop penalty / sampled crossings | D+ |
| --- | --- | ---: | --- | --- | ---: |
| Distance comparison | 35.097 km / 97 m | 0 | 32.4 / 34.0 / 28.5% | 0.922 / 1 | 345.75 m |
| Forest-focused | 34.095 km / 905 m | 0 | 54.2 / 27.4 / 8.2% | 1.668 / 4 | 300.50 m |
| Historical variant | 36.394 km / 1,394 m | 3 | 50.7 / 32.0 / 7.7% | 2.671 / 12 | 367.75 m |
| Other loop | 34.901 km / 99 m | 1 | 44.6 / 26.7 / 23.4% | 0.479 / 0 | 324.25 m |

All four are within tolerance, nondegenerate and nonsevere. The forest/history
pair shares a family; the history line trades extra distance, urban exposure and
crossings for visits. Sampled crossing counts and coordinate-segment sharing are
geometry proxies, not exact repeated-edge or access measurements.

Historical coverage is not uniformly improved. In the retained 35 km proposal
case, an optimized three-visit line reaches 54.7% woodland but measures 39.215 km,
outside tolerance; it cannot replace an in-tolerance option. The chosen round
retains one visit. Curated 35 km and 25 km cases also retain fewer visits. This is
a demonstrated bounded-search tradeoff, not proof that better combinations are
impossible. Round selection still chooses one complete request's portfolio, so
useful alternatives from the other round are not combined.

Host times are single observations including local routing, Nature, publication
and elevation, excluding actor/dataset startup and real inference. Unique Nature
analyses rise from 7 to 16 in the latest-place case (187 → 475 ms) and 6 to 16 in
retained 35 km (128 → 427 ms). They change from 5 to 7 for the curated case and
6 to 8 for 25 km. The saved routing round outweighs that extra analysis in those
two cases. Final-round point guidance examines 56 points in roughly 36,000
operations in these fixtures, below its strict bound. These are operation and
wall-time measurements, not a device memory/energy benchmark.

## Determinism, correctness and review

Four repeated optimized forest runs preserve selected round, canonical requests,
candidates, ranks, geometry and GPX exactly. Independent Python validation checks
91 candidate instances across the 12 matched runs and four repeats against the
shared submitted-candidate validator and actual native receipts. Every exported
vertex matches the returned native line; GPX has exactly one track and segment,
no route/extensions, and only validated reached waypoints. Export makes no route
call. Nature partitions authoritative native distance. All cache identities and
8+8/16 budgets hold, including successful/failed entries and backend misses.

Focused source review covers exact-point ordering, stop arrival, profile and
regional identity, cancellation after worker awaits, bounded spatial work,
canonical request ownership, unavailable metrics, variant accounting and the
unchanged no-POI promotion gate. The new worker query is local, build-bound and
read-only. It adds no account, bridge, network, storage or permission authority.
Authentication, speech, source rendering and snapshot schema are unchanged.
New synthetic regressions cover forest/shape/distance gates, ordinary wishes,
worker query/removal, strict native/cache budgets, labels and exact forest result
recovery/GPX. Unit tests remain independent of the private graph and services.

Local final validation passes:

- `make check`: Ruff, strict mypy (303 files), 1,612 tests; 16 integration tests
  deselected and nine existing NumPy warnings. Four missed shell-version assertions
  were corrected before the final passing run.
- All 61 browser harnesses and 18 self-contained drivers. The final changed UI and
  regional worker scenarios also pass in their drivers. The handoff driver needed
  its local evidence directory created, then passed a complete rerun. The six
  older real-service visual drivers still require their separate server/map setup;
  they are not claimed as passing here. The old form driver is superseded by the
  current offline product suites.
- Android Debug 288, Release 283 and staging 283 JVM tests, with no failures,
  errors or skips; all three lints and assemblies, plus debug instrumentation APK
  packaging. No device instrumentation was run.

The audited runtime source is `14f3cae9118b7a1bb360e9dd7f9092c24add15b2`.
All 153 declared assets exactly match each Debug, unsigned Release and staging
APK (staging uses its explicit private catalog). Production debugging is off;
there is no staging CA in normal variants or private regional database in any
APK. The native library hash is unchanged. ZIP and native ELF 16 KiB alignment,
staging certificate continuity, exact CA/catalog and ZIP integrity pass.

Prepared staging APK SHA-256:
`63bd8597b13d8c882ca9eda80cdb849c499974cabcc5e65bb3e42262a5908e05`.
The APK is retained privately and **not installed**. Documentation-only follow-up
commits do not change the audited runtime bytes.

Source review, local checks and actual route-quality acceptance are satisfactory.
The task authorizes routine merging after all four GitHub workflows pass at the
final PR head. The [PR checks and merge status](https://github.com/victorgabillon/sugarglider/pull/110)
are authoritative for that final remote gate. Physical installation and live
account operations remain separately pending.

## Remaining physical acceptance

The next physical test requires a separately authorized retained-data staging
installation and at most two new real account calls. It should enter the exact
French Marly sentence, verify edited speech/text and the account-discovered model,
record all route/visit/Nature/shape/family measurements and actual latency, inspect
the forest/history labels and reached-place stories, export through Android's
document picker, and compare canonical GPX and force-stop/restart recovery without
additional routing or inference. Finally restore the original 23.172 km route,
editor and speech-provider preference. No uninstall, data clearing, production or
Play operation is part of that acceptance. This test is pending; no current result
claims the changed APK has run on the phone.


## Complete retained route measurements

The following rows preserve canonical publication order within each case. `V`
is the number of checked visits; loop is the shared geometry penalty. All listed
lines are within their case's tolerance, nondegenerate and nonsevere. These are
mapped landcover shares, not asphalt, legality, current access or exact repetition.

| Case / version / line | Native km | Error m | V | Woodland % | Urban % | Unknown % | Loop | Sampled crossings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Latest-place 35 / before / 1 | 35.987 | 987 | 0 | 20.8 | 26.9 | 48.4 | 3.064 | 13 |
| Latest-place 35 / before / 2 | 36.456 | 1456 | 1 | 12.0 | 58.1 | 28.3 | 0.668 | 0 |
| Latest-place 35 / before / 3 | 32.997 | 2003 | 0 | 13.3 | 53.2 | 31.5 | 1.194 | 1 |
| Latest-place 35 / after / 1 | 35.097 | 97 | 0 | 32.4 | 34.0 | 28.5 | 0.922 | 1 |
| Latest-place 35 / after / 2 | 34.095 | 905 | 0 | 54.2 | 27.4 | 8.2 | 1.668 | 4 |
| Latest-place 35 / after / 3 | 36.394 | 1394 | 3 | 50.7 | 32.0 | 7.7 | 2.671 | 12 |
| Latest-place 35 / after / 4 | 34.901 | 99 | 1 | 44.6 | 26.7 | 23.4 | 0.479 | 0 |
| Retained 35 / before / 1 | 35.268 | 268 | 0 | 34.3 | 42.1 | 20.8 | 1.293 | 2 |
| Retained 35 / before / 2 | 38.499 | 3499 | 4 | 37.3 | 37.5 | 23.0 | 1.285 | 1 |
| Retained 35 / before / 3 | 36.080 | 1080 | 1 | 21.0 | 26.8 | 48.3 | 3.147 | 11 |
| Retained 35 / after / 1 | 34.947 | 53 | 0 | 31.3 | 35.9 | 27.6 | 0.658 | 0 |
| Retained 35 / after / 2 | 34.216 | 784 | 1 | 46.5 | 28.4 | 20.6 | 0.468 | 0 |
| Retained 35 / after / 3 | 35.639 | 639 | 1 | 30.7 | 33.7 | 29.8 | 0.688 | 0 |
| Retained 35 / after / 4 | 32.257 | 2743 | 0 | 33.8 | 42.9 | 19.3 | 0.617 | 0 |
| Curated 35 / before / 1 | 35.831 | 831 | 0 | 15.6 | 41.0 | 25.2 | 0.632 | 0 |
| Curated 35 / before / 2 | 37.432 | 2432 | 3 | 17.5 | 38.6 | 26.5 | 0.662 | 0 |
| Curated 35 / before / 3 | 37.184 | 2184 | 1 | 42.0 | 30.6 | 21.9 | 1.112 | 2 |
| Curated 35 / after / 1 | 34.549 | 451 | 0 | 42.9 | 36.8 | 15.8 | 1.074 | 1 |
| Curated 35 / after / 2 | 36.327 | 1327 | 1 | 54.6 | 23.2 | 17.5 | 0.868 | 1 |
| Curated 35 / after / 3 | 36.222 | 1222 | 0 | 46.2 | 30.1 | 9.9 | 2.949 | 16 |
| Retained 25 / before / 1 | 24.378 | 622 | 0 | 21.5 | 31.0 | 46.6 | 1.168 | 2 |
| Retained 25 / before / 2 | 27.378 | 2378 | 3 | 25.2 | 24.9 | 47.1 | 1.393 | 2 |
| Retained 25 / before / 3 | 26.997 | 1997 | 1 | 30.5 | 25.5 | 39.3 | 3.411 | 15 |
| Retained 25 / after / 1 | 24.795 | 205 | 0 | 41.6 | 48.2 | 6.2 | 1.097 | 1 |
| Retained 25 / after / 2 | 26.753 | 1753 | 1 | 65.6 | 27.6 | 6.5 | 0.877 | 1 |
| Retained 25 / after / 3 | 24.737 | 263 | 0 | 36.4 | 55.0 | 8.1 | 3.129 | 14 |
| History 35 / before / 1 | 35.268 | 268 | 0 | 34.3 | 42.1 | 20.8 | 1.293 | 2 |
| History 35 / before / 2 | 38.499 | 3499 | 4 | 37.3 | 37.5 | 23.0 | 1.285 | 1 |
| History 35 / before / 3 | 36.080 | 1080 | 1 | 21.0 | 26.8 | 48.3 | 3.147 | 11 |
| History 35 / after / 1 | 35.268 | 268 | 0 | 34.3 | 42.1 | 20.8 | 1.293 | 2 |
| History 35 / after / 2 | 38.499 | 3499 | 4 | 37.3 | 37.5 | 23.0 | 1.285 | 1 |
| History 35 / after / 3 | 36.080 | 1080 | 1 | 21.0 | 26.8 | 48.3 | 3.147 | 11 |
| Distance 35 / before / 1 | 35.268 | 268 | 0 | 34.3 | 42.1 | 20.8 | 1.293 | 2 |
| Distance 35 / before / 2 | 38.499 | 3499 | 4 | 37.3 | 37.5 | 23.0 | 1.285 | 1 |
| Distance 35 / before / 3 | 36.080 | 1080 | 1 | 21.0 | 26.8 | 48.3 | 3.147 | 11 |
| Distance 35 / after / 1 | 35.268 | 268 | 0 | 34.3 | 42.1 | 20.8 | 1.293 | 2 |
| Distance 35 / after / 2 | 38.499 | 3499 | 4 | 37.3 | 37.5 | 23.0 | 1.285 | 1 |
| Distance 35 / after / 3 | 36.080 | 1080 | 1 | 21.0 | 26.8 | 48.3 | 3.147 | 11 |
