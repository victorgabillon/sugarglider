#!/usr/bin/env python3
"""Explicit Debug-only ADB integration; supplied local DEM/plan, no downloads."""

import argparse
import gzip
import os
import re
import struct
import subprocess
import uuid
import zipfile
from pathlib import Path

from sugarglider.offline_regions.elevation_hgt_probe import probe_hgt_file
from sugarglider.offline_regions.native_height_experiment import HeightPlan

DEBUG_PACKAGE = "io.github.victorgabillon.sugarglider.debug"
TEST_PACKAGE = DEBUG_PACKAGE + ".test"
PRODUCTION_PACKAGE = "io.github.victorgabillon.sugarglider"
RUNNER = "io.github.victorgabillon.sugarglider.HeightResearchInstrumentation"
ROOT = Path(__file__).resolve().parents[1]


def command(*arguments: str, timeout: int = 120) -> str:
    completed = subprocess.run(
        arguments, check=True, capture_output=True, text=True, timeout=timeout
    )
    return completed.stdout


def certificate(sdk: Path, apk: Path) -> str:
    value = command(
        str(sdk / "build-tools/36.0.0/apksigner"), "verify", "--print-certs", str(apk)
    )
    match = re.search(r"certificate SHA-256 digest: ([0-9a-f]{64})", value)
    if match is None:
        raise ValueError("APK certificate unavailable")
    return match[1]


