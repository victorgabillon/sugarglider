# Elevation analysis from native Valhalla heights — PR89

Implemented on PR88 base `df114de9376d7d9e7e3744f384b2b6bca123de19`.
Measurements: 2026-10-15. This is a working, optional Python analysis pipeline
and an offline evaluation tool. There is no production elevation UI or automatic
route enrichment in this PR. Routing, candidates, ranking, profiles, geometry,
waypoints, GPX, Android, installations and published regional data are unchanged.

## Result on the actual PR88 profile

The original Fairphone route is **25,353 m**, with 1,051 geometry vertices and
509 native height samples at 50 m nominal spacing. The last interval is **3 m**;
it is not rounded to 50 m. All 509 heights are available and every interval
satisfies the default 100 m coverage limit. Available native altitudes span
**61.16–169.98 m**. The loop starts and ends at 111.05 m, hence equal D+/D−.

| Method | D+ (m) | D− (m) |
| --- | ---: | ---: |
| Raw native samples | 539.63 | 539.63 |
| Distance box, ±25 m | 501.05 | 501.05 |
| **Selected distance box, ±50 m** | **472.45** | **472.45** |
| Distance box, ±75 m | 452.49 | 452.49 |
| Distance box, ±100 m | 435.03 | 435.03 |
| Distance box, ±150 m | 411.71 | 411.71 |
| Distance box, ±250 m | 370.18 | 370.18 |
| Three-sample median, endpoints retained | 467.78 | 467.78 |

The selected unrounded value is **472.44780000000003 m** in both directions.
Filtered heights span 62.0175–169.0875 m. The reported minimum/maximum in the
public analysis model deliberately describe **available raw heights**; they do
not conceal the raw extrema by substituting smoothed values.

These are measured signal summaries, not surveyed terrain truth. No target D+
was supplied, assumed, or used to select parameters. Numerical agreement with a
second implementation of the same DEM does not validate its terrain accuracy.

## Contract and evidence binding

`sugarglider.analysis.elevation` provides immutable, strict, JSON-serializable
`ElevationProfile`, `ElevationParameters` and `ElevationAnalysis` models and the
pure `analyze_elevation(profile, parameters)` function. There is no I/O, routing
call, FastAPI dependency, DEM lookup, or dependency on optional elevation being
present in the planning path.

Inputs retain source SHA-256, geometry SHA-256, public routing profile,
authoritative route length, height reference, ordered sample indices and precise
routed progress. Progress starts at exactly zero, is strictly increasing, and
ends at exactly the supplied route length. Zero and negative altitudes are valid;
`null` means unavailable. Duplicate progress is rejected; repeated geometry
vertices and revisiting coordinates remain valid in PR88's normalized sampler.

Finite heights must be within PR88's native usable range ±16,384 m. The inherited
limits remain 2,048 samples, 200 km, and 2 MiB per evidence file. Oversized,
nonfinite, unordered, malformed, unexpected-field and mismatched data is rejected,
never reordered, truncated or silently coarsened. Strict parsing rejects numeric
strings and booleans in numeric fields.

The offline `elevation_analysis` adapter checks the full PR88 chain:

1. Hash the original routed geometry exactly as PR88 did; match route/profile/
   distance/source/spacing identities across the documents.
2. Recompute the normalized PR88 sample plan from that geometry, including source
   edges, fractions, six-decimal sampling coordinates and exact progress.
3. Match the native result's source hash and SHA-256 of the **exact plan bytes**.
4. Match every native height and every sample position; verify comparison counts,
   availability and errors. Optionally cross-check every CSV field and row.

The real JSON, CSV, plan, native output and original geometry all pass. Hashes bind
the supplied evidence; they do not authenticate an untrusted publisher. The DEM
source hash identifies compressed HGT bytes, not a certified vertical datum.

Output retains all samples at their original distances and adds filtered heights
and segment IDs. It includes algorithm version `distance-box-v1`, explicit
parameters, input/source/route identities, coverage, covered/unknown distance,
available sample count, available extrema and raw/filtered ascent/descent.

`profile_sha256` is a portable streamed fingerprint, separate from the algorithm
and parameters: SHA-256 of ASCII `sugarglider-elevation-profile-v1` plus a NUL;
then source hash, geometry hash, routing profile and height reference as UTF-8,
each prefixed by its big-endian unsigned 32-bit byte length; then big-endian
binary64 route distance and unsigned 32-bit sample count; then each sample's
unsigned 32-bit index, binary64 distance, unsigned byte height-presence flag, and
optional binary64 height. There is no platform-dependent JSON float formatting
or additional full-profile serialization. Synthetic golden fixtures cover the
entire output and fingerprint for a future native implementation.

