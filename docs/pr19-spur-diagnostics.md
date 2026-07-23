# PR19 route-spur diagnostics

PR19 detects substantial out-and-back excursions after final routed geometry, stop
outcomes, and traversal anchors are known. It adds diagnostics only: generation,
routing calls, budgets, cache identity, scoring, recommendation order, reversal, and
GPX output are unchanged.

## Evidence and thresholds

Detection projects GraphHopper edge IDs onto the same normalized geometry edges used
by repetition and immediate-backtracking analysis. It finds maximal edge-run sequences
that later occur in reverse and tolerates a short turnaround connector. Exact
duplicates and nested or crossing detections with shared outbound and return evidence
are coalesced in route-index space. Other overlapping interpretations are resolved as
one deterministic maximum-value non-overlapping portfolio and reported with
`overlapping_spur_evidence_pruned`; returning runs are never counted twice.
Coordinate proximity alone never creates or merges a spur, so an ordinary loop,
junction reuse, or self-crossing is not sufficient evidence.

The immutable server defaults require at least 100 m of reversed-edge evidence, allow
at most 100 m around a turnaround connector and 30 m of endpoint segmentation gap,
require 90% route-wide edge-ID coverage for medium or high confidence, and merge only
structurally shared reversed-corridor evidence. Incomplete coverage remains a warning
and prevents high-confidence classification.

Each public spur records deterministic identity, kind, confidence, reason codes,
branch/turnaround/rejoin progress and coordinates, exact routed interval geometry,
outbound, return, connector, repeated, and complete-excursion distances, maximum
separation, and ordered deliberate stops. Reached or approximated requested targets,
exact waypoints, and deliberately inserted discovered stops can be attributed through
their final traversal progress. Incidental nearby POIs are not included.

## Browser explanation and limitation

The selected candidate shows a **Route shape issues** section. Each accessible card
reports repeated and complete distance, deliberate stops, and the intentionally
cautious statements “Candidate for route refinement” and “No alternative exit has
been tested yet.” Activating a card fits the exact excursion geometry. Local MapLibre
layers add a subtle excursion highlight plus branch and turnaround markers; PR18
direction arrows remain above route-analysis lines and below these annotations and
the ordinary marker/label foreground.

A detected spur does not prove that it is avoidable, undesirable for the user's
intent, or replaceable by a safe profile-compatible route. PR20 will use these
intervals for bounded alternative-exit routing and will evaluate any actual repair
before making such a claim.
