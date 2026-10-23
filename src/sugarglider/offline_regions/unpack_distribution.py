"""Verify a confined site archive and its separate exact-build authorization."""

import argparse
import hashlib
import json
import math
import re
import shutil
import stat
import zipfile
from pathlib import Path
from typing import NoReturn, cast
from urllib.parse import urlsplit

from sugarglider.offline_regions.elevation_component import ElevationManifest

# Keep the legacy --private verifier independently copyable. Public v3 verification
# below imports the installed, pinned application and its code-owned notice registry.
NOTICE_FILE = "SOURCE_NOTICES.txt"
NOTICE_LIMIT = 131_072

MAX_BYTES = 950_000_000  # Below the published 1 GB GitHub Pages site limit.
MAX_FILES = 128  # Bound archive metadata; not a special-case retained-version limit.
REGIONAL_FILES = {
    "manifest.json",
    "map/manifest.json",
    "map/basemap.pmtiles",
    "routing/manifest.json",
    "routing/valhalla_tiles.tar",
    "pois/index.json.gz",
    "nature/index.json.gz",
    "elevation/manifest.json",
}
ROOT_FILES = {".nojekyll", "README.txt", "index.html", "catalog.json"}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate publication JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid publication JSON constant: {value}")


def _read_object(bundle: zipfile.ZipFile, name: str) -> dict[str, object]:
    if bundle.getinfo(name).file_size > 65_536:
        raise ValueError("publication JSON exceeds its size budget")
    value = json.loads(
        bundle.read(name),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("publication JSON must be an object")
    return cast(dict[str, object], value)


def _text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value.strip() == value
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
    )


def _verify_identities(
    bundle: zipfile.ZipFile, regions: dict[str, set[str]], publication: bool = False
) -> None:
    """Check the one advertised row and every version's immutable path identity."""
    catalog = _read_object(bundle, "catalog.json")
    offerings = catalog.get("regions")
    if (
        set(catalog) != {"schema_version", "regions"}
        or type(catalog.get("schema_version")) is not int
        or catalog["schema_version"] != 1
        or not isinstance(offerings, list)
        or len(offerings) != 1
        or not isinstance(offerings[0], dict)
    ):
        raise ValueError("invalid publication catalog")
    offering = cast(dict[str, object], offerings[0])
    if set(offering) != {
        "region_id",
        "build_id",
        "display_name",
        "description",
        "bounds",
        "download_bytes",
        "manifest_url",
    }:
        raise ValueError("invalid publication catalog fields")
    current = f"regions/{offering['region_id']}/{offering['build_id']}"
    if current not in regions:
        raise ValueError("catalog build identity is missing from publication")
    url = offering["manifest_url"]
    if not isinstance(url, str) or not _text(url, 1_500):
        raise ValueError("invalid catalog manifest URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"[a-z0-9.-]+(?::[1-9][0-9]{0,4})?", parsed.netloc)
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith(f"/{current}/manifest.json")
        or any(
            not re.fullmatch(r"[A-Za-z0-9._~-]+", part) or ".." in part or part == "."
            for part in parsed.path[1:].split("/")
        )
        or (parsed.port is not None and not 1 <= parsed.port <= 65_535)
    ):
        raise ValueError("invalid catalog manifest URL/identity")
    bounds = offering["bounds"]
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in bounds
        )
        or not (
            -180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90
        )
        or not _text(offering["display_name"], 120)
        or not _text(offering["description"], 500)
        or type(offering["download_bytes"]) is not int
    ):
        raise ValueError("invalid publication catalog values")
    for relative, files in regions.items():
        manifest = _read_object(bundle, f"{relative}/manifest.json")
        _, region_id, build_id = relative.split("/")
        if (
            region_id != offering["region_id"]
            or manifest.get("region_id") != region_id
            or manifest.get("build_id") != build_id
            or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 2
        ):
            raise ValueError("regional manifest path/build identity mismatch")
        if publication and manifest.get("publication_allowed") is not True:
            raise ValueError(
                "V2 DEM publication blocked pending provenance "
                "and redistribution review"
            )
        components = manifest.get("components")
        if not isinstance(components, dict) or set(components) != {
            "map",
            "routing",
            "pois",
            "nature",
            "elevation",
        }:
            raise ValueError("V2 requires five mandatory components")
        descriptors = [
            descriptor
            for component in components.values()
            for descriptor in component.get("files", [])
        ]
        if files != {
            "manifest.json",
            *(descriptor["path"] for descriptor in descriptors),
        }:
            raise ValueError("publication has an incomplete regional version")
        if relative == current and (
            manifest.get("bounds") != bounds
            or manifest.get("display_name") != offering["display_name"]
            or offering["download_bytes"]
            != sum(
                bundle.getinfo(f"{relative}/{name}").file_size
                for name in files - {"manifest.json"}
            )
        ):
            raise ValueError("catalog differs from advertised manifest/content")


