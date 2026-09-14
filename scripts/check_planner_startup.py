"""Full bundled-page regression with real CDP pointer input.

Fixtures only replace native/storage boundaries. Use --app-root with the frozen
checkout to prove it fails without editing it. HTTPS, Chrome profile and OPFS
region fixtures are isolated from production.
"""

from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import math
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://appassets.androidplatform.net"


class CDP:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.counter = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.counter += 1
        identity = self.counter
        self.ws.send(
            json.dumps({"id": identity, "method": method, "params": params or {}})
        )
        while True:
            event = json.loads(self.ws.recv(timeout=60))
            if event.get("id") == identity:
                if "error" in event:
                    raise RuntimeError(event["error"])
                return event.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def snapshot(self) -> Any:
        return self.evaluate(
            "(async()=>{const fixture=await import("
            '"/tests/browser/planner_startup_fixture.js");'
            "return fixture.startupSnapshot();})()"
        )

    def tap(self, x: float, y: float) -> None:
        for event in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call(
                "Input.dispatchMouseEvent",
                {"type": event, "x": x, "y": y, "button": "left", "clickCount": 1},
            )


def wait_ready(cdp: CDP) -> Any:
    for _ in range(200):
        time.sleep(0.1)
        snapshot = cdp.snapshot()
        if (
            snapshot.get("canvas")
            and "ready" in snapshot.get("region", "").lower()
            and not snapshot.get("regionRefreshDisabled")
        ):
            return snapshot
    raise AssertionError(f"Region not ready: {snapshot}")


def click_control(cdp: CDP, selector: str) -> None:
    closed = cdp.evaluate(f"""(() => {{
        const e = document.querySelector({json.dumps(selector)});
        return e.closest('details:not([open])')?.id;
    }})()""")
    if closed and not selector.endswith(" > summary"):
        click_control(cdp, f"#{closed} > summary")
    rect = cdp.evaluate(f"""(() => {{
        const element = document.querySelector({json.dumps(selector)});
        element.scrollIntoView({{block: 'center'}});
        const r=element.getBoundingClientRect();
        return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()""")
    cdp.tap(rect["x"], rect["y"])


