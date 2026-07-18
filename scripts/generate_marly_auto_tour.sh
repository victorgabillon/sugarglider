#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}
JSON_OUTPUT=${1:-${JSON_OUTPUT:-/tmp/sugarglider-marly-auto-tour.json}}
GPX_OUTPUT=${2:-${GPX_OUTPUT:-/tmp/sugarglider-marly-auto-tour.gpx}}
WAYPOINT_JSON=${WAYPOINT_JSON:-/tmp/sugarglider-marly-all-pois.json}
REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REQUEST_PATH="$REPOSITORY_ROOT/examples/marly/auto-tour-request.json"
SELECTED_ROUTE=$(mktemp)

cleanup() {
    rm -f "$SELECTED_ROUTE"
}
trap cleanup EXIT HUP INT TERM

curl --fail --silent --show-error "$API_URL/ready" >/dev/null
curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$REQUEST_PATH" \
    --output "$JSON_OUTPUT" \
    "$API_URL/v1/tours/generate"

python - "$JSON_OUTPUT" "$SELECTED_ROUTE" "$WAYPOINT_JSON" <<'PY'
import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, object]:
    with Path(path).open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    return value


def shape(candidate: dict[str, object]) -> dict[str, object] | None:
    route = candidate["route"]
    assert isinstance(route, dict)
    analysis = route["analysis"]
    assert isinstance(analysis, dict)
    value = analysis.get("loop_geometry")
    return value if isinstance(value, dict) else None


def report(label: str, candidate: dict[str, object]) -> None:
    route = candidate["route"]
    assert isinstance(route, dict)
    summary = route["summary"]
    analysis = route["analysis"]
    assert isinstance(summary, dict) and isinstance(analysis, dict)
    repetition = analysis["repetition"]
    backtrack = analysis["immediate_backtrack"]
    assert isinstance(repetition, dict) and isinstance(backtrack, dict)
    repeated = repetition["repeated_distance"]
    assert isinstance(repeated, dict)
    geometry = shape(candidate)
    nature = analysis.get("nature")
    visits = candidate.get("poi_visits", [])
    assert isinstance(visits, list)
    scenic = [visit for visit in visits if visit["poi"]["group"] == "scenic"]
    water = [
        visit
        for visit in visits
        if visit["poi"]["category"] == "drinking_water"
        and visit["poi"]["potability"] == "verified"
    ]
    print(f"\n{label}")
    print(
        f"  signature={candidate['signature']}; construction={candidate['construction']}; "
        f"skeleton={candidate['skeleton_method']}; direction={candidate['direction']}"
    )
    print(
        f"  distance={summary['distance_m']:.1f} m; target error={candidate['target_error_m']:.1f} m; "
        f"backtracking={100 * backtrack['share']:.3f}%; repeated={100 * repeated['share']:.3f}%"
    )
    if geometry is None:
        print("  loop geometry=not evaluated")
    else:
        penalty = geometry["penalty_breakdown"]
        print(
            f"  geometry penalty={penalty['total']:.6f}; near-parallel={100 * geometry['near_parallel']['share']:.3f}%; "
            f"outbound/return={100 * geometry['outbound_return_proximity']['share']:.3f}%; "
            f"compactness={geometry['compactness']:.6f}; sector balance={geometry['sector_balance']:.6f}; "
            f"max sector={100 * geometry['maximum_sector_distance_share']:.3f}%; "
            f"occupied sectors={geometry['occupied_sector_count']}; angular monotonicity={geometry['angular_monotonicity']:.6f}; "
            f"self-crossings={geometry['self_crossing_count']}"
        )
    print(
        "  nature="
        + ("not evaluated" if nature is None else f"{nature['nature_score']:.1f}/100")
    )
    print(
        f"  scenic visits={len(scenic)}; verified-water visits={len(water)}; "
        f"total reward={candidate['total_poi_reward']:.3f}; soft-distance penalty={candidate['soft_distance_penalty']:.6f}"
    )
    requested = candidate.get("requested_place_visits", [])
    assert isinstance(requested, list)
    print(
        f"  requested satisfied={sum(visit['satisfied'] for visit in requested)}; "
        f"missed={sum(not visit['satisfied'] for visit in requested)}"
    )
    for visit in requested:
        print(
            f"    requested {visit['requested_place']['name']}: satisfied={visit['satisfied']}; "
            f"distance={visit['measured_distance_m']:.1f} m; radius={visit['requested_place']['visit_radius_m']:.1f} m; "
            f"deliberate={visit['deliberately_routed']}; reason={visit['reason']}"
        )
    for visit in visits:
        actual_delta = visit["actual_distance_delta_m"]
        actual_text = "unavailable after repair" if actual_delta is None else f"{actual_delta:.1f} m"
        print(
            f"    {visit['poi']['display_name']}: progress={100 * visit['route_progress_share']:.1f}%; "
            f"estimated detour={visit['estimated_detour_m']:.1f} m; "
            f"actual delta={actual_text}; reward={visit['reward']:.3f}; "
            f"reason={visit['reason']}"
        )