## Chosen method and mathematical properties

Default parameters are a **50 m radius / 100 m full-width distance box**,
maximum supported adjacent sample gap **100 m**, constant boundary extension
with original endpoints retained, and no missing-data filling. Radius zero
explicitly selects raw analysis. Positive radii are bounded to 1–500 m and gap
limits to (0, 1,000] m; invalid settings fail rather than change policy.

Split the samples at **every null** and every adjacent interval exceeding the
gap limit. Within each supported run, regard heights as a piecewise-linear
function of routed distance. Integrate that signal exactly over each centered
window, extending the run's end heights as constants for the window calculation.
Retain the original first and last sample of each run. This boundary condition
does not create output in unknown intervals. No run ever reads another run's
heights, even when the smoothing window exceeds its length. Single available
samples remain visible but contribute no distance or gain.

Sum positive and negative differences **only within those filtered runs**, using
`math.fsum`. No extra vertices are inserted in the filtered profile. The algorithm
does not infer unobserved summits between samples. Closed routes use the same
endpoint policy, not circular wrapping; relocating a loop's start can therefore
change the small boundary contribution.

The selection is based on interpretable synthetic behavior, not a desired real
route total. At 50 m regular spacing, the ±50 m box on the linear interpolant has
interior weights **¼, ½, ¼**: it removes sample-to-sample alternating noise, retains
linear slopes, and preserves broad plateaus and their full climb heights. A
±25 m radius leaves half the alternating amplitude; widening beyond ±50 m
attenuates broader features further. A genuine sharp summit is reduced: the
synthetic 30 m triangle with 10 m rise per 50 m becomes 25 m. Three broad 30 m
climbs retain 90 m total. No filter can distinguish every short real climb from
noise without additional observations; the parameter table exposes that choice.

For each run, let `TV` denote total variation and `Δ` its endpoint height change.
A positive normalized convolution cannot increase TV: by the triangle inequality,
the variation of the weighted average is at most the weighted original variation.
Constant extension has the same TV as the original signal. Keeping original
endpoints is equivalent, for this bound, to taking the convolution at positions
outside both window supports, where it equals those endpoints, and retaining
interior samples. Variation of that subsequence is at most full convolution TV.
Thus filtered TV ≤ raw TV while Δ is retained, and
`D+ = (TV + Δ)/2`, `D− = (TV − Δ)/2` cannot increase.

The centered kernel and identical endpoint policy commute with distance reversal.
Reversing a fully covered input therefore exchanges D+ and D−; the same holds
run by run for partial data. The real profile reverses with **0.0 m** difference
in totals and filtered sample heights in the measured run.

Numerical checks allow **1e-7 m absolute** for invariants and reversal, with no
relative allowance. Tests include 2,048 irregular samples spanning almost 100 km
and heights approaching the usable ±16 km bounds. Exact constant profiles yield
exact zero. This numerical tolerance is unrelated to terrain accuracy or the
PR88 native serialization tolerance of 0.010001 m. A range-sum tree integrates
local windows without subtracting two large route-wide prefix integrals; direct
trapezoid reference tests verify the numerical integration independently.

### Median, Gaussian and hysteresis investigation

The three-sample median is robust to isolated spikes, and gives 467.78 m on this
profile. It also completely erases the genuine `[0, 10, 0]` summit. An index-based
window changes physical width with irregular spacing and dense vertices get
disproportionate influence. A distance-weighted median could be investigated
later, but the median comparator is not a hidden preprocessing stage.

The [SciPy Gaussian filter documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.gaussian_filter1d.html)
defines sigma in sample units; the [median documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.median_filter.html)
likewise specifies sample footprints and explicit boundary modes. Applying these
directly to irregular routed distances would need another sampling policy. The
distance box avoids resampling, a new numerical dependency and an opaque kernel
truncation parameter, while giving an exact, auditable integral.

We also implemented a simple causal height deadband: accept a whole change when
it reaches the threshold; ignore the terminal residual. It is **not** the chosen
algorithm. Its real-profile sensitivity demonstrates why blindly importing a
height threshold is insufficient:

| Threshold | Forward D+ / D− (m) | Reversed D+ / D− (m) |
| --- | ---: | ---: |
| 1 m | 511.92 / 511.38 | 509.88 / 510.58 |
| 2 m | 480.27 / 479.73 | 479.85 / 478.92 |
| 3 m | 451.80 / 451.26 | 450.14 / 449.21 |
| 5 m | 427.07 / 422.35 | 410.68 / 414.47 |
| 10 m | 389.60 / 384.88 | 351.63 / 358.02 |