def unpack_distribution(
    archive: Path,
    output: Path,
    expected_sha256: str,
    *,
    publication: bool = False,
    evidence_path: Path | None = None,
    approval_path: Path | None = None,
    trusted_approval_sha256: str | None = None,
) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError(
            "expected SHA-256 must contain 64 lowercase hexadecimal digits"
        )
    if not 0 < archive.stat().st_size <= MAX_BYTES:
        raise ValueError("publication archive exceeds the static host size budget")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_sha256:
            raise ValueError("publication archive checksum mismatch")
    if any(path.is_symlink() for path in (output, *output.absolute().parents)):
        raise ValueError("symbolic-link output path is not allowed")
    if output.exists():
        raise FileExistsError(output)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names: set[str] = set()
        regions: dict[str, set[str]] = {}
        total = 0
        if not 1 <= len(members) <= MAX_FILES:
            raise ValueError("invalid publication file count")
        for member in members:
            name = member.filename
            mode = member.external_attr >> 16
            if (
                name in names
                or member.compress_type != zipfile.ZIP_STORED
                or member.flag_bits & 1
                or stat.S_IFMT(mode) != stat.S_IFREG
                or member.is_dir()
            ):
                raise ValueError("invalid publication archive entry")
            names.add(name)
            if name == NOTICE_FILE and member.file_size > NOTICE_LIMIT:
                raise ValueError("oversized supplementary notice file")
            if name not in ROOT_FILES | {NOTICE_FILE}:
                match = re.fullmatch(
                    r"(regions/[a-z0-9][a-z0-9_-]{0,63}/[a-f0-9]{64})/(.+)", name
                )
                if match is None or (
                    match[2] not in REGIONAL_FILES
                    and not re.fullmatch(
                        r"elevation/skadi/[NS][0-9]{2}/[NS][0-9]{2}[EW][0-9]{3}\.hgt\.gz",
                        match[2],
                    )
                ):
                    raise ValueError("unexpected publication path")
                regions.setdefault(match[1], set()).add(match[2])
            total += member.file_size
            if member.file_size < 0 or total > MAX_BYTES:
                raise ValueError(
                    "publication content exceeds the static host size budget"
                )
        if not ROOT_FILES <= names or not regions:
            raise ValueError("publication is missing its catalog or attribution")
        _verify_identities(bundle, regions, publication)
        if publication:
            if (
                evidence_path is None
                or approval_path is None
                or trusted_approval_sha256 is None
                or len(regions) != 1
            ):
                raise ValueError(
                    "public V2 export requires exact-build operator approval"
                )
            from sugarglider.offline_regions.models import RegionalManifest
            from sugarglider.offline_regions.publication import (
                authorize_release_manifest,
                parse_publication_evidence,
            )

            if (
                evidence_path.stat().st_size > 32_768
                or approval_path.stat().st_size > 4096
            ):
                raise ValueError("oversized publication evidence/approval")
            evidence = parse_publication_evidence(evidence_path.read_bytes())
            from sugarglider.offline_regions.ign_publication import (
                IGNPublicationEvidence,
                require_ign_v2_namespace,
            )

            if isinstance(evidence, IGNPublicationEvidence):
                catalog = _read_object(bundle, "catalog.json")
                rows = catalog["regions"]
                assert isinstance(rows, list) and isinstance(rows[0], dict)
                require_ign_v2_namespace(
                    str(rows[0]["manifest_url"]).split("/regions/", 1)[0] + "/"
                )
            relative = next(iter(regions))
            manifest = RegionalManifest.model_validate_json(
                bundle.read(f"{relative}/manifest.json")
            )
            authorize_release_manifest(
                manifest,
                evidence,
                approval_path.read_bytes(),
                trusted_approval_sha256,
                elevation=ElevationManifest.model_validate_json(
                    bundle.read(f"{relative}/elevation/manifest.json")
                ),
            )
            from sugarglider.offline_regions.distribution import (
                _notice,
                distribution_index,
                publication_notice,
                supplementary_notice,
            )

            supplement = supplementary_notice(evidence)
            if supplement is not None:
                if NOTICE_FILE not in names or bundle.read(NOTICE_FILE) != supplement:
                    raise ValueError("missing or changed bound supplementary notices")
            if (
                bundle.getinfo("README.txt").file_size > 4 * NOTICE_LIMIT
                or bundle.getinfo("index.html").file_size > 4 * NOTICE_LIMIT
            ):
                raise ValueError("oversized hosted notice documents")
            expected_readme = (
                _notice(manifest, relative)
                + publication_notice(evidence, approval_path.read_bytes())
            ).encode("utf-8")
            catalog = _read_object(bundle, "catalog.json")
            rows = catalog["regions"]
            assert isinstance(rows, list) and isinstance(rows[0], dict)
            total = sum(
                bundle.getinfo(f"{relative}/{name}").file_size
                for name in regions[relative]
            )
            expected_index = distribution_index(
                manifest, str(rows[0]["description"]), total, relative, supplement
            ).encode("utf-8")
            if (
                bundle.read("README.txt") != expected_readme
                or bundle.read("index.html") != expected_index
            ):
                raise ValueError(
                    "hosted notices differ from exact approved notice rendering"
                )
            if supplement is None and NOTICE_FILE in names:
                raise ValueError(
                    "legacy evidence cannot authorize supplementary notices"
                )
        elif NOTICE_FILE in names:
            raise ValueError(
                "supplementary notices require independently approved v3 evidence"
            )
        output.mkdir()  # Exclusive output ownership; extraction never replaces data.
        try:
            for member in members:
                target = output / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as reader, target.open("xb") as writer:
                    shutil.copyfileobj(reader, writer, length=1_048_576)
            if publication:
                from sugarglider.offline_regions.validation import verify_region

                verify_region(output / next(iter(regions)))
            return output
        except BaseException:
            shutil.rmtree(output)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("expected_sha256")
    parser.add_argument(
        "--private",
        action="store_true",
        help="local verification only; never authorize publication",
    )
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--trusted-approval-sha256")
    arguments = parser.parse_args()
    unpack_distribution(
        arguments.archive,
        arguments.output,
        arguments.expected_sha256,
        publication=not arguments.private,
        evidence_path=arguments.evidence,
        approval_path=arguments.approval,
        trusted_approval_sha256=arguments.trusted_approval_sha256,
    )
    print(
        "Private archive verified; publication remains blocked."
        if arguments.private
        else "Authorized exact-build archive verified; nothing published."
    )


if __name__ == "__main__":
    main()
