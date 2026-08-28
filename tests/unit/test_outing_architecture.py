"""Architecture and browser-safety contracts for PR23 outings."""

import ast
import re
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
        "outings/live_sqlite_repository.py",
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


def test_outing_http_geolocation_and_eventsource_are_scoped_to_focused_modules() -> (
    None
):
    outings = (STATIC_DIRECTORY / "outings.js").read_text()
    live = (STATIC_DIRECTORY / "outing_live.js").read_text()
    tracking = (STATIC_DIRECTORY / "outing_tracking.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    app = (STATIC_DIRECTORY / "app.js").read_text()
    sources = {path.name: path.read_text() for path in STATIC_DIRECTORY.glob("*.js")}
    all_frontend = "\n".join(sources.values())
    assert "/v2/outings" in outings
    assert "/v2/outings" not in map_source
    assert "/v2/outings" not in app
    assert "fetch(" not in map_source
    for term in ("navigator.geolocation", "watchPosition", "clearWatch"):
        assert term in tracking
        assert {name for name, source in sources.items() if term in source} == {
            "outing_tracking.js",
            "planner_location.js",
        }
    assert {name for name, source in sources.items() if "EventSource" in source} == {
        "outing_live.js"
    }
    for path_fragment in ("/live", "/events", "/position"):
        assert path_fragment in live
        owners = {name for name, source in sources.items() if path_fragment in source}
        expected = {"outing_live.js"}
        if path_fragment in {"/live", "/events"}:
            expected.add("service_worker_policy.js")
        assert owners == expected
    assert {
        name
        for name, source in sources.items()
        if "X-Sugarglider-Participant-Token" in source
    } == {"outing_live.js", "outings.js"}
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "WebSocket",
        "sendBeacon",
        "Notification",
        "wakeLock",
    ):
        assert forbidden not in all_frontend
    assert {name for name, source in sources.items() if "indexedDB" in source} == {
        "pwa_store.js"
    }
    assert {name for name, source in sources.items() if "serviceWorker" in source} == {
        "pwa_controller.js"
    }
    event_stream = live[live.index("export function connectOutingLiveEvents") :]
    event_source_line = next(
        line for line in event_stream.splitlines() if "new EventSource" in line
    )
    assert "?" not in event_source_line
    assert "#" not in event_source_line
    assert "token" not in event_stream.lower()


def test_pr24_live_invariants_are_durable_repository_rules() -> None:
    rules = (ROOT / "AGENTS.md").read_text()
    for required in (
        "live positions belong to participant identity",
        "No owner, join, or participant capability may enter SSE",
        "current-position table is authoritative",
        "Client sequence, not captured time or receive time",
        "Stale and expired are distinct",
        "participant leave atomically clears",
        "durable per-outing cursor",
        "explicit SQLite read transaction",
        "Async SSE handlers must offload every synchronous SQLite",
        "historical-location API",
    ):
        assert required in rules
    for required in (
        "explicit participant click",
        "foreground-only",
        "must never request location permission",
        "capability-free EventSource",
        "JavaScript in-memory receipt",
        "single-flight",
        "latest unsent",
        "exact unsnapped participant coordinates",
        "server-controlled timestamps",
        "explicit Stop is the reliable action",
        "no PWA",
    ):
        assert required in rules


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


def test_outing_display_does_not_schedule_planner_poi_requests() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text()
    fetch = app[
        app.index("async function fetchViewportPois") : app.index(
            "function schedulePoiRefresh"
        )
    ]
    schedule = app[
        app.index("function schedulePoiRefresh") : app.index(
            "function updateOptionsFromControls"
        )
    ]
    guard = "if (state.outingDisplay) return;"
    assert guard in fetch
    assert guard in schedule


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
        STATIC_DIRECTORY / "outing_view.js",
    ]
    assert all(len(path.read_text().splitlines()) <= 800 for path in paths)
    assert not any(
        path.name.endswith((".sqlite", ".sqlite3", ".gpx", ".png"))
        for path in OUTINGS.iterdir()
    )


