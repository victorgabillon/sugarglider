"""Python contracts for native candidate publication, without any router or data."""

import json
from pathlib import Path
from typing import Any

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.domain.models import GeoJsonPosition, RouteResult, RouteSummary
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER, RouteTopology
from sugarglider.planning.signatures import candidate_signature
from sugarglider.routing.profiles import ROUTING_PROFILES
from sugarglider.web.build_local_analysis_templates import (
    render_local_analysis_templates,
)
from sugarglider.web.routes import STATIC_DIRECTORY

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "pr41_local_candidates.json"
)


def candidate_fixture_payload() -> dict[str, Any]:
    """Deterministic synthetic native replies and independent canonical truths."""
    geometries: tuple[tuple[str, RouteTopology, tuple[GeoJsonPosition, ...]], ...] = (
        (
            "open",
            "point_to_point",
            ((2.0, 48.0), (2.003, 48.002), (2.007, 48.004), (2.009, 48.008)),
        ),
        (
            "loop",
            "loop",
            ((2.0, 48.0), (2.01, 48.0), (2.01, 48.01), (2.0, 48.01), (2.0, 48.0)),
        ),
        (
            "offset_open",
            "point_to_point",
            (
                (2.096667, 48.871389),
                (2.100301, 48.873847),
                (2.107543, 48.872851),
                (2.114927, 48.881971),
            ),
        ),
        (
            "long_open",
            "point_to_point",
            tuple(
                (
                    round(2.096667 + index * 0.000063 + (index % 3) * 0.000003, 6),
                    round(48.871389 + index * 0.000051 + (index % 5) * 0.000007, 6),
                )
                for index in range(65)
            ),
        ),
        (
            "crossing",
            "loop",
            (
                (2.0, 48.0),
                (2.01, 48.01),
                (2.0, 48.01),
                (2.01, 48.0),
                (2.0, 48.0),
            ),
        ),
    )
    cases: list[dict[str, Any]] = []
    for profile in ROUTING_PROFILES:
        for shape, topology, geometry in geometries:
            coordinate = {
                "lon": (geometry[1][0] + geometry[2][0]) / 2,
                "lat": (geometry[1][1] + geometry[2][1]) / 2 + 0.0001,
                "name": "Requested coordinate",
            }
            request = PLAN_REQUEST_ADAPTER.validate_python(
                {
                    "schema_version": 1,
                    "kind": "waypoint_route",
                    "name": f"Café & forêt — {shape}",
                    "topology": topology,
                    "start": {
                        "lon": geometry[0][0],
                        "lat": geometry[0][1],
                        "name": "Trailhead",
                    },
                    "end": {
                        "lon": geometry[-1][0],
                        "lat": geometry[-1][1],
                        "name": "Finish",
                    }
                    if topology == "point_to_point"
                    else None,
                    "routing_profile": profile.id,
                    "candidate_count": 2,
                    "seed": 35,
                    "distance_objective": {
                        "target_m": 3_000.0,
                        "tolerance_m": 500.0,
                        "maximum_m": None,
                        "priority": "flexible",
                    },
                    "preferences": {
                        "nature": "off",
                        "loop_geometry": "off",
                        "path_selection": "shortest",
                    },
                    "waypoint_order": "fixed",
                    "waypoints": [
                        {
                            "id": "named-point",
                            "name": "Well & <place>",
                            "coordinate": coordinate,
                            "constraint_strength": "exact",
                        }
                    ],
                }
            )
            distance = 2_650.0
            route = RouteResult(
                name=request.name,
                routing_profile=profile.id,
                summary=RouteSummary(
                    distance_m=distance,
                    duration_ms=1_234_567,
                    input_point_count=3,
                    routed_point_count=len(geometry),
                ),
                geometry=geometry,
                analysis=RouteAnalyzer().analyze(
                    geometry, distance, {}, activity_kind=profile.activity_kind
                ),
            )
            draft = CandidateDraft(
                route=route,
                routing_points=(),
                topology=topology,
                construction="synthetic_native_fixture",
                search_family="waypoint_control",
            )
            points = [
                {"lat": geometry[0][1], "lon": geometry[0][0]},
                {"lat": coordinate["lat"], "lon": coordinate["lon"]},
                {"lat": geometry[-1][1], "lon": geometry[-1][0]},
            ]
            traversal = build_plan_traversal(request, draft)
            snapped = [
                points[0],
                {
                    "lat": traversal.anchors[1].routed_coordinate.lat,
                    "lon": traversal.anchors[1].routed_coordinate.lon,
                },
                points[-1],
            ]
            cases.append(
                {
                    "id": f"{profile.id}/{shape}",
                    "request": request.model_dump(mode="json"),
                    "native_draft": {
                        "candidate_id": f"synthetic-{profile.id}-{shape}",
                        "profile": profile.id,
                        "engine": "valhalla-mobile",
                        "engine_version": "synthetic-test",
                        "pack_id": "synthetic-test-pack",
                        "geometry": geometry,
                        "distance_m": distance,
                        "duration_s": 1_234.567,
                        "requested_points": points,
                        "snapped_points": snapped,
                    },
                    "expected": {
                        "signature": candidate_signature(route, topology=topology),
                        "traversal": traversal.model_dump(mode="json"),
                        "analysis": route.analysis.model_dump(mode="json"),
                    },
                }
            )
    return {"cases": cases}


def render_candidate_fixture() -> str:
    return json.dumps(candidate_fixture_payload(), ensure_ascii=False, indent=2) + "\n"


def test_unknown_analysis_templates_match_domain_analyzer() -> None:
    assert (STATIC_DIRECTORY / "local_analysis_templates.js").read_text() == (
        render_local_analysis_templates()
    )


def test_local_candidate_fixture_matches_canonical_python_contracts() -> None:
    assert FIXTURE.read_text() == render_candidate_fixture()
