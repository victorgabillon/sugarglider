"""Architecture and browser-safety contracts for PR23 outings."""

import ast
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "sugarglider"
OUTINGS = SOURCE / "outings"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_domain_dependency_direction_has_no_cycles_or_fastapi() -> None:
    planning_imports = {
        name for path in (SOURCE / "planning").rglob("*.py") for name in _imports(path)
    }
    outing_imports = {name for path in OUTINGS.glob("*.py") for name in _imports(path)}
    saved_imports = {
        name
        for path in (SOURCE / "saved_routes").glob("*.py")
        for name in _imports(path)
    }
    assert not any(
        name.startswith(("sugarglider.outings", "sugarglider.saved_routes"))
        for name in planning_imports
    )
    assert not any(
        name.startswith(("fastapi", "sugarglider.saved_routes"))
        for name in outing_imports
    )
    assert not any(name.startswith("sugarglider.outings") for name in saved_imports)


def test_sqlite_is_confined_to_approved_adapters() -> None:
    production_importers = {
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*.py")
        if "sqlite3" in _imports(path)
    }
    assert production_importers == {
        "outings/sqlite_repository.py",
        "saved_routes/sqlite_repository.py",
    }


def test_outing_handlers_are_synchronous_and_api_is_the_saved_route_bridge() -> None:
    source = (SOURCE / "api" / "outings.py").read_text()
    tree = ast.parse(source)
    handlers = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"get", "post", "delete"}
            for decorator in node.decorator_list
        )
    }
    assert handlers
    assert all(isinstance(node, ast.FunctionDef) for node in handlers.values())
    assert "SavedRouteServiceDependency" in source
    assert "OutingServiceDependency" in source


def test_outing_http_and_capabilities_are_isolated_from_map_and_storage() -> None:
    outings = (STATIC_DIRECTORY / "outings.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    app = (STATIC_DIRECTORY / "app.js").read_text()
    all_frontend = "\n".join(path.read_text() for path in STATIC_DIRECTORY.glob("*.js"))
    assert "/v2/outings" in outings
    assert "/v2/outings" not in map_source
    assert "/v2/outings" not in app
    assert "fetch(" not in map_source
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "geolocation",
        "EventSource",
        "WebSocket",
    ):
        assert forbidden not in all_frontend


def test_invitation_fragment_is_scrubbed_and_never_uses_a_query() -> None:
    source = (STATIC_DIRECTORY / "outings.js").read_text()
    assert "#invite=" in source
    assert "historyObject.replaceState" in source
    assert "location.hash" in source
    assert "?invite=" not in source
    assert "url.origin !== origin" in source


def test_outing_snapshot_display_has_no_fake_plan_or_profile_catalogue() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    start = controller[controller.index("export async function startOutingPage") :]
    assert "getConfig()" in start
    assert "getOuting(slug)" in start
    for forbidden in (
        "getRoutingProfiles",
        "getPoiStatus",
        "generatePlan",
        "visualizeRoute",
        "getSavedRoute",
        "PlanResult",
        "search_diagnostics:",
    ):
        assert forbidden not in start
    assert (
        "planned_route.candidate.route.geometry"
        in (STATIC_DIRECTORY / "map.js").read_text()
    )
    assert "search diagnostics not applicable" in view