def test_pr25_live_client_validates_sse_and_uses_capability_free_public_reads() -> None:
    live = (STATIC_DIRECTORY / "outing_live.js").read_text()
    assert "encodeURIComponent(slug)" in live
    assert 'method: "PUT"' in live
    assert 'method: "DELETE"' in live
    assert "[PARTICIPANT_TOKEN_HEADER]: participantToken" in live
    assert "signal: options.signal" in live
    assert "keepalive: options.keepalive === true" in live
    assert 'source.addEventListener("open"' in live
    assert 'source.addEventListener("error"' in live
    for event_name in (
        "snapshot",
        "reset",
        "position_updated",
        "position_cleared",
        "outing_closed",
    ):
        assert f'"{event_name}"' in live
    assert "event.lastEventId" in live
    assert "payload[identifierField]" in live
    assert "handlers.malformed?.()" in live
    for forbidden in ("console.", "location.hash", "URLSearchParams"):
        assert forbidden not in live


def test_pr25_public_live_reducer_is_dom_free_latest_only_and_gap_safe() -> None:
    reducer = (STATIC_DIRECTORY / "outing_live_state.js").read_text()
    for exported in (
        "emptyOutingLiveState",
        "replaceWithSnapshot",
        "applyLiveEvent",
        "upsertOptimisticPosition",
        "removeOptimisticPosition",
        "livePositionForParticipant",
        "liveFreshness",
        "visibleLivePositions",
    ):
        assert f"export function {exported}" in reducer
    assert 'status: "recovery_required"' in reducer
    assert "normalized.event_id !== current.cursor + 1" in reducer
    assert "normalized.event_id <= current.cursor" in reducer
    assert "Date.parse(normalized.generated_at) - clientNow" in reducer
    assert "snapshot.slug !== expectedSlug" in reducer
    assert "staleAfterSeconds >= expireAfterSeconds" in reducer
    assert "position?.schema_version !== 1" in reducer
    assert "event?.schema_version !== 1" in reducer
    assert "OFFSET_TIMESTAMP_PATTERN" in reducer
    assert 'typeof value === "number"' in reducer
    assert (
        re.search(
            r"\bNumber\(\s*(?:position|coordinate|snapshot|event)",
            reducer,
        )
        is None
    )
    assert 'return "expired"' in reducer
    assert 'return serverNow >= staleAt ? "stale" : "fresh"' in reducer
    assert "positions: upsertPosition" in reducer
    for forbidden in (
        "document.",
        "window.",
        "navigator.",
        "participant_token",
        "route.geometry",
        "positionHistory",
        "coordinateHistory",
    ):
        assert forbidden not in reducer


def test_pr25_tracker_is_explicit_single_flight_and_latest_sample_only() -> None:
    tracker = (STATIC_DIRECTORY / "outing_tracking.js").read_text()
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    assert "let pendingSample = null;" in tracker
    assert "let generationCounter = 0;" in tracker
    assert "let activePublish = null;" in tracker
    assert "activePublish === operation" in tracker
    assert "activePublish = operation;" in tracker
    assert "receivePosition(generation, position)" in tracker
    assert "receiveError(generation, error)" in tracker
    assert "pendingSample = {" in tracker
    assert "let requestInFlight" not in tracker
    assert "PUBLICATION_INTERVAL_MS = 5_000" in tracker
    assert "MAXIMUM_RETRY_MS = 30_000" in tracker
    assert "Math.max(now, lastAcceptedSequence + 1)" in tracker
    assert "Number.MAX_SAFE_INTEGER" in tracker
    assert "outing_position_sequence_conflict" in tracker
    assert "conflictRetried" in tracker
    assert "sessionHasUncertainPublish" in tracker
    assert "waitForPublishOutcome" in tracker
    assert "terminalPromise" in tracker
    assert "latestSamples" not in tracker
    assert "pendingSamples" not in tracker
    assert "coordinates.push" not in tracker
    assert "watchPosition(" in tracker
    assert "startCurrentOutingPositionSharing" in controller
    start_handler = controller[
        controller.index(
            "function startCurrentOutingPositionSharing"
        ) : controller.index("async function stopCurrentOutingPositionSharing")
    ]
    assert "tracker.start(receipt" in start_handler


