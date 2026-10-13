"""PR86 safety contracts for persistent native Valhalla Mobile actors."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KOTLIN = ROOT / "android/app/src/main/java/io/github/victorgabillon/sugarglider"
TEST_KOTLIN = ROOT / "android/app/src/test/java/io/github/victorgabillon/sugarglider"


def test_old_valhalla_engine_cannot_leak_across_activity_recreation() -> None:
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    engine = (KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    registry = (KOTLIN / "RoutingPackRegistry.kt").read_text()
    activity = (KOTLIN / "MainActivity.kt").read_text()

    assert "interface NativeRouteEngine : AutoCloseable" in boundary
    assert "override fun close()" in boundary
    assert "override fun close()" in engine
    assert "actorHolder.release()" in engine
    assert "disposeActor = { actor -> actor.valhalla.close() }" in engine
    assert "disposeActor(previous.actor)" in registry

    # The same serial executor runs native route calls and queued disposal.
    # Shutdown may not interrupt JNI work or synchronously block the UI thread.
    assert "localRouteExecutor.execute { nativeRouteEngine.close() }" in activity
    assert "localRouteExecutor.shutdown()" in activity
    assert "localRouteExecutor.shutdownNow()" not in activity


def test_valhalla_graph_has_no_remote_fallback_in_new_models() -> None:
    engine = (KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    tests = (TEST_KOTLIN / "ValhallaLocalConfigurationTest.kt").read_text()
    assert 'tileUrl = ""' in engine
    assert "tileUrlGz = false" in engine
    assert 'AdditionalData(elevation = "")' in engine
    assert ".withTileExtract(tileArchive.absolutePath)" in engine
    assert 'optString("tile_url", "")' in tests
    assert 'optBoolean("tile_url_gz", false)' in tests
