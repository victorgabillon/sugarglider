# On-device Start and End snapping

A newly chosen Android Start or End uses **Near this point**. The endpoint editor and map ribbon also offer **Exact point**. Canonical requests store the independent choices in `endpoint_snap_policy: {"start": "near", "end": "exact"}`. An absent policy retains exact on-device intent; importing an older request stamps that intent into the editor. Point edits, mode changes and Undo retain it.

`endpoint_snapping.js` owns the native and canonical publication policy:

| Requested policy | Native displacement | Result |
| --- | --- | --- |
| Near | 0–25 m | Accept |
| Near | >25–150 m | Accept with a persistent adjustment disclosure |
| Near | >150 m | Keep a proposal outside the successful candidates; require explicit adoption and another Generate |
| Exact | >25 m | Reject; do not retry with weaker constraints |

Inclusive comparisons allow one micrometre of floating-point error. Distance measures displacement, not a walkable connection. Neither mode routes straight lines between the selected and native points. Interior exact waypoints retain their 300 m limit. Auto Tour validates both departures and returns against Start's policy; actual graph-derived loop closure remains independently limited to 25 m. An unsatisfied exact endpoint prevents a flexible endpoint recovery proposal from hiding that failure.

The mode searches check native profile, pack, snapped leg-boundary coordinates, ordered geometry and closure. The shared evaluator independently repeats endpoint bounds and native boundary identity before publication. Large proposals come only from otherwise validated native paths, remain bounded to two endpoints, and are bound to the active regional routing pack. Cancellation and regional leases retain their existing ownership and drain behavior. Budgets, costing and ranking are unchanged.

Successful candidates retain requested and routed coordinates, unrounded measured displacements, limits and statuses under `diagnostics.details.local_routing.endpoint_adjustments`. Adjustments over 25 m additionally create `endpoint_adjusted` compromises. A flexible adjusted traversal anchor is `approach` / `approximated`, rather than exact / reached. Neither original request coordinates nor native geometry are changed.

The map and Routes view retain compact disclosures for the selected candidate. Original hollow markers and actual routed square markers have accessible labels; a separate dashed map source shows displacement and metres. **Show adjustment**, **Move Start/End** and **Use routed point** are ordinary buttons. Adoption uses the existing point edit/history mechanism, invalidates results, and never generates automatically. Changing candidate, region or intent clears stale overlays. Immutable snapshots remain read-only.

**Show adjustment** collapses the map disclosures, keeps focus on the relevant warning summary, and fits both markers above the measured route dock. The warning remains available to reopen before adoption; showing it never edits the request or starts routing.

GPX serializes only the selected canonical native geometry: one track, one segment, no explanatory connector, route-analysis extensions or rerouting. Elevation continues sampling that same native geometry.

Typed canonical Python models retain policy for storage and export; submitted snapshots enforce its bounds. The development GraphHopper planner rejects an explicit Near policy before dispatch because the native leg-boundary adjustment workflow is on-device. It must not silently reinterpret it. This change does not introduce another server planning implementation.

## Evidence and scope

`endpoint_snapping_acceptance.cjs` exercises the normal planner and real canonical module worker across both endpoints, all six profiles and the 0, 24.9, 25, 25.1, 89.2, 149.9, 150, 150.1 and 5,000 m cases. It also covers loops, exact intent, invalid/missing native evidence, region identity, cancellation, interior limits, GPX and edit history. Existing strict browser regressions remain in place.

`endpoint_snapping_ui_acceptance.cjs` runs the bundled page with synthetic committed regions and native replies on desktop and a 372 × 709 px touch viewport. It exercises real map selection, warnings, keyboard/touch adoption, Undo, exact JSON restoration, candidate-specific overlays and region switching. Its large-adjustment review checks that both complete markers stay above the dock and showing them neither edits nor routes. Both suites run in CI alongside Nature, region persistence and elevation acceptance.

The historical 89.2 m screenshot's exact request and native coordinates were not recovered from retained private evidence. The deterministic synthetic 89.2 m test reproduces the threshold rejection; it does not establish the original activity, coordinates, road accessibility or other route validity conditions. No regional data or graph was rebuilt. A staging APK can be prepared, but installation and physical acceptance require separate authorization. No phone changes are part of this implementation.

Ranking does not prefer smaller endpoint displacements. Any such ranking change needs a separate product decision.