def test_pr25_geolocation_normalization_and_stop_lifecycle_are_bounded() -> None:
    tracker = (STATIC_DIRECTORY / "outing_tracking.js").read_text()
    normalize = tracker[
        tracker.index("export function normalizeGeolocationPosition") : tracker.index(
            "export function createOutingTracker"
        )
    ]
    for required in (
        "boundedPrimitiveNumber(latitude, -90, 90)",
        "boundedPrimitiveNumber(longitude, -180, 180)",
        "boundedPrimitiveNumber(accuracy, 0, 10_000)",
        "primitiveFiniteNumber(timestamp)",
        "capturedAt.toISOString()",
        "boundedOptional(position.coords.altitude, -1_000, 12_000)",
        "boundedOptional(position.coords.speed, 0, 150)",
    ):
        assert required in normalize
    assert re.search(r"\bNumber\(", normalize) is None
    stop = tracker[
        tracker.index("async function stop(") : tracker.index("function shutdown()")
    ]
    assert stop.index("invalidateLocalSession") < stop.index("waitForPublishOutcome")
    assert stop.index("waitForPublishOutcome") < stop.index("beginClear")
    invalidate = tracker[
        tracker.index("function invalidateLocalSession") : tracker.index(
            "function clearOwnedWatch"
        )
    ]
    assert "pendingSample = null" in invalidate
    assert "cancelCadenceTimer()" in invalidate
    assert "cancelRetryTimer()" in invalidate
    assert "if (abortPublish) activePublish?.controller.abort()" in invalidate
    clear_watch = tracker[
        tracker.index("function clearOwnedWatch") : tracker.index(
            "function cancelCadenceTimer"
        )
    ]
    assert "geolocation.clearWatch(watch.id)" in clear_watch
    assert "activeWatch = null" in clear_watch
    perform = tracker[
        tracker.index("async function performPublish") : tracker.index(
            "async function recoverSequence"
        )
    ]
    assert "if (activePublish === operation) activePublish = null" in perform
    assert "if (!ownsPublish(operation)) return outcome" in perform
    reset = tracker[
        tracker.index("function resetForNewSession") : tracker.index(
            "function invalidateLocalSession"
        )
    ]
    for reset_value in (
        "pendingSample = null",
        "lastPublishedAt = null",
        "retryDelayMs = INITIAL_RETRY_MS",
        "clearingFailed = false",
        "activePublish = null",
        "activeClear = null",
    ):
        assert reset_value in reset
    assert "lastAcceptedSequence = -1" in reset
    assert "currentPosition?.sequence" in tracker
    pagehide = tracker[
        tracker.index("function pagehide(") : tracker.index("function online()")
    ]
    assert "keepalive: true" in pagehide
    assert "abortPublish: true" in pagehide
    assert "sendBeacon" not in tracker


