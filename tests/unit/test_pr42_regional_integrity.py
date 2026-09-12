"""Pinned, locally packaged incremental SHA-256 and its shared map-store use."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/sugarglider/web/static"
VENDOR = STATIC / "vendor/noble-hashes-2.4.0"


def test_vendored_sha2_dependency_closure_and_license_are_pinned() -> None:
    readme = (VENDOR / "README.md").read_text()
    expected = dict(re.findall(r"- `([^`]+)`: `([a-f0-9]{64})`", readme))
    assert set(expected) == {"sha2.js", "_md.js", "_u64.js", "utils.js", "LICENSE"}
    shell = (ROOT / "android/shell-assets.txt").read_text().splitlines()
    worker = (STATIC / "service-worker.js").read_text()
    for name, digest in expected.items():
        path = VENDOR / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert f"vendor/noble-hashes-2.4.0/{name}" in shell
        if name.endswith(".js"):
            source = path.read_text()
            assert f'"/static/vendor/noble-hashes-2.4.0/{name}"' in worker
            for dependency in re.findall(r'from "([^"]+)"', source):
                assert dependency.startswith("./")
                assert dependency.removeprefix("./") in expected
    assert "The MIT License (MIT)" in (VENDOR / "LICENSE").read_text()
    assert "e1946149b780017b2564fcc092cb01c04e1d7f20627d0296c17da8868f4436dc" in readme


def test_map_completion_follows_regional_archive_verification() -> None:
    store = (STATIC / "map_pack_store.js").read_text()
    finish = store.split("async finishInstall(", 1)[1]
    assert finish.index("await verifyRegionalFile(") < finish.index(
        'directory.getFileHandle("manifest.json"'
    )
    assert "regionalFileIntegrity(expectedArchive)" in store
    assert "integrity.byte_size !== manifest.byte_size" in store
    assert (
        '"/static/regional_integrity.js"' in (STATIC / "service-worker.js").read_text()
    )
