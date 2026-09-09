"""Keep the lightweight PR37 acceptance fixtures tied to the regional templates."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/browser/pr37_paris_multipack_harness.js"


@pytest.mark.parametrize("region", ["marly", "paris"])
def test_multipack_fixture_matches_template_and_documented_build(region: str) -> None:
    source = HARNESS.read_text(encoding="utf-8")
    identity_block = re.search(r"const PACK_IDENTITIES = (\{.*?\n\});", source, re.S)
    assert identity_block is not None
    identity = json.loads(identity_block.group(1))[region]
    template = json.loads(
        (ROOT / f"map-packs/{region}-map-dev-v1.template.json").read_text(
            encoding="utf-8"
        )
    )
    assert identity["pack_id"] == template["pack_id"]
    assert identity["bounds"] == template["bounds"]
    assert identity["byte_size"] > template["byte_size"]
    documentation = (ROOT / "docs/pr37-paris-multipack.md").read_text(encoding="utf-8")
    assert identity["build_id"] in documentation
    assert f"{identity['byte_size']:,}" in documentation


def test_multipack_harness_loads_only_local_shared_map_dependencies() -> None:
    html = HARNESS.with_suffix(".html").read_text(encoding="utf-8")
    source = HARNESS.read_text(encoding="utf-8")
    imports = re.findall(r'from "([^"]+)"', source)
    assert {Path(path).name for path in imports} == {
        "offline_map.js",
        "map_pack_manifest.js",
        "map.js",
    }
    references = imports + re.findall(r'(?:src=|from )"([^"]+)"', html)
    for reference in references:
        assert reference.startswith(".")
        assert (HARNESS.parent / reference).is_file()
    assert 'addEventListener("unhandledrejection"' in html
    assert 'addEventListener("error"' in html
    assert "data/map-packs/" not in source
    assert "fetch(" not in source
    assert "setTimeout(" not in source