def test_pr25_viewer_join_creator_and_mutation_flows_never_auto_start() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    start_page = controller[controller.index("export async function startOutingPage") :]
    assert "connectCurrentOutingLiveEvents" not in start_page
    assert "startOutingLiveExperience(slug)" in start_page
    assert "startCurrentOutingPositionSharing" not in start_page
    create = controller[
        controller.index(
            "async function createOutingFromSavedRoute"
        ) : controller.index("async function copyOutingLink")
    ]
    join = controller[
        controller.index("async function joinCurrentOuting") : controller.index(
            "async function downloadMyOutingGpx"
        )
    ]
    assert "startCurrentOutingPositionSharing" not in create
    assert "startCurrentOutingPositionSharing" not in join
    assert join.index("const joined = await joinOuting(") < join.index(
        "outingMembershipRefresh.invalidate();"
    )
    assert join.index("outingMembershipRefresh.invalidate();") < join.index(
        "state.outingSnapshot = joined.outing;"
    )
    assert join.index("state.outingInviteToken = null;") < join.index(
        "showOutingView(state, outingViewHandlers());"
    )
    assert join.index("showOutingView(state, outingViewHandlers());") < join.index(
        "selectOutingParticipant(joined.participant_id);"
    )
    same_tab = controller[
        controller.index("async function enterCreatedOutingHere") : controller.index(
            "export function bindOutingController"
        )
    ]
    for receipt_field in ("slug", "participant_id", "participant_token"):
        assert f"{receipt_field}: receipt.{receipt_field}" in same_tab
    for forbidden in ("window.location", "startCurrentOutingPositionSharing"):
        assert forbidden not in same_tab
    history = same_tab[
        same_tab.index("window.history.replaceState") : same_tab.index(
            "prepareOutingPage"
        )
    ]
    assert "null" in history
    assert "`/o/${encodeURIComponent(receipt.slug)}`" in history
    for forbidden in ("participant_token", "owner_token", "join_token", "#", "?"):
        assert forbidden not in history
    assert "startOutingLiveExperience(receipt.slug)" in same_tab


def test_pr25_leave_and_delete_abort_tracking_before_ordinary_mutation() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    leave = controller[
        controller.index("async function leaveCurrentOuting") : controller.index(
            "function outingViewHandlers"
        )
    ]
    delete = controller[
        controller.index("async function removeCurrentOuting") : controller.index(
            "function selectOutingParticipant"
        )
    ]
    assert leave.index("stopTrackerBeforeOutingMutation();") < leave.index(
        "await leaveOuting("
    )
    assert delete.index("stopTrackerBeforeOutingMutation();") < delete.index(
        "await deleteOuting("
    )
    assert delete.index("await deleteOuting(") < delete.index("handleOutingClosed();")
    assert "clearOutingPosition" not in leave
    assert "clearOutingPosition" not in delete


def test_pr25_duplicate_live_events_have_no_membership_side_effects() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    update = controller[
        controller.index("function applyOutingLiveUpdate") : controller.index(
            "function applyOutingLiveClear"
        )
    ]
    clear = controller[
        controller.index("function applyOutingLiveClear") : controller.index(
            "async function recoverOutingLiveSnapshot"
        )
    ]
    for handler in (update, clear):
        assert handler.index('if (result.status === "ignored") return;') < (
            handler.index("refreshOutingSnapshotForMembershipChange")
        )


def test_pr25_map_uses_exact_public_coordinates_and_stable_route_colors() -> None:
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    live_render = map_source[
        map_source.index(
            "export function renderOutingLivePositions"
        ) : map_source.index("export function clearOutingLivePositions")
    ]
    assert "coordinates: [position.coordinate.lon, position.coordinate.lat]" in (
        live_render
    )
    assert "outingParticipantColor(joinOrder)" in live_render
    assert "accuracyPolygon(" in live_render
    assert 'freshness === "fresh" ? 1 : 0.46' in live_render
    assert "fitOutingRoutes" not in live_render
    for forbidden in (
        "snap",
        "project",
        "route progress",
        "nearest route",
        "ETA",
    ):
        assert forbidden.lower() not in live_render.lower()
    assert "positionOutingLiveLayers();" in map_source
    assert "...OUTING_LIVE_LAYERS.filter" in map_source
    for diagnostic in (
        "positionSourceExists",
        "accuracySourceExists",
        "expectedLayerCount",
        "renderedCurrentPositionCount",
        "renderedAccuracyPolygonCount",
        "freshCount",
        "staleCount",
        "selectedParticipantId",
        "duplicateLayerCount",
    ):
        assert diagnostic in map_source


