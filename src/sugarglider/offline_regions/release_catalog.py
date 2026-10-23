"""Explicit V2 app-release gate; never changes the bundled/active public catalog."""

import argparse
import zipfile
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field

from sugarglider.offline_regions.distribution import distribution_base_url
from sugarglider.offline_regions.elevation_component import ElevationManifest
from sugarglider.offline_regions.ign_publication import (
    IGNPublicationEvidence,
    require_ign_v2_namespace,
)
from sugarglider.offline_regions.models import (
    Identifier,
    RegionBounds,
    Sha256,
    StrictModel,
    contained_path,
)
from sugarglider.offline_regions.publication import (
    authorize_release_manifest,
    parse_publication_evidence,
)
from sugarglider.offline_regions.publication_records import bounded_record
from sugarglider.offline_regions.validation import verify_region


class CatalogRow(StrictModel):
    region_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    build_id: Sha256
    bounds: RegionBounds
    download_bytes: Annotated[int, Field(gt=0, le=950_000_000)]
    manifest_url: Annotated[str, Field(min_length=1, max_length=2048)]


class ReleaseCatalog(StrictModel):
    schema_version: Literal[1]
    regions: Annotated[tuple[CatalogRow, ...], Field(min_length=1, max_length=32)]


def preflight_catalog(
    catalog: Path,
    site: Path,
    *,
    base_url: str,
    private: bool = False,
    evidence_path: Path | None = None,
    approval_path: Path | None = None,
    trusted_approval_sha256: str | None = None,
) -> ReleaseCatalog:
    base = distribution_base_url(base_url)
    if catalog.stat().st_size > 65_536:
        raise ValueError("catalog exceeds limit")
    parsed = ReleaseCatalog.model_validate_json(catalog.read_bytes())
    if len({row.region_id for row in parsed.regions}) != len(parsed.regions):
        raise ValueError("duplicate release catalog region")
    for row in parsed.regions:
        relative = f"regions/{row.region_id}/{row.build_id}"
        if row.manifest_url != f"{base}{relative}/manifest.json":
            raise ValueError("catalog URL must bind the exact immutable V2 build")
        manifest = verify_region(contained_path(site, relative))
        total = sum(f.byte_size for c in manifest.components.ordered for f in c.files)
        if (
            manifest.region_id != row.region_id
            or manifest.build_id != row.build_id
            or manifest.bounds != row.bounds
            or manifest.display_name != row.display_name
            or total != row.download_bytes
        ):
            raise ValueError(
                "catalog differs from verified V2 manifest/component bytes"
            )
        if not private:
            if (
                evidence_path is None
                or approval_path is None
                or trusted_approval_sha256 is None
            ):
                raise ValueError("app release requires explicit publication approval")
            evidence = parse_publication_evidence(bounded_record(evidence_path))
            if isinstance(evidence, IGNPublicationEvidence):
                require_ign_v2_namespace(base)
            authorize_release_manifest(
                manifest,
                evidence,
                bounded_record(approval_path, 4096),
                trusted_approval_sha256,
                elevation=ElevationManifest.model_validate_json(
                    bounded_record(
                        contained_path(site, relative + "/elevation/manifest.json"),
                        65_536,
                    )
                ),
            )
            from sugarglider.offline_regions.distribution import (
                _notice,
                distribution_index,
                publication_notice,
                supplementary_notice,
            )
            from sugarglider.offline_regions.source_notices import (
                NOTICE_FILE,
                NOTICE_LIMIT,
            )

            supplement = supplementary_notice(evidence)
            expected = {
                "README.txt": (
                    _notice(manifest, relative)
                    + publication_notice(evidence, bounded_record(approval_path, 4096))
                ).encode("utf-8"),
                "index.html": distribution_index(
                    manifest,
                    row.description,
                    total + (site / relative / "manifest.json").stat().st_size,
                    relative,
                    supplement,
                ).encode("utf-8"),
            }
            if supplement is not None:
                expected[NOTICE_FILE] = supplement
            for name, value in expected.items():
                if (
                    bounded_record(contained_path(site, name), 4 * NOTICE_LIMIT)
                    != value
                ):
                    raise ValueError(
                        "release catalog has missing or changed bound notices"
                    )
            if supplement is None and (site / NOTICE_FILE).exists():
                raise ValueError(
                    "legacy evidence cannot authorize supplementary notices"
                )
        if urlsplit(row.manifest_url).scheme != "https":
            raise ValueError("release requires HTTPS")
    return parsed


def verify_apk_catalog(apk: Path, catalog: Path) -> None:
    """Bind the actual assembled app's catalog, not a replacement host-only file."""
    with zipfile.ZipFile(apk) as archive:
        info = archive.getinfo("assets/web/offline_region_catalog.json")
        if info.file_size > 65_536:
            raise ValueError("APK catalog exceeds release budget")
        if archive.read(info) != catalog.read_bytes():
            raise ValueError("APK catalog differs from coordinated V2 catalog")
        if any(
            name.endswith((".hgt", ".hgt.gz", ".osm.pbf", ".pmtiles", ".tar"))
            for name in archive.namelist()
        ):
            raise ValueError("APK contains regional/DEM data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--trusted-approval-sha256")
    args = parser.parse_args()
    if args.apk is None and not args.private:
        parser.error("app release preflight requires the actual assembled --apk")
    if args.apk is not None:
        verify_apk_catalog(args.apk, args.catalog)
    preflight_catalog(
        args.catalog,
        args.site,
        base_url=args.base_url,
        private=args.private,
        evidence_path=args.evidence,
        approval_path=args.approval,
        trusted_approval_sha256=args.trusted_approval_sha256,
    )
    print(
        "Private V2 staging verified" if args.private else "V2 release preflight passed"
    )


if __name__ == "__main__":
    main()