A synthetic regression also demonstrates reversal bias and terminal loss. This
does not establish that every hysteresis algorithm is biased: a symmetric extrema
method could satisfy the invariants, but would add a vertical significance policy
without a calibrated local error model. No deadband is applied to the selected
profile. [Strava's official explanation](https://support.strava.com/en-us/articles/15402093-elevation-on-strava-faqs)
uses different thresholds for different measurement sources; its numbers are
context for investigation, not a validation reference or a specification we copy.

## Coverage and uncertainty

`complete` means every sample is available and all adjacent intervals are within
the configured gap limit. `partial` means at least one sample is available but
some route distance is unsupported. `unavailable` means all heights are null.
These are **sample support** states, not a claim about DEM coverage between every
pair of coordinates or measurement accuracy.

`total_ascent_m` and `total_descent_m` are populated only for complete coverage.
For partial coverage, `observed_ascent_m` / `observed_descent_m` summarize supported
runs only. They are not extrapolated full-route values or certified physical lower
bounds. If no interval is supported, observed quantities are null too, even when
one isolated height exists. Covered and unknown distance partition route length.
Plots must break when segment IDs change, including across long gaps whose two
endpoints both have available heights.

### Sampling density

First, decimate the **actual native heights**, retaining the final endpoint. The
same ±50 m smoother is used throughout:

| Nominal native subset spacing | Samples | Raw D+ / D− (m) | Filtered D+ / D− (m) |
| --- | ---: | ---: | ---: |
| 50 m | 509 | 539.63 / 539.63 | 472.45 / 472.45 |
| 100 m | 255 | 495.90 / 495.90 | 452.35 / 452.35 |
| 200 m | 128 | 443.85 / 443.85 | 421.01 / 421.01 |
| 400 m | 65 | 387.05 / 387.05 | 372.38 / 372.38 |

For this sampling experiment **only**, the gap limit is explicitly relaxed to
1,000 m. At 200/400 m, the production default correctly reports partial coverage
and null full-route totals; the table is not an automatic relaxation.

Next, resample the original routed geometry with PR88's **Python bilinear sampler
against exactly the same pinned HGT**. This investigates finer intervals without
claiming a new native run or an independent reference DEM:

| Same-DEM spacing | Samples | Raw D+ / D− (m) | Filtered D+ / D− (m) |
| --- | ---: | ---: | ---: |
| 12.5 m | 2,030 | 587.18 / 587.18 | 494.58 / 494.58 |
| 25 m | 1,016 | 570.21 / 570.21 | 489.80 / 489.80 |
| 50 m | 509 | 539.70 / 539.70 | 472.47 / 472.47 |
| 100 m | 255 | 495.90 / 495.90 | 452.35 / 452.35 |
| 200 m | 128 | 443.86 / 443.86 | 421.01 / 421.01 |

The 50 m Python/native filtered difference is about **0.0222 m**, consistent with
PR88's serialization difference. The approximately **22.1 m** increase at 12.5 m
relative to the native 50 m result is a meaningful sampling sensitivity: smoothing
does not recover summits absent from the sampled signal. Finer spacing approaches
this DEM interpolant, not necessarily true terrain. The 25 m and 12.5 m results
also differ; convergence is not established by one pair of resolutions.

### What has and has not been validated

Validated: evidence binding, native/Python sampling agreement from PR88, numerical
integration, invariant behavior on known synthetic terrain, gap handling,
determinism, serialization, bounds and observed performance. No independent
surveyed or barometric elevation profile of this exact route was available in
the supplied research artifacts. The prior local altitude plausibility checks
are not a validation of cumulative ascent. No preferred external D+ is invented.

Uncertainty remains from DEM source/compositing, unresolved vertical datum,
integer cell heights, grid resolution, horizontal route/map positioning,
six-decimal sampling-coordinate quantization, sampling density, vegetation/
structures/bridges versus actual path elevation, and smoothing/boundary policy.
Raw cumulative ascent accumulates small fluctuations; broad filtering can erase
short genuine climbs. The ±25–100 m range (435.03–501.05 m) is a **parameter
sensitivity range**, not a statistical confidence interval. No calibrated terrain
error bound can be inferred from centimetre serialization agreement.

DEM bytes, complete personal routes, native profiles, CSVs, plots and evaluation
artifacts remain outside Git. PR88's provenance, datum and redistribution questions
remain unresolved, and the DEM is still unpublished.

## Performance and verification

Analysis uses **O(n log n)** time and **O(n)** additional memory, bounded at 2,048
samples. A linear-size integral range tree, binary searches and local partial
trapezoids avoid quadratic windows and whole-profile copies for fingerprinting.
The input and route are never mutated. There is no native call in these timings.

Measured with Python 3.13.5 on an Intel Core i7-11800H Linux host: ten warmups,
200 independent calls per input; timings include fingerprinting, filtered sample
construction and immutable result validation, excluding input loading/DEM/JNI/
serialization. Peak additional Python memory is measured separately with
`tracemalloc`; it is not process RSS or a Fairphone measurement.

| Input | Median | p95 | Peak additional Python memory |
| --- | ---: | ---: | ---: |
| Actual 509 samples | 5.35 ms | 5.98 ms | 540 KiB |
| Synthetic full 2,048-sample budget | 22.35 ms | 26.06 ms | 2.09 MiB |

The fourfold sample increase costs approximately 4.2 times the analysis time;
observed allocation remains linear. Host timings are observations, not device
latency promises. Full raw timings and private evaluation outputs remain under
`/tmp/sugarglider-elevation-evaluation`.
Focused tests cover constant/zero/negative height, monotone ascent/descent,
summits, multiple broad climbs, alternating noise, noisy ascending/descending
slopes including endpoint residuals, reversed routes, irregular spacing, repeated
vertices, missing intervals, long gaps, isolated heights, partial/unavailable
coverage, strict validation, identity tampering, CSV/CLI/file integration,
independent trapezoid integration, deterministic budget-sized inputs and portable
golden results. Tests use synthetic terrain only and need no native engine,
network, Docker or map data.

Final `make check`: Ruff formatting/lint passed (288 Python files); strict mypy
passed (274 source/test files); **1,348 tests passed**, with 16 live GraphHopper
integration tests intentionally deselected, in 156.52 s. The **81 new focused
elevation tests** passed separately. The six relevant browser harnesses passed
**139 scenarios** (profiles 4, local waypoints 34, planner 19, candidates 40,
GPX 27, regional integrity 15), with external requests blocked. Android code is
unchanged, so no new APK, device installation or local Android test run was needed.

## Reproduce without changing the application

All evidence paths are explicit and all outputs should remain outside Git:

```sh
uv run python -m sugarglider.offline_regions.elevation_analysis \
  --profile /tmp/sugarglider-height-research/elevation-profile.json \
  --plan /tmp/sugarglider-height-research/plan.json \
  --route /tmp/sugarglider-height-research/route.json \
  --native-result /tmp/sugarglider-height-research/fairphone-final/native-result.json \
  --csv /tmp/sugarglider-height-research/elevation-profile.csv \
  > /tmp/elevation-analysis.json

# Adds filter sensitivity, native subsets, benchmarks and an optional same-DEM
# density study. Does not download, install, route, publish or alter source files.
uv run python -m sugarglider.offline_regions.elevation_study \
  --profile /tmp/sugarglider-height-research/elevation-profile.json \
  --plan /tmp/sugarglider-height-research/plan.json \
  --route /tmp/sugarglider-height-research/route.json \
  --native-result /tmp/sugarglider-height-research/fairphone-final/native-result.json \
  --csv /tmp/sugarglider-height-research/elevation-profile.csv \
  --tile /tmp/sugarglider-height-research/source/skadi/N48/N48E002.hgt.gz \
  --repetitions 200 > /tmp/elevation-study.json

make check
```

The study requires complete default-policy support for raw/median/deadband
comparisons. The analysis command itself fully supports partial/unavailable
profiles. An absent or invalid optional elevation request must remain separate
from planning success; existing planning does not call this analysis at all.

## Next Android/WebView integration

1. Analyze only the already selected candidate's immutable native height profile.
   Cache by exact route/source/profile identity, algorithm version and parameters;
   discard late results when selection identity changes. A failure or missing DEM
   must leave the route usable and display elevation unavailable.
2. Use this JSON contract and the committed synthetic `contract-v1.json` golden
   fixtures for an equivalent native implementation. Python is the executable
   reference; Android still needs a tested native port and device performance
   measurements. Do not embed a Python runtime merely for this module.
3. Return the complete analysis projection to WebView. The browser plots exact
   routed distance and precomputed heights, breaks at segment boundaries and
   displays returned metrics; it must not recompute D+/D− or alter route geometry.
4. Label totals as terrain estimates. For this input, a summary such as
   **≈470 m D+ / ≈470 m D−** avoids implying centimetre terrain accuracy. Details
   should expose full sampled coverage, method/window, source identity, available
   extrema and sensitivity. Partial coverage shows measured supported distance
   and observed totals explicitly, with no full-route estimate.
5. Before choosing denser native sampling for the UI, measure its actual JNI
   latency/memory on device under the unchanged 2,048-sample budget. Explore
   25 m where it fits; never silently coarsen long routes or tune the window to
   match another service's total. Keep routing/ranking/GPX unchanged. Elevation
   publication and installation remain separate work pending provenance review.