def test_pr25_live_view_handles_zero_participants_viewers_and_freshness() -> None:
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    html = (STATIC_DIRECTORY / "index.html").read_text()
    assert "state.outingSnapshot.participants.forEach" in view
    assert "visibleLivePositions" in view
    assert 'status: "Not sharing"' in view
    assert 'status: freshness === "fresh" ? "Live" : "Stale"' in view
    assert "Accuracy ±${Math.round(position.accuracy_m)} m" in view
    assert "state.outingTrackingActive" in view
    assert "state.outingTrackingTransitionPending" in view
    assert "participantReceiptBelongsToOuting" in view
    assert "Viewer mode" in view
    for element_id in (
        "outing-live-panel",
        "outing-live-connection",
        "outing-live-summary",
        "outing-live-own-controls",
        "start-outing-live-sharing",
        "stop-outing-live-sharing",
        "outing-live-tracking-status",
        "open-outing-live-here",
        "outing-owner-actions",
        "delete-outing-owner-view",
    ):
        assert f'id="{element_id}"' in html
    assert 'aria-live="polite"' in html
    assert "foreground browser location" in html
    assert "No historical activity track is retained" in html


def test_pr25_gap_recovery_is_single_flight_and_recreates_public_stream() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    lifecycle = (STATIC_DIRECTORY / "outing_live_lifecycle.js").read_text()
    recovery = controller[
        controller.index("async function recoverOutingLiveSnapshot") : controller.index(
            "async function refreshOutingSnapshotForMembershipChange"
        )
    ]
    assert "outingLiveRecovery.run(session)" in recovery
    assert "closeOutingLiveConnection()" in recovery
    assert '"reconnecting"' in recovery
    assert "replaceWithSnapshot" in recovery
    assert "connectCurrentOutingLiveEvents(session)" in recovery
    recovery_error = recovery[
        recovery.index("function handleOutingLiveRecoveryError") :
    ]
    assert 'error?.code === "outing_not_found"' in recovery_error
    assert "handleOutingClosed(session)" in recovery_error
    assert "if (!currentOutingLiveSession(session)) return;" in recovery_error
    assert recovery_error.count("connectCurrentOutingLiveEvents(session)") == 1
    assert "createGuardedSingleFlight" in lifecycle
    assert "activeOperation === operation" in lifecycle
    assert "isCurrent(operation.session)" in lifecycle
    assert "createDirtyRerun" in lifecycle
    assert "activeOperation.dirty = true" in lifecycle
    assert "do {" in lifecycle
    assert "Last-Event-ID" not in controller
    assert "URLSearchParams" not in controller


def test_pr25_live_card_updates_preserve_focusable_nodes() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    live_render = view[
        view.index("export function renderOutingLiveView") : view.index(
            "function renderParticipantCardsStructure"
        )
    ]
    incremental = view[
        view.index("function updateParticipantCards") : view.index(
            "function participantLiveDescription"
        )
    ]
    select = controller[
        controller.index("function selectOutingParticipant") : controller.index(
            "async function joinCurrentOuting"
        )
    ]
    assert "replaceChildren" not in live_render
    assert "updateParticipantCards(state)" in live_render
    assert "card.dataset.participantId" in view
    assert "classList.toggle" in incremental
    assert 'setAttribute("aria-pressed"' in incremental
    assert "textContent" in incremental
    assert "showOutingView" not in select


def test_pr25_owner_delete_is_memory_capability_gated_in_outing_view() -> None:
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    show_view = view[
        view.index("export function showOutingView") : view.index(
            "export function renderOutingLiveView"
        )
    ]
    owner_controls = show_view[
        show_view.index("const owner = state.outingOwnerReceipt") : show_view.index(
            'byId("join-outing").disabled'
        )
    ]
    assert "owner.slug !== outing.slug" in owner_controls
    assert "state.outingClosed" in owner_controls
    assert 'byId("delete-outing-owner-view").onclick = handlers.deleteOwner' in view
    assert "deleteOwner: removeCurrentOuting" in controller
    assert "dataset.owner" not in view
    assert "owner_token" not in view