def test_create_share_join_and_receipts_follow_explicit_memory_only_flows() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    state = (STATIC_DIRECTORY / "state.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    assert "createOutingFromSavedRoute" in controller
    assert (
        "navigator.share"
        not in controller[
            controller.index(
                "async function createOutingFromSavedRoute"
            ) : controller.index("async function copyOutingLink")
        ]
    )
    assert "AbortError" in controller
    for field in (
        "outingSnapshot",
        "outingDisplay",
        "selectedOutingParticipantId",
        "outingOwnerReceipt",
        "outingParticipantReceipt",
        "outingInviteToken",
    ):
        assert field in state
    invalidate = state[state.index("export function invalidateCandidates") :]
    invalidate = invalidate[: invalidate.index("export function", 1)]
    assert "outingOwnerReceipt" not in invalidate
    assert "outingParticipantReceipt" not in invalidate
    assert "savedRouteSlugForOuting" in view


def test_substantial_outing_workflows_stay_out_of_app_coordinator() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text()
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    workflow_names = (
        "createOutingFromSavedRoute",
        "copyOutingLink",
        "shareCurrentOutingInvitation",
        "removeCurrentOuting",
        "joinCurrentOuting",
        "downloadMyOutingGpx",
        "leaveCurrentOuting",
        "outingViewHandlers",
    )
    for name in workflow_names:
        assert name not in app
        assert name in controller
    assert "function startOutingPage" not in app
    assert "startOutingPage(currentOutingSlug" in app


def test_outing_map_branch_precedes_ordinary_candidate_rendering() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text()
    render = app[
        app.index("function renderMapData()") : app.index("function candidateBadges")
    ]
    outing_branch = render.index("if (state.outingDisplay && state.outingSnapshot)")
    assert outing_branch < render.index("renderCandidates(")
    assert render.index("renderOutingRoutes(", outing_branch) < render.index("return;")
    assert "isImmutableSnapshotDisplay()" in render


def test_outing_interactions_use_only_outing_http_and_route_layers() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    outings = (STATIC_DIRECTORY / "outings.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    render = map_source[
        map_source.index("export function renderOutingRoutes") : map_source.index(
            "export function outingRouteRenderDiagnostics"
        )
    ]
    for forbidden in (
        "/v2/visualization",
        "/v2/plans/generate",
        "/v2/plans/reverse",
        "/v2/routing-profiles",
        "/v2/pois",
        "/v2/saved-routes",
        "GraphHopper",
    ):
        assert forbidden not in controller
        assert forbidden not in outings
    assert 'clearByPrefix("candidate-")' in render
    assert 'clearByPrefix("outing-route-")' in render
    assert "const sourceId = `outing-route-${index}`" in render
    assert "candidate-${index}" not in render


def test_outing_creation_busy_and_zero_participant_view_are_explicit() -> None:
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    assert '["running", "reversing"].includes(state.request.status)' in view
    assert "outing.participants.length" in view
    assert "state.outingSnapshot.participants.forEach" in view


def test_outing_mutations_are_single_flight_and_disable_stable_controls() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    html = (STATIC_DIRECTORY / "index.html").read_text()
    assert "let outingMutationPending = false;" in controller
    assert 'id="join-outing"' in html
    for name in (
        "createOutingFromSavedRoute",
        "removeCurrentOuting",
        "joinCurrentOuting",
        "leaveCurrentOuting",
    ):
        start = controller.index(f"async function {name}")
        next_function = controller.find("\nasync function ", start + 1)
        if next_function < 0:
            next_function = controller.find("\nfunction ", start + 1)
        implementation = controller[start:next_function]
        assert "beginOutingMutation()" in implementation
        assert "finally {" in implementation
        assert "finishOutingMutation();" in implementation
    controls = view[
        view.index("export function setOutingMutationControls") : view.index(
            "export function renderOutingReceipt"
        )
    ]
    for control_id in (
        "show-create-outing",
        "create-outing",
        "join-outing",
        "delete-outing",
        "leave-outing",
    ):
        assert f'byId("{control_id}").disabled' in controls
    assert "classList.remove" not in controls


def test_new_modules_remain_focused_and_below_size_limit() -> None:
    paths = [
        *OUTINGS.glob("*.py"),
        SOURCE / "api" / "outings.py",
        STATIC_DIRECTORY / "outings.js",
        STATIC_DIRECTORY / "outing_controller.js",
        STATIC_DIRECTORY / "outing_view.js",
    ]
    assert all(len(path.read_text().splitlines()) <= 800 for path in paths)
    assert not any(
        path.name.endswith((".sqlite", ".sqlite3", ".gpx", ".png"))
        for path in OUTINGS.iterdir()
    )
