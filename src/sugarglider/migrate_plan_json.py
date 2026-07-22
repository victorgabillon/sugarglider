#!/usr/bin/env python3
"""Convert one known pre-PR14 request JSON file to canonical schema version 1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sugarglider.planning.models import PLAN_REQUEST_ADAPTER

type JsonObject = dict[str, Any]


class MigrationError(ValueError):
    """The input is unknown or would require an unsafe guess."""


def migrate_document(
    source: JsonObject,
    *,
    target_distance_m: float | None = None,
    topology: str | None = None,
    start_index: int | None = None,
    end_index: int | None = None,
) -> tuple[JsonObject, tuple[str, ...]]:
    """Return a validated canonical document and every explicit assumption."""
    if source.get("schema_version") == 1:
        if any(
            value is not None
            for value in (target_distance_m, topology, start_index, end_index)
        ):
            raise MigrationError("migration overrides cannot modify canonical input")
        canonical = PLAN_REQUEST_ADAPTER.validate_python(source)
        return canonical.model_dump(mode="json"), ("input is already canonical",)
    if "kind" in source or "schema_version" in source:
        raise MigrationError("unsupported schema version or incomplete canonical input")
    if _looks_like_auto_tour(source):
        migrated, assumptions = _migrate_auto_tour(
            source,
            target_distance_m=target_distance_m,
            topology_override=topology,
        )
    elif "points" in source:
        migrated, assumptions = _migrate_waypoint(
            source,
            target_distance_m=target_distance_m,
            topology_override=topology,
            start_index=start_index,
            end_index=end_index,
        )
    else:
        raise MigrationError("unrecognized legacy request shape")
    canonical = PLAN_REQUEST_ADAPTER.validate_python(migrated)
    return canonical.model_dump(mode="json"), tuple(assumptions)


def _looks_like_auto_tour(source: JsonObject) -> bool:
    markers = {
        "requested_places",
        "hard_points",
        "preferred_poi_ids",
        "direction_preference",
        "distance_priority",
        "scenic_preference",
        "drinking_water_preference",
    }
    return bool(markers.intersection(source))


def _migrate_auto_tour(
    source: JsonObject,
    *,
    target_distance_m: float | None,
    topology_override: str | None,
) -> tuple[JsonObject, list[str]]:
    assumptions: list[str] = []
    start = source.get("start")
    end = source.get("end")
    if start is None:
        raise MigrationError("legacy Auto Tour has no explicit start")
    topology = topology_override or source.get("route_topology")
    if topology_override is not None:
        assumptions.append(f"used topology override {topology_override}")
    if topology in (None, "auto"):
        topology = "point_to_point" if end is not None else "loop"
        assumptions.append(f"resolved topology as {topology} from explicit endpoints")
    if topology not in {"loop", "point_to_point"}:
        raise MigrationError("unknown legacy Auto Tour topology")
    if topology == "loop" and end is not None:
        raise MigrationError("loop Auto Tour contains an ambiguous end")
    if topology == "point_to_point" and end is None:
        raise MigrationError("point-to-point Auto Tour has no end")

    raw_stops = source.get("requested_places")
    if raw_stops is None and "points" in source:
        raw_stops = [
            point
            for point in source["points"]
            if not _same_coordinate(point, start)
            and not (end is not None and _same_coordinate(point, end))
        ]
        assumptions.append("interpreted legacy Auto Tour points as requested stops")
        removed_endpoints = len(source["points"]) - len(raw_stops)
        if removed_endpoints:
            assumptions.append(
                f"removed {removed_endpoints} requested-stop duplicate(s) of endpoints"
            )
    if not isinstance(raw_stops, list):
        raise MigrationError("legacy requested stops are not an array")
    stops = [
        _migrate_stop(value, index=index, assumptions=assumptions)
        for index, value in enumerate(raw_stops)
    ]
    return (
        {
            "schema_version": 1,
            "kind": "auto_tour",
            "name": source.get("name", "Sugarglider Auto Tour"),
            "topology": topology,
            "start": start,
            "end": end if topology == "point_to_point" else None,
            "routing_profile": source.get("profile", "hike"),
            "candidate_count": source.get("candidate_count", 3),
            "seed": source.get("seed", 0),
            "distance_objective": _distance_objective(
                source, target_distance_m=target_distance_m
            ),
            "preferences": _auto_tour_preferences(source, topology=topology),
            "hard_waypoints": [
                _migrate_exact_waypoint(point, index)
                for index, point in enumerate(source.get("hard_points", []), start=1)
            ],
            "requested_stops": stops,
            "preferred_discovered_poi_ids": source.get("preferred_poi_ids", []),
            "free_poi_spur_physical_m": source.get("free_poi_spur_repeated_m", 200.0),
        },
        assumptions,
    )


def _migrate_stop(value: object, *, index: int, assumptions: list[str]) -> JsonObject:
    if not isinstance(value, dict):
        raise MigrationError("legacy requested stop is not an object")
    coordinate = value.get(
        "coordinate", value if {"lat", "lon"} <= value.keys() else None
    )
    if not isinstance(coordinate, dict):
        raise MigrationError("legacy requested stop has no coordinate")
    name = value.get("name") or coordinate.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MigrationError("legacy requested stop has no name")
    stop_id = value.get("id")
    if not isinstance(stop_id, str) or not stop_id:
        stable_index = value.get("original_index", index)
        stop_id = f"migrated-requested-stop-{stable_index}"
        assumptions.append(f"assigned requested stop ID {stop_id}")
    migrated: JsonObject = {
        "id": stop_id,
        "name": name,
        "semantic_coordinate": coordinate,
        "importance": value.get("importance", "must_visit"),
        "constraint_strength": "approach",
        "osm_reference": value.get("osm_reference"),
        "access_search_radius_m": value.get(
            "access_search_radius_m", value.get("visit_radius_m", 500.0)
        ),
        "maximum_best_effort_distance_m": None,
        "approach_override": value.get("approach_override"),
    }
    if "arrival_tolerance_m" in value:
        assumptions.append(
            f"removed user arrival tolerance from requested stop {stop_id}"
        )
    return migrated


def _migrate_waypoint(
    source: JsonObject,
    *,
    target_distance_m: float | None,
    topology_override: str | None,
    start_index: int | None,
    end_index: int | None,
) -> tuple[JsonObject, list[str]]:
    raw_points = source.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise MigrationError("legacy waypoint request needs at least two points")
    assumptions: list[str] = []
    explicit_start = source.get("start")
    explicit_end = source.get("end")
    topology = topology_override or source.get("route_topology")
    if topology_override is not None:
        assumptions.append(f"used topology override {topology_override}")
    close = source.get("close_loop")
    if topology in (None, "auto"):
        if close is True:
            topology = "loop"
        elif close is False or explicit_end is not None:
            topology = "point_to_point"
        else:
            raise MigrationError("legacy waypoint topology is ambiguous")
        assumptions.append(f"resolved topology as {topology}")
    if topology not in {"loop", "point_to_point"}:
        raise MigrationError("unknown legacy waypoint topology")

    points = list(raw_points)
    start = explicit_start
    if start_index is not None:
        if explicit_start is not None:
            raise MigrationError("start-index conflicts with an explicit start")
        if not 0 <= start_index < len(points):
            raise MigrationError("start-index is outside the points array")
        start = points.pop(start_index)
        assumptions.append(f"used point {start_index} as explicit start")
    if start is None:
        start = points.pop(0)
        assumptions.append("promoted the first legacy point to explicit start")
    end = explicit_end
    if end_index is not None:
        if explicit_end is not None:
            raise MigrationError("end-index conflicts with an explicit end")
        adjusted_end_index = end_index
        if start_index is not None and end_index > start_index:
            adjusted_end_index -= 1
        if not 0 <= adjusted_end_index < len(points):
            raise MigrationError("end-index is outside the points array")
        end = points.pop(adjusted_end_index)
        assumptions.append(f"used point {end_index} as explicit end")
    if topology == "point_to_point" and end is None:
        if not points:
            raise MigrationError("point-to-point legacy request has no end")
        end = points.pop()
        assumptions.append("promoted the last legacy point to explicit end")
    if topology == "loop":
        end = None
        if points and _same_coordinate(points[-1], start):
            points.pop()
            assumptions.append("removed the duplicated legacy loop closure")
    if topology == "loop" and not points:
        raise MigrationError("canonical waypoint loop needs an interior waypoint")

    target = (
        target_distance_m
        if target_distance_m is not None
        else source.get("target_distance_m")
    )
    if target is None:
        raise MigrationError(
            "legacy waypoint route has no target distance; use --target-distance-m"
        )
    if target_distance_m is not None:
        assumptions.append(f"used target distance override {target_distance_m:g} m")
    old_order = source.get("point_order_mode", "fixed")
    if old_order not in {"fixed", "optimize_loop", "optimize_path"}:
        raise MigrationError("unknown legacy waypoint order mode")
    return (
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": source.get("name", "Sugarglider Waypoint Route"),
            "topology": topology,
            "start": start,
            "end": end,
            "routing_profile": source.get("profile", "hike"),
            "candidate_count": source.get("candidate_count", 3),
            "seed": source.get("seed", 0),
            "distance_objective": {
                "target_m": target,
                "tolerance_m": source.get("tolerance_m", 2_000),
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": _waypoint_preferences(source, topology=topology),
            "waypoints": [
                _migrate_route_waypoint(point, index)
                for index, point in enumerate(points, start=1)
            ],
            "waypoint_order": "fixed" if old_order == "fixed" else "optimize",
        },
        assumptions,
    )


def _distance_objective(
    source: JsonObject, *, target_distance_m: float | None
) -> JsonObject:
    target = (
        target_distance_m
        if target_distance_m is not None
        else source.get("target_distance_m")
    )
    if target is None:
        raise MigrationError(
            "legacy Auto Tour has no target distance; use --target-distance-m"
        )
    return {
        "target_m": target,
        "tolerance_m": source.get("tolerance_m", 2_000),
        "maximum_m": source.get("maximum_distance_m"),
        "priority": source.get("distance_priority", "flexible"),
    }


def _common_preferences(source: JsonObject) -> JsonObject:
    return {
        "nature": source.get("nature_preference", "off"),
        "path_selection": source.get("path_selection_mode", "shortest"),
    }


def _auto_tour_preferences(source: JsonObject, *, topology: object) -> JsonObject:
    del topology
    return {
        **_common_preferences(source),
        "scenic": source.get("scenic_preference", "prefer"),
        "drinking_water": source.get("drinking_water_preference", "prefer"),
        "loop_geometry": source.get("loop_geometry_preference", "off"),
        "direction": source.get("direction_preference", "any"),
    }


def _waypoint_preferences(source: JsonObject, *, topology: object) -> JsonObject:
    del topology
    return {
        **_common_preferences(source),
        "loop_geometry": source.get("loop_geometry_preference", "off"),
    }


def _same_coordinate(left: object, right: object) -> bool:
    return (
        isinstance(left, dict)
        and isinstance(right, dict)
        and left.get("lat") == right.get("lat")
        and left.get("lon") == right.get("lon")
    )


def _migrate_exact_waypoint(value: object, index: int) -> JsonObject:
    if not isinstance(value, dict):
        raise MigrationError("legacy hard waypoint is not an object")
    return {
        "id": f"migrated-exact-waypoint-{index}",
        "name": value.get("name") or f"Exact waypoint {index}",
        "coordinate": value,
    }


def _migrate_route_waypoint(value: object, index: int) -> JsonObject:
    if not isinstance(value, dict):
        raise MigrationError("legacy waypoint is not an object")
    return {
        "id": f"migrated-route-waypoint-{index}",
        "name": value.get("name") or f"Waypoint {index}",
        "coordinate": value,
        "constraint_strength": "exact",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--target-distance-m", type=float)
    parser.add_argument("--topology", choices=("loop", "point_to_point"))
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    arguments = parser.parse_args()
    if arguments.output.exists() and not arguments.overwrite:
        parser.error(f"output already exists: {arguments.output}")
    try:
        source = json.loads(arguments.input.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            raise MigrationError("top-level JSON value must be an object")
        migrated, assumptions = migrate_document(
            source,
            target_distance_m=arguments.target_distance_m,
            topology=arguments.topology,
            start_index=arguments.start_index,
            end_index=arguments.end_index,
        )
    except (OSError, json.JSONDecodeError, MigrationError, ValueError) as exc:
        parser.error(str(exc))
    arguments.output.write_text(
        json.dumps(migrated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for assumption in assumptions:
        print(f"Assumption: {assumption}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
