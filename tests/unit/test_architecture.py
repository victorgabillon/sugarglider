"""Lightweight import and canonical-public-source architecture boundaries."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "sugarglider"


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(modules)


def test_dependency_direction_has_no_forbidden_reverse_imports() -> None:
    forbidden = {
        "pois": ("sugarglider.planning", "sugarglider.api", "sugarglider.web"),
        "routing": ("sugarglider.planning", "sugarglider.api", "sugarglider.web"),
        "domain": ("sugarglider.planning", "sugarglider.api", "sugarglider.web"),
        "analysis": ("sugarglider.planning", "sugarglider.api", "sugarglider.web"),
        "planning": ("sugarglider.api", "sugarglider.web"),
    }
    violations: list[str] = []
    for package, prefixes in forbidden.items():
        for path in sorted((SOURCE / package).rglob("*.py")):
            for module in _imports(path):
                if module.startswith(prefixes):
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
    assert violations == []


def test_planning_has_no_hidden_hike_defaults_or_raw_backend_profile_names() -> None:
    planning = SOURCE / "planning"
    forbidden_backend_names = ('"bike"', '"mtb"', '"racingbike"')
    violations: list[str] = []
    for path in sorted(planning.rglob("*.py")):
        source = path.read_text()
        if 'profile: RoutingProfileId = "hike"' in source:
            violations.append(f"{path.relative_to(ROOT)}: hidden hike default")
        if path.name not in {"profile_quality.py"}:
            for value in forbidden_backend_names:
                if value in source:
                    violations.append(f"{path.relative_to(ROOT)}: raw {value}")
    assert violations == []


def test_superseded_generation_and_tours_packages_have_no_source_modules() -> None:
    for package in ("generation", "tours"):
        directory = SOURCE / package
        assert not directory.exists() or not tuple(directory.rglob("*.py"))


def test_runtime_planning_has_no_adapter_or_removed_package_imports() -> None:
    planning = SOURCE / "planning"
    assert not (planning / "adapters.py").exists()
    prohibited = (
        "sugarglider.planning.adapters",
        "sugarglider.generation",
        "sugarglider.tours",
    )
    violations = {
        str(path.relative_to(ROOT)): module
        for path in planning.rglob("*.py")
        for module in _imports(path)
        if module.startswith(prohibited)
    }
    assert violations == {}


def test_runtime_source_contains_no_obsolete_planning_symbols() -> None:
    runtime_files = tuple(
        path for path in SOURCE.rglob("*.py") if path.name != "migrate_plan_json.py"
    ) + tuple(SOURCE.rglob("*.js"))
    prohibited = re.compile(
        r"\b(close_loop|route_topology|visit_radius_m|requested_places|hard_points|"
        r"point_order_mode|optimize_loop|optimize_path|TourPoiVisit|satisfied|missed|"
        r"inserted_poi_reward)\b"
    )
    violations = {
        str(path.relative_to(ROOT)): sorted(set(prohibited.findall(path.read_text())))
        for path in runtime_files
        if prohibited.search(path.read_text(encoding="utf-8"))
    }
    assert violations == {}


def test_runtime_planning_source_contains_no_migration_concepts() -> None:
    prohibited = re.compile(
        r"Legacy Python compatibility|legacy recommendation|compatibility helper|"
        r'ProposalVariant[^\n]*"legacy"',
        re.IGNORECASE,
    )
    violations = {
        str(path.relative_to(ROOT)): prohibited.findall(
            path.read_text(encoding="utf-8")
        )
        for path in (SOURCE / "planning").rglob("*.py")
        if prohibited.search(path.read_text(encoding="utf-8"))
    }
    assert violations == {}


def test_native_waypoint_modules_are_bounded_and_have_no_raw_backend_calls() -> None:
    waypoint = SOURCE / "planning" / "waypoint"
    files = tuple(sorted(waypoint.glob("*.py")))
    line_violations = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in files
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert line_violations == {}
    assert not (waypoint / "candidates.py").exists()
    obsolete = re.compile(
        r"waypoint\.(candidates|engine_models|proposals|ranking)|"
        r"RouteGenerationService|WaypointSearchRequest"
    )
    obsolete_violations = {
        path.name: obsolete.findall(path.read_text(encoding="utf-8"))
        for path in files
        if obsolete.search(path.read_text(encoding="utf-8"))
    }
    assert obsolete_violations == {}
    raw_call = re.compile(
        r"(?:self\._backend|(?<!context\.routes\.)\bbackend)\."
        r"(?:route|round_trip|alternative_routes|isochrone)\("
    )
    raw_violations = {
        path.name: raw_call.findall(path.read_text(encoding="utf-8"))
        for path in files
        if raw_call.search(path.read_text(encoding="utf-8"))
    }
    assert raw_violations == {}


def test_native_auto_tour_modules_are_bounded_and_gateway_only() -> None:
    auto_tour = SOURCE / "planning" / "auto_tour"
    files = tuple(sorted(auto_tour.glob("*.py")))
    assert not (auto_tour / "candidates.py").exists()
    assert not (auto_tour / "engine_models.py").exists()
    assert not (auto_tour / "legacy_selection.py").exists()
    assert {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in files
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    } == {}
    raw_call = re.compile(
        r"(?:self\._backend|(?<!context\.routes\.)\bbackend)\."
        r"(?:route|round_trip|alternative_routes|isochrone)\("
    )
    assert {
        path.name: raw_call.findall(path.read_text(encoding="utf-8"))
        for path in files
        if raw_call.search(path.read_text(encoding="utf-8"))
    } == {}
    duplicated_route_counters = re.compile(
        r"\b(?:route_requests|skeleton_requests|poi_requests|"
        r"requested_place_requests|repair_requests|alternative_requests|"
        r"external_cache_hits|cache_misses)\b"
    )
    assert {
        path.name: duplicated_route_counters.findall(path.read_text(encoding="utf-8"))
        for path in files
        if duplicated_route_counters.search(path.read_text(encoding="utf-8"))
    } == {}


def test_all_ordinary_planning_modules_fit_the_physical_line_limit() -> None:
    files = tuple(sorted((SOURCE / "planning").rglob("*.py")))
    assert {
        str(path.relative_to(SOURCE)): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in files
        if len(path.read_text(encoding="utf-8").splitlines()) > 800
    } == {}