def package_metadata(sdk: Path, apk: Path) -> tuple[str, int]:
    value = command(str(sdk / "build-tools/36.0.0/aapt"), "dump", "badging", str(apk))
    match = re.search(r"package: name='([^']+)' versionCode='(\d*)'", value)
    if match is None:
        raise ValueError("APK identity unavailable")
    # Instrumentation APKs have no version code; application APKs must have one.
    return match[1], int(match[2] or "0")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk", type=Path, default=Path(os.environ.get("ANDROID_HOME", "/missing-sdk"))
    )
    parser.add_argument(
        "--apk",
        type=Path,
        default=ROOT / "android/app/build/outputs/apk/debug/app-debug.apk",
    )
    parser.add_argument(
        "--test-apk",
        type=Path,
        default=ROOT
        / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial")
    args = parser.parse_args()
    output: Path = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("output must be a new research directory outside the checkout")
    output.mkdir(parents=True)
    plan_bytes = args.plan.read_bytes()
    if len(plan_bytes) > 1_048_576 or args.tile.name != "N48E002.hgt.gz":
        raise ValueError("invalid research input")
    plan = HeightPlan.model_validate_json(plan_bytes)
    probe_hgt_file(args.tile, plan.source_sha256)
    devices = [
        line.split()[0]
        for line in command("adb", "devices").splitlines()
        if "\tdevice" in line
    ]
    serial: str = args.serial or (devices[0] if len(devices) == 1 else "")
    if serial not in devices:
        raise ValueError("select exactly one authorized connected device")

    def adb(*arguments: str, timeout: int = 120) -> str:
        return command("adb", "-s", serial, *arguments, timeout=timeout)

    installed_paths = adb("shell", "pm", "path", DEBUG_PACKAGE).splitlines()
    if len(installed_paths) != 1 or not installed_paths[0].startswith(
        "package:/data/app/"
    ):
        raise ValueError("expected one installed Debug APK")
    installed = output / "installed-debug-before.apk"
    adb("pull", installed_paths[0].removeprefix("package:"), str(installed))
    old_id, old_code = package_metadata(args.sdk, installed)
    new_id, new_code = package_metadata(args.sdk, args.apk)
    test_id, _ = package_metadata(args.sdk, args.test_apk)
    if (
        old_id != DEBUG_PACKAGE
        or new_id != DEBUG_PACKAGE
        or test_id != TEST_PACKAGE
        or old_code <= 0
        or new_code < old_code
    ):
        raise ValueError("unsafe APK identity or version")
    expected_certificate = certificate(args.sdk, installed)
    if any(
        certificate(args.sdk, apk) != expected_certificate
        for apk in (args.apk, args.test_apk)
    ):
        raise ValueError("APK signing certificate mismatch")
    with zipfile.ZipFile(installed) as old, zipfile.ZipFile(args.apk) as new:
        if old.read("AndroidManifest.xml") != new.read("AndroidManifest.xml"):
            raise ValueError("Debug application manifest changed")
    test_manifest = command(
        str(args.sdk / "build-tools/36.0.0/aapt"),
        "dump",
        "xmltree",
        str(args.test_apk),
        "AndroidManifest.xml",
    )
    if f'"{DEBUG_PACKAGE}"' not in test_manifest or f'"{RUNNER}"' not in test_manifest:
        raise ValueError("instrumentation target or runner mismatch")
    production_paths = [
        line.removeprefix("package:")
        for line in adb("shell", "pm", "path", PRODUCTION_PACKAGE).splitlines()
    ]
    production_before = adb("shell", "sha256sum", *production_paths)
    (output / "production-apk-hashes-before.txt").write_text(production_before)
    (output / "production-package-before.txt").write_text(
        adb("shell", "dumpsys", "package", PRODUCTION_PACKAGE)
    )
    packs = adb(
        "shell",
        "run-as",
        DEBUG_PACKAGE,
        "find",
        "files/regional-routing-packs",
        "-name",
        "valhalla_tiles.tar",
    ).splitlines()
    packs_before = adb("shell", "run-as", DEBUG_PACKAGE, "sha256sum", *packs)
    (output / "routing-hashes-before.txt").write_text(packs_before)
    print(
        "Verified Debug/test IDs, matching installed certificates, "
        "version and byte-identical app manifest.",
        flush=True,
    )
    adb("install", "-r", str(args.apk))
    adb("install", "-r", str(args.test_apk))
    research_id = "native-height-research-" + uuid.uuid4().hex[:16]
    staging = "/data/local/tmp/" + research_id
    cache = "cache/" + research_id
    adb("shell", "mkdir", staging)
    adb("shell", "run-as", DEBUG_PACKAGE, "mkdir", cache)
    adb(
        "shell",
        "run-as",
        DEBUG_PACKAGE,
        "mkdir",
        "-p",
        cache + "/real/N48",
        cache + "/void/N48",
        cache + "/empty",
    )
    void_file = output / "synthetic-void-N48E002.hgt.gz"
    with void_file.open("wb") as stream:
        with gzip.GzipFile(
            fileobj=stream, mode="wb", filename="", mtime=0
        ) as compressed:
            row = struct.pack(">h", -32_768) * 3_601
            for _ in range(3_601):
                compressed.write(row)
    for source, staged_name, destination in (
        (args.plan, "plan.json", cache + "/plan.json"),
        (args.tile, "real.hgt.gz", cache + "/real/N48/N48E002.hgt.gz"),
        (void_file, "void.hgt.gz", cache + "/void/N48/N48E002.hgt.gz"),
    ):
        adb("push", str(source), staging + "/" + staged_name)
        adb(
            "shell",
            "run-as",
            DEBUG_PACKAGE,
            "cp",
            staging + "/" + staged_name,
            destination,
        )
    result = adb(
        "shell",
        "am",
        "instrument",
        "-w",
        "-r",
        "-e",
        "research_id",
        research_id,
        TEST_PACKAGE + "/" + RUNNER,
    )
    (output / "instrumentation.txt").write_text(result)
    if (
        "Native height research passed:" not in result
        or "INSTRUMENTATION_CODE: -1" not in result
    ):
        raise RuntimeError(
            "physical height suite failed; inspect retained instrumentation output"
        )
    for name in ("native-result.json", "diagnostics.json"):
        (output / name).write_text(
            adb("shell", "run-as", DEBUG_PACKAGE, "cat", cache + "/" + name)
        )
    production_after = adb("shell", "sha256sum", *production_paths)
    packs_after = adb("shell", "run-as", DEBUG_PACKAGE, "sha256sum", *packs)
    (output / "production-apk-hashes-after.txt").write_text(production_after)
    (output / "routing-hashes-after.txt").write_text(packs_after)
    if production_after != production_before or packs_after != packs_before:
        raise RuntimeError("production/routing preservation check failed")
    # Only the fresh directories created above; no existing app data is cleared.
    adb("shell", "run-as", DEBUG_PACKAGE, "rm", "-r", cache)
    adb("shell", "rm", "-r", staging)
    print(result.strip())
    print(
        "Production APKs and routing archives unchanged; owned disposable data removed."
    )


if __name__ == "__main__":
    main()
