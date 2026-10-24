"""Entire IGN authorization path with synthetic bytes, never real authority."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import osmium
import pytest
from test_pr39_offline_regional_pipeline import fake_components

from sugarglider.offline_regions.build import build_region
from sugarglider.offline_regions.distribution import prepare_distribution
from sugarglider.offline_regions.elevation_component import ElevationManifest
from sugarglider.offline_regions.ign_publication import (
    LEGAL_URLS,
    IGNLegalEvidence,
    IGNNotices,
    IGNPublicationEvidence,
    prepare_ign_request,
    verify_ign_records,
)
from sugarglider.offline_regions.models import build_identity, canonical_json
from sugarglider.offline_regions.publication import (
    OperatorApproval,
    authorize_release_manifest,
    digest,
    parse_publication_evidence,
    prepare_approved_region,
)
from sugarglider.offline_regions.release_catalog import preflight_catalog
from sugarglider.offline_regions.unpack_distribution import unpack_distribution
from sugarglider.offline_regions.validation import verify_region

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://private.example.test/v2/"


class ApprovalArguments(TypedDict):
    evidence_path: Path
    approval_path: Path
    trusted_approval_sha256: str


@dataclass(frozen=True)
class IGNFixture:
    region: Path
    originals: Path
    prepared: Path
    conversion: Path
    graph: Path
    legal: Path
    pbf: Path
    evidence: IGNPublicationEvidence

    def verify(self, evidence: IGNPublicationEvidence | None = None) -> None:
        verify_ign_records(
            evidence or self.evidence,
            self.region,
            self.originals,
            self.prepared,
            self.conversion,
            self.graph,
            self.legal,
            self.pbf,
        )

    def approve(
        self, output: Path, approval: bytes | None = None, pin: str | None = None
    ) -> Path:
        value = synthetic_approval(self.evidence) if approval is None else approval
        prepare_approved_region(
            self.region,
            output,
            self.evidence,
            self.originals,
            self.conversion,
            self.graph,
            approval_bytes=value,
            trusted_approval_sha256=digest(value) if pin is None else pin,
            prepared=self.prepared,
            legal_directory=self.legal,
            osm_pbf=self.pbf,
        )
        return output


def synthetic_approval(evidence: IGNPublicationEvidence) -> bytes:
    return canonical_json(
        OperatorApproval(
            decision="approve-publication",
            operator="SYNTHETIC TEST ONLY",
            approved_at="2026-10-20T00:00:00Z",
            evidence_sha256=digest(canonical_json(evidence.model_dump(mode="json"))),
            release_build_id=evidence.release_build_id,
            scope="exact-regional-build-and-derived-DEM-enriched-graph",
            license_terms_accepted=True,
        ).model_dump(mode="json")
    )


def build_synthetic_ign(tmp_path: Path) -> IGNFixture:
    repository = tmp_path / "repository"
    repository.mkdir()
    for name in ("offline-regions", "map-packs"):
        shutil.copytree(ROOT / name, repository / name)
    pbf = tmp_path / "tiny.osm.pbf"
    processor = osmium.FileProcessor(ROOT / "tests/fixtures/pr39_region.osm")
    with osmium.SimpleWriter(pbf, header=processor.header) as writer:
        for entity in processor:
            writer.add(entity)
    region = build_region(
        repository, "yvelines-ouest-parisien", pbf, builder=fake_components
    )
    private = verify_region(region)
    originals, prepared, legal = (
        tmp_path / p for p in ("originals", "prepared", "legal")
    )
    for path in (originals, prepared, legal):
        path.mkdir()
    pins = json.loads(
        (ROOT / "offline-regions/sources/ign-rge-alti-5m-four-tiles.json").read_bytes()
    )
    grids = []
    for i, pin in enumerate(pins["files"]):
        data = f"SYNTHETIC archive {i}, not IGN data".encode()
        (originals / pin["filename"]).write_bytes(data)
        pin.update(byte_size=len(data), sha256=digest(data))
        name = f"grid-{i}"
        (prepared / (name + ".asc")).write_bytes(b"synthetic decoded grid")
        (prepared / (name + ".tif")).write_bytes(b"synthetic prepared grid")
        grids.append(
            dict(
                path=name + ".tif",
                source_archive_sha256=pin["sha256"],
                original_ascii_sha256=digest(b"synthetic decoded grid"),
                sha256=digest(b"synthetic prepared grid"),
            )
        )
    prepared_bytes = canonical_json(dict(sources=pins, grids=grids))
    (prepared / "prepared.json").write_bytes(prepared_bytes)
    tiles = private.components.elevation.files[1:]
    conversion = tmp_path / "conversion.json"
    conversion_bytes = canonical_json(
        dict(
            algorithm="ign-rge-alti-5m-ign69-skadi-v1",
            sources=pins,
            prepared_sha256=digest(prepared_bytes),
            input_vertical_crs="EPSG:5720",
            output_vertical_crs="EPSG:5720",
            vertical_operation="identity; IGN69 normal heights retained",
            interpolation="bilinear point nodes; all positive-weight nodes required",
            rounding="nearest integer ties to even; <=0.5 m",
            nodata=-32768,
            tiles=[
                dict(
                    path=f.path.removeprefix("elevation/skadi/"),
                    sha256=f.sha256,
                    byte_size=f.byte_size,
                )
                for f in tiles
            ],
        )
    )
    conversion.write_bytes(conversion_bytes)
    metadata = json.loads((region / "elevation/manifest.json").read_bytes())
    metadata.update(
        provenance_status="documented",
        vertical_datum="IGN69",
        derivation=dict(
            algorithm="ign-rge-alti-5m-ign69-skadi-v1",
            sources=pins,
            prepared_sha256=digest(prepared_bytes),
            transformation_sha256=digest(conversion_bytes),
        ),
    )
    elevation_bytes = canonical_json(metadata)
    ElevationManifest.model_validate_json(elevation_bytes)
    (region / "elevation/manifest.json").write_bytes(elevation_bytes)
    payload = private.model_dump(mode="json", exclude={"build_id"})
    payload["components"]["elevation"]["files"][0].update(
        byte_size=len(elevation_bytes), sha256=digest(elevation_bytes)
    )
    payload["build_id"] = build_identity(payload)
    (region / "manifest.json").write_bytes(canonical_json(payload))
    private = verify_region(region)
    graph = tmp_path / "graph.json"
    graph.write_bytes(
        canonical_json(
            dict(
                private_build_id=private.build_id,
                graph_sha256=private.components.routing.files[1].sha256,
                source_pbf_sha256=private.source.sha256,
                valhalla_image=private.tools.valhalla_image,
                enrichment=(
                    "valhalla_build_tiles; additional_data.elevation; network=none"
                ),
                dem_tiles=[f.model_dump(mode="json") for f in tiles],
            )
        )
    )
    documents = []
    for role, url in LEGAL_URLS.items():
        value = f"SYNTHETIC legal evidence {role}; not a licence".encode()
        (legal / (role + ".txt")).write_bytes(value)
        documents.append(
            dict(
                role=role,
                url=url,
                path=role + ".txt",
                byte_size=len(value),
                sha256=digest(value),
            )
        )
    legal_evidence = IGNLegalEvidence.model_validate_json(
        canonical_json(
            dict(
                schema_version=1,
                status="evidence-for-human-review-not-authorization",
                retrieved_at="2026-10-20T00:00:00Z",
                documents=documents,
            )
        )
    )
    notices = IGNNotices(
        ign="IGN — RGE ALTI® 5 m; Licence Ouverte / Open Licence 2.0",
        osm="© OpenStreetMap contributors; ODbL 1.0",
        source_editions=tuple(p["filename"] for p in pins["files"]),
        heights="NGF-IGN69 normal heights (EPSG:5720); no vertical conversion",
        modifications=(
            "5 m point grids to 1 arc-second HGT; bilinear; integer quantization; "
            "DEM-enriched Valhalla graph"
        ),
        database_offer="entire-derived-databases-in-regional-components",
        database_terms="ODbL-1.0; IGN contents under Licence Ouverte 2.0",
        no_endorsement="No IGN or OpenStreetMap endorsement; no warranty",
    )
    evidence = prepare_ign_request(
        region,
        originals,
        prepared,
        conversion,
        graph,
        legal,
        legal_evidence,
        notices,
        pbf,
    )
    return IGNFixture(
        region, originals, prepared, conversion, graph, legal, pbf, evidence
    )


@pytest.fixture
def ign(tmp_path: Path) -> IGNFixture:
    return build_synthetic_ign(tmp_path)


def test_full_synthetic_ign_authorization_distribution_and_unpack(
    ign: IGNFixture, tmp_path: Path
) -> None:
    before = {
        p.relative_to(ign.region): p.read_bytes()
        for p in ign.region.rglob("*")
        if p.is_file()
    }
    assert not verify_region(ign.region).publication_allowed
    assert (
        parse_publication_evidence(canonical_json(ign.evidence.model_dump(mode="json")))
        == ign.evidence
    )
    approved = ign.approve(tmp_path / "approved")
    manifest = verify_region(approved)
    assert (
        manifest.publication_allowed
        and manifest.build_id == ign.evidence.release_build_id
    )
    elevation = ElevationManifest.model_validate_json(
        (approved / "elevation/manifest.json").read_bytes()
    )
    assert elevation.vertical_datum == "IGN69"
    assert elevation.publication_basis_sha256 == ign.evidence.basis_sha256
    assert len(elevation.tiles) == 4 and len(manifest.components.ordered) == 5
    assert {
        p.relative_to(ign.region): p.read_bytes()
        for p in ign.region.rglob("*")
        if p.is_file()
    } == before
    evidence_path, approval_path = (
        tmp_path / "evidence.json",
        tmp_path / "approval.json",
    )
    evidence_path.write_bytes(canonical_json(ign.evidence.model_dump(mode="json")))
    approval = synthetic_approval(ign.evidence)
    approval_path.write_bytes(approval)
    kwargs: ApprovalArguments = dict(
        evidence_path=evidence_path,
        approval_path=approval_path,
        trusted_approval_sha256=digest(approval),
    )
    output = tmp_path / "distribution"
    prepare_distribution(
        approved, output, base_url=BASE, description="Synthetic IGN", **kwargs
    )
    preflight_catalog(
        output / "site/catalog.json", output / "site", base_url=BASE, **kwargs
    )
    notice = (output / "site/README.txt").read_text()
    assert "IGN69" in notice and "EGM96" not in notice
    assert "OpenStreetMap" in notice and "Licence Ouverte" in notice
    assert "Free machine-readable offer" in notice
    archive = output / "sugarglider-regions-static.zip"
    unpacked = tmp_path / "unpacked"
    unpack_distribution(
        archive, unpacked, digest(archive.read_bytes()), publication=True, **kwargs
    )
    assert (
        verify_region(unpacked / "regions" / manifest.region_id / manifest.build_id)
        == manifest
    )


@pytest.mark.parametrize("approval,pin", [(b"", None), (None, "0" * 64)])
def test_missing_or_untrusted_human_approval_never_writes_output(
    ign: IGNFixture,
    tmp_path: Path,
    approval: bytes | None,
    pin: str | None,
) -> None:
    output = tmp_path / "forbidden"
    with pytest.raises(ValueError):
        ign.approve(output, approval, pin)
    assert not output.exists()
    assert not verify_region(ign.region).publication_allowed


@pytest.mark.parametrize(
    "part",
    [
        "archive",
        "grid",
        "ascii",
        "prepared",
        "conversion",
        "graph-record",
        "legal",
        "pbf",
        "hgt",
        "graph",
        "pois",
        "nature",
        "map",
        "missing-component",
    ],
)
def test_changed_retained_bytes_fail_before_any_approved_copy(
    ign: IGNFixture,
    tmp_path: Path,
    part: str,
) -> None:
    paths = {
        "archive": next(ign.originals.iterdir()),
        "grid": next(ign.prepared.glob("*.tif")),
        "ascii": next(ign.prepared.glob("*.asc")),
        "prepared": ign.prepared / "prepared.json",
        "conversion": ign.conversion,
        "graph-record": ign.graph,
        "legal": next(ign.legal.iterdir()),
        "pbf": ign.pbf,
        "hgt": next(ign.region.rglob("*.hgt.gz")),
        "graph": ign.region / "routing/valhalla_tiles.tar",
        "pois": ign.region / "pois/index.json.gz",
        "nature": ign.region / "nature/index.json.gz",
        "map": ign.region / "map/basemap.pmtiles",
        "missing-component": ign.region / "elevation/manifest.json",
    }
    path = paths[part]
    if part == "missing-component":
        path.unlink()
    else:
        data = path.read_bytes()
        path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    output = tmp_path / "forbidden"
    with pytest.raises((ValueError, OSError)):
        ign.approve(output)
    assert not output.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "legal-missing",
        "legal-url",
        "legal-duplicate",
        "ign-attribution",
        "osm-attribution",
        "datum",
        "private-id",
        "graph",
        "hgt",
        "editions",
        "unknown-product",
    ],
)
def test_missing_or_invalid_source_specific_evidence_is_rejected(
    ign: IGNFixture, fault: str
) -> None:
    payload: dict[str, Any] = ign.evidence.model_dump(mode="json")
    basis = payload["basis"]
    if fault == "source":
        del basis["derivation"]["sources"]
    elif fault == "legal-missing":
        del basis["legal_evidence"]
    elif fault == "legal-url":
        basis["legal_evidence"]["documents"][0]["url"] = "https://example.test/license"
    elif fault == "legal-duplicate":
        basis["legal_evidence"]["documents"][-1] = basis["legal_evidence"]["documents"][
            0
        ]
    elif fault == "ign-attribution":
        basis["notices"]["ign"] = ""
    elif fault == "osm-attribution":
        basis["notices"]["osm"] = ""
    elif fault == "datum":
        basis["output_vertical_crs"] = "EPSG:5773"
    elif fault == "private-id":
        payload["private_build_id"] = "0" * 64
    elif fault == "graph":
        payload["graph_sha256"] = "0" * 64
    elif fault == "hgt":
        payload["derived_tiles"][0]["sha256"] = "0" * 64
    elif fault == "editions":
        basis["notices"]["source_editions"] = ["2026"]
    else:
        payload["upstream_product"] = "unknown"
    with pytest.raises(ValueError):
        parse_publication_evidence(canonical_json(payload))


def test_different_build_approval_and_changes_to_any_component_are_rejected(
    ign: IGNFixture, tmp_path: Path
) -> None:
    approved = ign.approve(tmp_path / "approved")
    manifest = verify_region(approved)
    approval = synthetic_approval(ign.evidence)
    for change in ({"release_build_id": "f" * 64},):
        with pytest.raises(ValueError):
            authorize_release_manifest(
                manifest,
                ign.evidence.model_copy(update=change),
                approval,
                digest(approval),
            )
    payload = manifest.model_dump(mode="json", exclude={"build_id"})
    payload["components"]["map"]["files"][1]["sha256"] = "f" * 64
    payload["build_id"] = build_identity(payload)
    from sugarglider.offline_regions.models import RegionalManifest

    with pytest.raises(ValueError):
        authorize_release_manifest(
            RegionalManifest.model_validate_json(canonical_json(payload)),
            ign.evidence,
            approval,
            digest(approval),
        )


@pytest.mark.parametrize(
    "base",
    [
        "http://example.test/v2/",
        "https://user@example.test/",
        "https://example.test/v2/?token=x",
        "https://example.test/v2/../v1/",
        "https://example.test/v2/#x",
    ],
)
def test_unsafe_urls_and_private_publication_fail_closed(
    ign: IGNFixture, tmp_path: Path, base: str
) -> None:
    with pytest.raises(ValueError):
        prepare_distribution(
            ign.region, tmp_path / "bad", base_url=base, description="Synthetic"
        )
    assert not (tmp_path / "bad").exists()


def test_real_private_identity_and_v1_catalog_are_not_replaced() -> None:
    # Lock the production V1 catalog bytes. V2 staging must be an explicit input.
    assert (
        digest(
            (
                ROOT / "src/sugarglider/web/static/offline_region_catalog.json"
            ).read_bytes()
        )
        == V1_CATALOG_SHA256
    )


def test_python_and_browser_share_the_synthetic_ign_public_wire_contract() -> None:
    from sugarglider.offline_regions.models import RegionalManifest

    vector = json.loads(
        (ROOT / "tests/fixtures/pr101_ign_publication.json").read_bytes()
    )
    assert vector["synthetic_only"] is True
    regional = RegionalManifest.model_validate_json(canonical_json(vector["manifest"]))
    elevation_bytes = canonical_json(vector["elevation"])
    elevation = ElevationManifest.model_validate_json(elevation_bytes)
    assert regional.components.elevation.files[0].sha256 == digest(elevation_bytes)
    assert elevation.vertical_datum == "IGN69"
    assert elevation.publication_basis_sha256 is not None


@pytest.mark.parametrize("gate", ["package", "catalog", "unpack"])
def test_each_ign_export_gate_requires_independent_approval(
    ign: IGNFixture,
    tmp_path: Path,
    gate: str,
) -> None:
    approved = ign.approve(tmp_path / "approved")
    evidence_path, approval_path = (
        tmp_path / "evidence.json",
        tmp_path / "approval.json",
    )
    evidence_path.write_bytes(canonical_json(ign.evidence.model_dump(mode="json")))
    approval = synthetic_approval(ign.evidence)
    approval_path.write_bytes(approval)
    kwargs: ApprovalArguments = dict(
        evidence_path=evidence_path,
        approval_path=approval_path,
        trusted_approval_sha256=digest(approval),
    )
    distribution = tmp_path / "distribution"
    prepare_distribution(
        approved, distribution, base_url=BASE, description="Synthetic", **kwargs
    )
    kwargs["trusted_approval_sha256"] = "0" * 64
    output = tmp_path / "denied"
    with pytest.raises(ValueError, match="independently authorized"):
        if gate == "package":
            prepare_distribution(
                approved, output, base_url=BASE, description="Synthetic", **kwargs
            )
        elif gate == "catalog":
            preflight_catalog(
                distribution / "site/catalog.json",
                distribution / "site",
                base_url=BASE,
                **kwargs,
            )
        else:
            archive = distribution / "sugarglider-regions-static.zip"
            unpack_distribution(
                archive,
                output,
                digest(archive.read_bytes()),
                publication=True,
                **kwargs,
            )
    assert not output.exists()
    kwargs["trusted_approval_sha256"] = digest(approval)
    with pytest.raises(ValueError, match="/v2/"):
        prepare_distribution(
            approved,
            output,
            base_url="https://private.example.test/v1/",
            description="Synthetic",
            **kwargs,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("output_vertical_crs", "EPSG:5773"),
        ("input_vertical_crs", "EPSG:5773"),
        ("vertical_operation", "geoid shift"),
        ("algorithm", "cop-dem-cog-egm96-v1"),
        ("tiles", []),
    ],
)
def test_rehashed_but_semantically_wrong_conversion_cannot_request_approval(
    ign: IGNFixture,
    field: str,
    value: object,
) -> None:
    conversion = json.loads(ign.conversion.read_bytes())
    conversion[field] = value
    ign.conversion.write_bytes(canonical_json(conversion))
    metadata = json.loads((ign.region / "elevation/manifest.json").read_bytes())
    metadata["derivation"]["transformation_sha256"] = digest(
        ign.conversion.read_bytes()
    )
    metadata_bytes = canonical_json(metadata)
    (ign.region / "elevation/manifest.json").write_bytes(metadata_bytes)
    regional = reidentify_synthetic_metadata(ign.region, metadata_bytes)
    graph = json.loads(ign.graph.read_bytes())
    graph["private_build_id"] = regional
    ign.graph.write_bytes(canonical_json(graph))
    with pytest.raises(ValueError, match="conversion/datum/HGT"):
        prepare_ign_request(
            ign.region,
            ign.originals,
            ign.prepared,
            ign.conversion,
            ign.graph,
            ign.legal,
            ign.evidence.basis.legal_evidence,
            ign.evidence.basis.notices,
            ign.pbf,
        )


def reidentify_synthetic_metadata(region: Path, metadata: bytes) -> str:
    """Reidentify a synthetic mutation so semantic checks must catch it."""
    payload = json.loads((region / "manifest.json").read_bytes())
    payload.pop("build_id")
    payload["components"]["elevation"]["files"][0].update(
        byte_size=len(metadata), sha256=digest(metadata)
    )
    payload["build_id"] = build_identity(payload)
    (region / "manifest.json").write_bytes(canonical_json(payload))
    return verify_region(region).build_id


V1_CATALOG_SHA256 = "009a3ebcdd5d8774b04f58320eca0f92a58adab55ef521fe675d9aa7332ba48c"
