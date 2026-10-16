"""The elevation UI stays a local consumer of the native analysis sidecar."""

from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]


def test_elevation_presentation_cannot_start_another_analysis_pipeline() -> None:
    for name in (
        "elevation_profile.js",
        "elevation_view.js",
        "elevation_map_marker.js",
    ):
        source = (STATIC_DIRECTORY / name).read_text()
        for forbidden in (
            "fetch(",
            "nativeBridgeTransport",
            "sampleElevationGeometry",
            "createLocalPlanner",
            "local_routing.js",
            "elevation_sampling.js",
        ):
            assert forbidden not in source, (name, forbidden)
    projection = (STATIC_DIRECTORY / "elevation_profile.js").read_text()
    assert ".filtered_height_m" in projection
    assert "analysis.segments" in projection
    for total in ("total_ascent_m", "total_descent_m", "observed_ascent_m"):
        assert total not in projection
    app = (STATIC_DIRECTORY / "app.js").read_text()
    assert "selectedRouteElevation?.owns(" in app
    assert "selectedRouteElevation?.retry()" in app


def test_elevation_section_has_accessible_summary_and_existing_cancel() -> None:
    index = (STATIC_DIRECTORY / "index.html").read_text()
    section = index[index.index('<section id="route-elevation"') :]
    section = section[: section.index("</section>")]
    for identifier in (
        "route-elevation-title",
        "route-elevation-status",
        "cancel-route-elevation",
        "retry-route-elevation",
        "show-elevation-on-map",
        "elevation-position-readout",
    ):
        assert f'id="{identifier}"' in section
    assert 'aria-live="off"' in section
    assert "data-elevation-ascent" in section
    assert "data-elevation-descent" in section
    assert "data-elevation-altitude" in section
    assert (ROOT / "tests/browser/pr92_elevation_ui_harness.js").exists()
