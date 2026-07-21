"""Build map sections from the exact route-analysis edge classifiers."""

from dataclasses import dataclass
from typing import Literal

from sugarglider.analysis.backtracking import (
    DirectedEdgeTraversal,
    classify_immediate_backtracking,
)
from sugarglider.analysis.route import (
    ProjectedGeometryEdge,
    classify_repeated_edges,
    known_edge_id,
    project_geometry_edges,
)
from sugarglider.analysis.visualization_models import (
    LineStringGeometry,
    RouteSectionFeature,
    RouteSectionProperties,
    RouteVisualization,
)
from sugarglider.domain.analysis import DetailValue
from sugarglider.domain.models import GeoJsonPosition, RouteResult
from sugarglider.nature.analysis import NatureEdgeContext, NatureRouteAnalyzer


@dataclass(frozen=True)
class _SectionKey:
    kind: Literal["normal", "repeated", "immediate_backtrack"]
    edge_id: int | None
    surface: DetailValue
    road_class: DetailValue
    nature: NatureEdgeContext | None


def _detail(edge: ProjectedGeometryEdge, name: str) -> DetailValue:
    present, value = edge.detail(name)
    return value if present else None


def _key(
    edge: ProjectedGeometryEdge,
    *,
    repeated: bool,
    immediate_backtrack: bool,
    nature: NatureEdgeContext | None,
) -> _SectionKey:
    kind: Literal["normal", "repeated", "immediate_backtrack"]
    if immediate_backtrack:
        kind = "immediate_backtrack"
    elif repeated:
        kind = "repeated"
    else:
        kind = "normal"
    return _SectionKey(
        kind=kind,
        edge_id=known_edge_id(edge),
        surface=_detail(edge, "surface"),
        road_class=_detail(edge, "road_class"),
        nature=nature,
    )


def build_route_visualization(
    route: RouteResult,
    nature_analyzer: NatureRouteAnalyzer | None = None,
) -> RouteVisualization:
    """Classify and group route geometry without changing the posted result."""
    edges = project_geometry_edges(
        geometry=route.geometry,
        route_distance_m=route.summary.distance_m,
        path_details=route.path_details,
    ).edges
    repeated = classify_repeated_edges(edges)
    immediate = classify_immediate_backtracking(
        tuple(
            DirectedEdgeTraversal(
                edge_id=known_edge_id(edge),
                start=edge.start,
                end=edge.end,
                distance_m=edge.distance_m,
            )
            for edge in edges
        )
    )
    nature_contexts: tuple[NatureEdgeContext | None, ...] = (
        nature_analyzer.edge_contexts(edges)
        if nature_analyzer is not None
        else tuple(None for _edge in edges)
    )

    features: list[RouteSectionFeature] = []
    section_key: _SectionKey | None = None
    coordinates: list[GeoJsonPosition] = []
    distance_m = 0.0

    def finish_section() -> None:
        nonlocal coordinates, distance_m
        if section_key is None:
            return
        features.append(
            RouteSectionFeature(
                geometry=LineStringGeometry(coordinates=tuple(coordinates)),
                properties=RouteSectionProperties(
                    kind=section_key.kind,
                    distance_m=distance_m,
                    edge_id=section_key.edge_id,
                    surface=section_key.surface,
                    road_class=section_key.road_class,
                    nature_class=(
                        section_key.nature.nature_class
                        if section_key.nature is not None
                        else None
                    ),
                    park_or_protected=(
                        section_key.nature.park_or_protected
                        if section_key.nature is not None
                        else None
                    ),
                    near_water=(
                        section_key.nature.near_water
                        if section_key.nature is not None
                        else None
                    ),
                ),
            )
        )
        coordinates = []
        distance_m = 0.0

    for index, edge in enumerate(edges):
        edge_key = _key(
            edge,
            repeated=repeated[index],
            immediate_backtrack=immediate[index],
            nature=nature_contexts[index],
        )
        if edge_key != section_key:
            finish_section()
            section_key = edge_key
            coordinates = [edge.start, edge.end]
            distance_m = edge.distance_m
        else:
            coordinates.append(edge.end)
            distance_m += edge.distance_m
    finish_section()
    return RouteVisualization(features=tuple(features))