result = load(sys.argv[1])
control = result["control"]
candidates = result["candidates"]
search = result["search"]
assert isinstance(control, dict) and isinstance(candidates, list) and candidates
assert isinstance(search, dict)
recommended = candidates[0]
assert isinstance(recommended, dict)
report("Best no-POI Auto Tour control", control)
report("Recommended Auto Tour", recommended)

print("\nBounded search")
for key in (
    "isochrone_request_count",
    "round_trip_control_request_count",
    "sampled_fallback_skeleton_count",
    "skeleton_route_request_count",
    "skeleton_candidate_count",
    "retained_skeleton_count",
    "poi_index_candidate_count",
    "already_collected_poi_count",
    "poi_route_evaluation_count",
    "local_repair_evaluation_count",
    "corridor_repair_evaluation_count",
    "alternative_leg_request_count",
    "total_route_request_count",
    "total_route_request_budget",
    "budget_exhausted",
    "route_cache_hit_count",
    "requested_place_satisfied_count",
    "requested_place_missed_count",
    "maximum_distance_m",
):
    print(f"  {key}={search[key]}")
for key, value in search["timings"].items():
    print(f"  {key}={value:.3f}")
print("  warnings=" + (", ".join(search["warnings"]) or "none"))

rejections = recommended.get("rejected_poi_opportunities", [])
print("\nTop rejected opportunities")
if not rejections:
    print("  none")
for rejection in rejections:
    print(
        f"  {rejection['display_name']}: {rejection['reason_code']}; "
        f"estimated detour={rejection['estimated_detour_m']:.1f} m; "
        f"route distance={rejection['nearest_route_distance_m']:.1f} m"
    )

route = recommended["route"]
distance = route["summary"]["distance_m"]
if distance > recommended["maximum_distance_m"]:
    raise SystemExit(f"recommended distance {distance:.1f} m exceeded the safety maximum")
if not all(visit["satisfied"] for visit in recommended["hard_point_visits"]):
    raise SystemExit("an exact hard point was not satisfied")
analysis = route["analysis"]
if len(candidates) != 3:
    raise SystemExit(f"expected three returned candidates, got {len(candidates)}")
if search["sampled_fallback_skeleton_count"] == 0 or search["poi_route_evaluation_count"] == 0:
    raise SystemExit("fallback did not perform sampled deliberate place routing")
if recommended["skeleton_method"] == "graphhopper_round_trip":
    raise SystemExit("the recommendation remained the original raw round trip")
requested_visits = recommended.get("requested_place_visits", [])
if not any(visit["satisfied"] and visit["deliberately_routed"] for visit in requested_visits):
    raise SystemExit("no imported requested place influenced the recommendation")

scenic_count = recommended["selected_scenic_count"]
water_count = recommended["selected_verified_water_count"]
if scenic_count == 0:
    print("No safe primary scenic insertion passed every control gate.")
if water_count == 0:
    print("No safe verified-water insertion passed every control gate.")

waypoint_path = Path(sys.argv[3])
if waypoint_path.is_file():
    waypoint = load(str(waypoint_path))
    waypoint_candidates = waypoint.get("candidates", [])
    if isinstance(waypoint_candidates, list) and waypoint_candidates:
        old = waypoint_candidates[0]
        old_shape = shape(old)
        print("\nExisting 23-waypoint route (observation only)")
        print(f"  signature={old['signature']}; distance={old['route']['summary']['distance_m']:.1f} m")
        if old_shape is not None:
            print(
                f"  compactness={old_shape['compactness']:.6f}; "
                f"near-parallel={100 * old_shape['near_parallel']['share']:.3f}%"
            )
else:
    print(f"\n23-waypoint observation skipped: no saved result at {waypoint_path}")

with Path(sys.argv[2]).open("w", encoding="utf-8") as output:
    json.dump(route, output, ensure_ascii=False, separators=(",", ":"))
PY

curl --fail --silent --show-error \
    --header "Content-Type: application/json" \
    --data-binary "@$SELECTED_ROUTE" \
    --output "$GPX_OUTPUT" \
    "$API_URL/v1/routes/gpx/from-result"

python - "$GPX_OUTPUT" <<'PY'
import sys
from xml.etree import ElementTree

root = ElementTree.parse(sys.argv[1]).getroot()
namespace = {"g": "http://www.topografix.com/GPX/1/1"}
assert len(root.findall("g:trk", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
assert len(root.findall("g:trk/g:trkseg/g:trkpt", namespace)) > 1
assert not root.findall("g:rte", namespace)
assert not root.findall(".//g:extensions", namespace)
PY

echo "Auto Tour JSON: $JSON_OUTPUT"
echo "Selected Auto Tour GPX: $GPX_OUTPUT"