def profile_ui_guards(cdp: CDP) -> list[Any]:
    evidence = []
    for profile, index in (("hike", 1), ("gravel_bike", 3)):
        # Native keyboard events select an actual option; no application state writes.
        click_control(cdp, "#profile")
        for key in ["Home", *(["ArrowDown"] * index), "Enter"]:
            for event in ("keyDown", "keyUp"):
                cdp.call("Input.dispatchKeyEvent", {"type": event, "key": key})
        time.sleep(0.3)
        chosen = cdp.snapshot()
        assert chosen["profile"] == profile, chosen
        assert "installed region" in chosen["help"], chosen
        for mode in ("waypoint_route", "auto_tour"):
            click_control(cdp, f'input[name="planning-mode"][value="{mode}"]')
            assert cdp.snapshot()["profile"] == profile
        if profile == "hike":
            # Temporary foot unavailability at the native boundary only.
            cdp.evaluate('globalThis.nativeFixtureAccessModes = ["bicycle"]')
            click_control(cdp, "#regional-refresh")
            unavailable = wait_ready(cdp)
            assert (
                unavailable["profile"] == "hike" and not unavailable["profileAvailable"]
            ), unavailable
            assert unavailable["disabled"] == [True, True]
            cdp.evaluate('globalThis.nativeFixtureAccessModes = ["foot", "bicycle"]')
        click_control(cdp, "#regional-refresh")
        ready = wait_ready(cdp)
        assert ready["profile"] == profile and ready["profileAvailable"], ready
        assert ready["disabled"] == [False, False], ready
        assert ready["status"] == "Ready to generate.", ready
        assert "Install a compatible" not in ready["help"], ready
        cdp.call("Page.reload", {"ignoreCache": True})
        time.sleep(0.5)
        restarted = wait_ready(cdp)
        assert restarted["profile"] == profile, restarted
        assert restarted["start"] is None and restarted["disabled"] == [True, True]
        cdp.evaluate(
            'document.querySelector(".maplibregl-canvas").scrollIntoView({block:"center"})'
        )
        rect = cdp.snapshot()["canvas"]
        cdp.tap(
            round(rect["x"] + rect["width"] / 2), round(rect["y"] + rect["height"] / 2)
        )
        time.sleep(0.3)
        after = cdp.snapshot()
        assert after["profile"] == profile and after["disabled"] == [False, False], (
            after
        )
        evidence.append(
            {
                "profile": profile,
                "chosen": chosen,
                "ready": ready,
                "restarted": restarted,
                "after_tap": after,
            }
        )
    assert "GraphHopper" not in cdp.evaluate(
        'document.querySelector("footer").textContent'
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    static = args.app_root.resolve() / "src/sugarglider/web/static"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *values: Any) -> None:
            pass

        def translate_path(self, path: str) -> str:
            path = path.split("?", 1)[0]
            if path == "/":
                return str(static / "index.html")
            if path == "/v1/ui/config":
                return str(static / "android_ui_config.json")
            for prefix in ("/static/", "/src/sugarglider/web/static/"):
                if path.startswith(prefix):
                    return str(static / path.removeprefix(prefix))
            return super().translate_path(path)

    with tempfile.TemporaryDirectory(prefix="sugarglider-startup-") as directory:
        temp = Path(directory)
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(temp / "key.pem"),
                "-out",
                str(temp / "cert.pem"),
                "-days",
                "1",
                "-subj",
                "/CN=appassets.androidplatform.net",
            ],
            check=True,
            capture_output=True,
        )
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT))
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(temp / "cert.pem", temp / "key.pem")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with (args.output / "chrome.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "google-chrome",
                    "--headless=new",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--no-proxy-server",
                    "--ignore-certificate-errors",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                    "--window-size=1440,1200",
                    "--host-resolver-rules=MAP appassets.androidplatform.net "
                    f"127.0.0.1:{server.server_port}",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={temp}/profile",
                    "about:blank",
                ],
                stdout=log,
                stderr=log,
            )
            try:
                port_file = temp / "profile/DevToolsActivePort"
                for _ in range(200):
                    if port_file.exists():
                        break
                    time.sleep(0.1)
                port = port_file.read_text().splitlines()[0]
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list"
                ) as response:
                    targets = json.load(response)
                with connect(
                    next(
                        t["webSocketDebuggerUrl"]
                        for t in targets
                        if t["type"] == "page"
                    ),
                    max_size=32 * 1024 * 1024,
                ) as ws:
                    cdp = CDP(ws)
                    cdp.call("Page.enable")
                    cdp.call(
                        "Page.navigate",
                        {"url": ORIGIN + "/tests/browser/planner_startup_fixture.html"},
                    )
                    time.sleep(1)
                    manifest = cdp.evaluate(
                        "(async()=>{const fixture=await import("
                        '"/tests/browser/planner_startup_fixture.js");'
                        "return fixture.installStartupRegion();})()"
                    )
                    native_source = cdp.evaluate(
                        "(async()=>{const fixture=await import("
                        '"/tests/browser/planner_startup_fixture.js");'
                        "return fixture.installNativeFixture.toString();})()"
                    )
                    cdp.call(
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": f"({native_source})();"},
                    )
                    evidence: dict[str, Any] = {
                        "test": "fresh_bundled_auto_tour_loop_map_tap_enables_generate",
                        "app_root": str(args.app_root),
                        "manifest": manifest,
                        "launches": [],
                    }
                    failures: list[str] = []
                    for launch in range(2):
                        cdp.call(
                            "Page.navigate" if launch == 0 else "Page.reload",
                            {"url": ORIGIN + "/"}
                            if launch == 0
                            else {"ignoreCache": True},
                        )
                        snapshot: Any = None
                        for _ in range(200):
                            time.sleep(0.1)
                            try:
                                snapshot = cdp.snapshot()
                            except RuntimeError:
                                continue
                            if (
                                snapshot.get("canvas")
                                and snapshot.get("regionValue")
                                and "ready" in snapshot.get("region", "").lower()
                            ):
                                break
                        before = snapshot
                        if not before or not before.get("canvas"):
                            raise AssertionError(f"Startup not ready: {before}")
                        cdp.evaluate(
                            'document.querySelector(".maplibregl-canvas").scrollIntoView({block:"center"})'
                        )
                        time.sleep(0.3)
                        before = cdp.snapshot()
                        rect = before["canvas"]
                        x, y = (
                            round(rect["x"] + rect["width"] / 2),
                            round(rect["y"] + rect["height"] / 2),
                        )
                        cdp.tap(x, y)
                        time.sleep(0.5)
                        after = cdp.snapshot()
                        evidence["launches"].append(
                            {"before": before, "tap": {"x": x, "y": y}, "after": after}
                        )
                        (args.output / f"startup-{launch}.png").write_bytes(
                            base64.b64decode(cdp.call("Page.captureScreenshot")["data"])
                        )
                        checks = {
                            "default Auto Tour/Loop": before["mode"] == "auto_tour"
                            and before["topology"] == "loop",
                            "empty endpoints and points": before["start"] is None
                            and before["end"] is None
                            and before["points"] == [],
                            "all six profiles ready": len(before["profiles"] or []) == 6
                            and all(row["available"] for row in before["profiles"]),
                            "explicit Trail run default": before["profile"]
                            == "trail_run"
                            and before["profileLabel"] == "Trail run",
                            "only missing start": before["disabled"] == [True, True]
                            and before["status"]
                            == "Click the map to choose your start point.",
                            "one map start": after["start"] is not None
                            and len(after["points"]) == 1
                            and after["points"][0] == after["start"]
                            and after["end"] is None,
                            "defaults remain": after["mode"] == "auto_tour"
                            and after["topology"] == "loop"
                            and after["profile"] == "trail_run",
                            "available and enabled": after["profileAvailable"]
                            and after["disabled"] == [False, False]
                            and after["validation"] == "",
                            "marker at tap": bool(after["marker"])
                            and abs(after["marker"]["x"] - x) < 2
                            and abs(after["marker"]["y"] - y) < 2,
                            "fields match start": bool(after["start"])
                            and abs(
                                float(after["startFields"][0]) - after["start"]["lat"]
                            )
                            < 1e-6
                            and abs(
                                float(after["startFields"][1]) - after["start"]["lon"]
                            )
                            < 1e-6,
                        }
                        if after["start"]:
                            bounds = before["bounds"]
                            fraction_x = (x - rect["x"]) / rect["width"]
                            fraction_y = (y - rect["y"]) / rect["height"]
                            north_y = math.asinh(
                                math.tan(math.radians(bounds["north"]))
                            )
                            south_y = math.asinh(
                                math.tan(math.radians(bounds["south"]))
                            )
                            expected_lat = math.degrees(
                                math.atan(
                                    math.sinh(
                                        north_y + fraction_y * (south_y - north_y)
                                    )
                                )
                            )
                            expected_lon = bounds["west"] + fraction_x * (
                                bounds["east"] - bounds["west"]
                            )
                            checks["known map coordinate"] = (
                                abs(after["start"]["lon"] - expected_lon) < 1e-6
                                and abs(after["start"]["lat"] - expected_lat) < 1e-6
                            )
                            west, south, east, north = manifest["bounds"]
                            checks["tap inside installed fixture"] = (
                                west < expected_lon < east
                                and south < expected_lat < north
                            )
                        failures.extend(
                            f"launch {launch}: {name}"
                            for name, passed in checks.items()
                            if not passed
                        )
                    evidence["failures"] = failures
                    evidence["native_requests"] = cdp.evaluate("nativeFixtureRequests")
                    (args.output / "startup.json").write_text(
                        json.dumps(evidence, indent=2) + "\n"
                    )
                    if failures:
                        raise AssertionError("; ".join(failures))
                    print(
                        evidence["test"]
                        + ": PASS (fresh startup + retained-region reload)",
                        flush=True,
                    )
                    guards = profile_ui_guards(cdp)
                    (args.output / "profile-ui-guards.json").write_text(
                        json.dumps(guards, indent=2) + "\n"
                    )
                    print(
                        "Explicit Hike/Gravel selection, mode changes, "
                        "readiness/unavailability, restart and copy: PASS"
                    )
            finally:
                process.terminate()
                process.wait(timeout=15)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