def test_pr25_membership_refresh_discards_only_stale_participant_receipt() -> None:
    controller = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    lifecycle = (STATIC_DIRECTORY / "outing_live_lifecycle.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    refresh = controller[
        controller.index("function applyRefreshedOutingMembership") : controller.index(
            "function handleOutingMembershipRefreshError"
        )
    ]
    assert "installAuthoritativeOutingSnapshot(" in refresh
    assert "outingTracker?.shutdown()" in refresh
    assert "syncTrackerState: syncOutingTrackingState" in refresh
    assert "state.outingOwnerReceipt" not in refresh
    assert "forgetParticipantIdentity(" in refresh
    assert "runBestEffortStorage(" in refresh
    discard = lifecycle[
        lifecycle.index(
            "export function discardStaleParticipantReceipt"
        ) : lifecycle.index("export function createGuardedSingleFlight")
    ]
    assert discard.index("shutdownTracker();") < discard.index("syncTrackerState();")
    assert discard.index("syncTrackerState();") < discard.index(
        "state.outingParticipantReceipt = null;"
    )
    assert "state.outingOwnerReceipt" not in discard
    assert view.count("participantReceiptBelongsToOuting") >= 3


def test_pr25_framework_free_runtime_harness_covers_review_races() -> None:
    harness = (ROOT / "tests/browser/pr25_live_runtime_harness.js").read_text()
    html = (ROOT / "tests/browser/pr25_live_runtime_harness.html").read_text()
    for scenario in (
        "scenarioLatePutAfterStop",
        "scenarioOldPutFinallyAfterNewStart",
        "scenarioTransportFailureStopUncertain",
        "scenarioQueuedFixAfterStop",
        "scenarioConflictRecoveryAfterStop",
        "scenarioClearAfterShutdown",
        "scenarioNewStartResetsCadenceAndRetry",
        "scenarioStrictMalformedValues",
        "scenarioClosedDuringRecovery",
        "scenarioTransientRecoveryReconnect",
        "scenarioMembershipDirtyRerun",
        "scenarioJoinInvalidatesStaleMembershipRefresh",
        "scenarioStaleParticipantReceipt",
        "scenarioOldSessionHandler",
    ):
        assert f"{scenario}(" in harness
    assert "runPr25LiveRuntimeHarness" in harness
    assert 'type="module"' in html
    assert "clearCallCount += 1" in harness
    assert "equal(rig.clearCalls(), 1" in harness
    assert "await microtasks();" in harness
    assert 'addEventListener("unhandledrejection"' in html
    assert "window.setTimeout(resolve, 0)" in html
    assert 'result.dataset.status = "failed"' in html
    assert html.index('addEventListener("unhandledrejection"') < html.index(
        '<script type="module">'
    )


def test_pr25_frontend_boundaries_and_module_sizes_are_explicit() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    view = (STATIC_DIRECTORY / "outing_view.js").read_text()
    for forbidden in (
        "/live",
        "/events",
        "/position",
        "EventSource",
        "watchPosition",
        "startOutingLiveExperience",
        "recoverOutingLiveSnapshot",
    ):
        assert forbidden not in app
    for forbidden in ("fetch(", "EventSource", "token", "geolocation"):
        assert forbidden not in map_source
    for forbidden in ("/live", "/events", "/position", "watchPosition"):
        assert forbidden not in view
    focused_modules = (
        "outing_live.js",
        "outing_live_lifecycle.js",
        "outing_live_state.js",
        "outing_view.js",
    )
    assert {
        name: len((STATIC_DIRECTORY / name).read_text().splitlines())
        for name in focused_modules
        if len((STATIC_DIRECTORY / name).read_text().splitlines()) >= 800
    } == {}
