"""Synthetic factual evidence/authorization; no DEM, network or external services."""

import json
import shutil
from pathlib import Path
from typing import TypedDict

import osmium
import pytest
from test_pr39_offline_regional_pipeline import fake_components

from sugarglider.offline_regions.build import build_region
from sugarglider.offline_regions.distribution import prepare_distribution
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import (
    OperatorApproval,
    PublicationEvidence,
    authorize_release_manifest,
    digest,
    prepare_approved_region,
    prepare_publication_request,
    verify_approval,
    verify_evidence,
)
from sugarglider.offline_regions.release_catalog import preflight_catalog
from sugarglider.offline_regions.terrain_conversion import (
    geoid_pipeline,
    quantize_height,
)
from sugarglider.offline_regions.terrain_source import (
    TerrainSources,
    verify_source,
)
from sugarglider.offline_regions.unpack_distribution import unpack_distribution
from sugarglider.offline_regions.validation import verify_region

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://private.example.test/"


class ApprovalArguments(TypedDict):
    evidence_path: Path
    approval_path: Path
    trusted_approval_sha256: str


@pytest.fixture
def private_region(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    for name in ("offline-regions", "map-packs"):
        shutil.copytree(ROOT / name, repository / name)
    pbf = tmp_path / "tiny.osm.pbf"
    processor = osmium.FileProcessor(ROOT / "tests/fixtures/pr39_region.osm")
    with osmium.SimpleWriter(pbf, header=processor.header) as writer:
        for entity in processor:
            writer.add(entity)
    return build_region(repository, "marly", pbf, builder=fake_components)


@pytest.fixture
def sources(tmp_path: Path) -> TerrainSources:
    value = json.loads(
        (ROOT / "offline-regions/sources/copernicus-2021-yvelines.json").read_bytes()
    )
    originals = tmp_path / "originals"
    originals.mkdir()
    for file in value["files"]:
        contents = b"synthetic source; not terrain data"
        (originals / file["filename"]).write_bytes(contents)
        file["byte_size"], file["sha256"] = len(contents), digest(contents)
    return TerrainSources.model_validate_json(json.dumps(value))


@pytest.fixture
def facts(
    tmp_path: Path, private_region: Path, sources: TerrainSources
) -> tuple[Path, PublicationEvidence]:
    private = verify_region(private_region)
    transform = {
        "sources": sources.model_dump(mode="json"),
        "algorithm": "cop-dem-cog-egm96-v1",
        "output_vertical_crs": "EPSG:5773",
        "input_vertical_crs": "EPSG:3855",
        "pipeline": geoid_pipeline(tmp_path / "originals"),
        "tiles": [
            {
                "path": f.path.removeprefix("elevation/skadi/"),
                "sha256": f.sha256,
                "byte_size": f.byte_size,
            }
            for f in private.components.elevation.files[1:]
        ],
    }
    record = {
        "graph_sha256": private.components.routing.files[1].sha256,
        "source_pbf_sha256": private.source.sha256,
        "valhalla_image": private.tools.valhalla_image,
        "enrichment": "valhalla_build_tiles; additional_data.elevation; network=none",
        "dem_tiles": [
            f.model_dump(mode="json") for f in private.components.elevation.files[1:]
        ],
    }
    (tmp_path / "transformation.json").write_bytes(canonical_json(transform))
    (tmp_path / "graph.json").write_bytes(canonical_json(record))
    output = tmp_path / "documented"
    evidence = prepare_publication_request(
        private_region,
        output,
        sources,
        tmp_path / "originals",
        tmp_path / "transformation.json",
        tmp_path / "graph.json",
    )
    assert not verify_region(output).publication_allowed
    assert not list(tmp_path.glob("*approval*"))
    return output, evidence


def synthetic_approval(evidence: PublicationEvidence) -> bytes:
    """Explicit synthetic authorization only; never an operator record for real data."""
    approval = OperatorApproval(
        decision="approve-publication",
        operator="SYNTHETIC TEST AUTHORITY",
        approved_at="2026-01-01T00:00:00Z",
        evidence_sha256=digest(canonical_json(evidence.model_dump(mode="json"))),
        release_build_id=evidence.release_build_id,
        scope="exact-regional-build-and-derived-DEM-enriched-graph",
        license_terms_accepted=True,
    )
    return canonical_json(approval.model_dump(mode="json"))


def test_facts_are_private_and_approval_is_independently_pinned(
    facts: tuple[Path, PublicationEvidence],
) -> None:
    region, evidence = facts
    assert not verify_region(region).publication_allowed
    approval = synthetic_approval(evidence)
    with pytest.raises(ValueError, match="independently authorized"):
        verify_approval(evidence, approval, "0" * 64)
    with pytest.raises(ValueError):
        verify_approval(evidence, b"", digest(b""))
    assert (
        verify_approval(evidence, approval, digest(approval)).release_build_id
        == evidence.release_build_id
    )
    changed = evidence.model_copy(update={"release_build_id": "f" * 64})
    with pytest.raises(ValueError, match="does not match"):
        verify_approval(changed, approval, digest(approval))


def test_exact_authorization_can_prepare_and_verify_an_approved_copy(
    tmp_path: Path,
    facts: tuple[Path, PublicationEvidence],
) -> None:
    private, evidence = facts
    before = (private / "manifest.json").read_bytes()
    approval = synthetic_approval(evidence)
    approved = tmp_path / "approved"
    manifest = prepare_approved_region(
        private,
        approved,
        evidence,
        tmp_path / "originals",
        tmp_path / "transformation.json",
        tmp_path / "graph.json",
        approval_bytes=approval,
        trusted_approval_sha256=digest(approval),
    )
    assert (
        manifest.publication_allowed and manifest.build_id == evidence.release_build_id
    )
    assert (private / "manifest.json").read_bytes() == before
    evidence_path, approval_path = (
        tmp_path / "evidence.json",
        tmp_path / "approval.json",
    )
    evidence_path.write_bytes(canonical_json(evidence.model_dump(mode="json")))
    approval_path.write_bytes(approval)
    kwargs: ApprovalArguments = dict(
        evidence_path=evidence_path,
        approval_path=approval_path,
        trusted_approval_sha256=digest(approval),
    )
    with pytest.raises(ValueError, match="operator approval"):
        prepare_distribution(
            approved, tmp_path / "denied", base_url=BASE, description="Synthetic"
        )
    output = tmp_path / "distribution"
    prepare_distribution(
        approved, output, base_url=BASE, description="Synthetic", **kwargs
    )
    preflight_catalog(
        output / "site/catalog.json", output / "site", base_url=BASE, **kwargs
    )
    archive = output / "sugarglider-regions-static.zip"
    checksum = digest(archive.read_bytes())
    with pytest.raises(ValueError, match="operator approval"):
        unpack_distribution(
            archive, tmp_path / "missing-approval", checksum, publication=True
        )
    unpack_distribution(
        archive, tmp_path / "unpacked", checksum, publication=True, **kwargs
    )
    changed = manifest.model_copy(update={"build_id": "f" * 64})
    with pytest.raises(ValueError, match="does not match"):
        authorize_release_manifest(changed, evidence, approval, digest(approval))


@pytest.mark.parametrize(
    "field,value",
    [
        ("sources", None),
        ("transformation", None),
        ("output_vertical_crs", "EGM2008"),
        ("geoid_license", "unknown"),
        ("transformation_sha256", "incorrect"),
    ],
)
def test_unknown_missing_or_mismatched_evidence_is_not_a_release(
    facts: tuple[Path, PublicationEvidence],
    field: str,
    value: object,
) -> None:
    payload = facts[1].model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        PublicationEvidence.model_validate_json(json.dumps(payload))


def test_source_transformation_graph_and_derived_hashes_remain_bound(
    tmp_path: Path,
    facts: tuple[Path, PublicationEvidence],
) -> None:
    directory, evidence = facts
    private = verify_region(directory)
    from sugarglider.offline_regions.publication import release_manifests

    proposed, _ = release_manifests(directory, private)
    args = (
        private,
        proposed,
        tmp_path / "originals",
        tmp_path / "transformation.json",
        tmp_path / "graph.json",
    )
    verify_evidence(evidence, *args)
    pin = evidence.sources.files[0]
    original = tmp_path / "originals" / pin.filename
    original.write_bytes(b"x" * pin.byte_size)
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_evidence(evidence, *args)


def test_research_distribution_and_v1_catalog_are_rejected_for_release(
    tmp_path: Path,
    private_region: Path,
) -> None:
    output = tmp_path / "distribution"
    prepare_distribution(private_region, output, base_url=BASE, description="Synthetic")
    preflight_catalog(
        output / "site/catalog.json", output / "site", base_url=BASE, private=True
    )
    with pytest.raises(ValueError, match="approval"):
        preflight_catalog(output / "site/catalog.json", output / "site", base_url=BASE)
    archive = output / "sugarglider-regions-static.zip"
    with pytest.raises(ValueError, match="publication blocked"):
        unpack_distribution(
            archive, tmp_path / "public", digest(archive.read_bytes()), publication=True
        )
    row = json.loads((output / "site/catalog.json").read_bytes())["regions"][0]
    path = output / f"site/regions/{row['region_id']}/{row['build_id']}/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["schema_version"] = 1
    path.write_bytes(canonical_json(manifest))
    with pytest.raises(ValueError):
        preflight_catalog(
            output / "site/catalog.json", output / "site", base_url=BASE, private=True
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -16385.0, 16385.0])
def test_invalid_terrain_cannot_be_quantized_to_a_valid_height(value: float) -> None:
    with pytest.raises(ValueError):
        quantize_height(value)


def test_height_quantization_is_signed_and_missing_is_never_zero() -> None:
    assert quantize_height(None) == -32768
    assert quantize_height(-1.5) == -2
    assert quantize_height(0.0) == 0
    assert quantize_height(0.5) == 0
    assert quantize_height(1.5) == 2


def test_source_hash_and_complete_product_are_required(
    tmp_path: Path,
    sources: TerrainSources,
) -> None:
    verify_source(tmp_path / "originals", sources.files[0])
    with pytest.raises(ValueError):
        verify_source(
            tmp_path / "originals",
            sources.files[0].model_copy(update={"sha256": "f" * 64}),
        )
    value = sources.model_dump(mode="json")
    value["files"][-1] = value["files"][0]
    with pytest.raises(ValueError, match="incomplete"):
        TerrainSources.model_validate_json(json.dumps(value))
    value = sources.model_dump(mode="json")
    value["license_url"] = "https://unknown.example/license"
    with pytest.raises(ValueError):
        TerrainSources.model_validate_json(json.dumps(value))


def test_conversion_is_reproducible_north_to_south_big_endian_and_void_safe(
    tmp_path: Path,
) -> None:
    import gzip
    import struct

    from sugarglider.offline_regions.terrain_conversion import convert_tile

    def row(latitude: float, west: int, count: int) -> list[float | None]:
        assert west == 1 and count == 3601
        return [latitude, *([None] * 3599), 100.0]

    def datum(lon: float, lat: float, height: float) -> float:
        return height + lon * 0.25 - lat * 0.125

    first, second = tmp_path / "one.hgt.gz", tmp_path / "two.hgt.gz"
    convert_tile(first, 48, 1, row, datum)
    convert_tile(second, 48, 1, row, datum)
    assert first.read_bytes() == second.read_bytes()
    data = gzip.decompress(first.read_bytes())
    assert len(data) == 3601 * 3601 * 2
    assert struct.unpack_from(">h", data, 0)[0] == round(datum(1, 49, 49))
    assert struct.unpack_from(">h", data, 3600 * 3601 * 2)[0] == round(datum(1, 48, 48))
    assert struct.unpack_from(">h", data, 2)[0] == -32768
    assert struct.unpack_from(">h", data, 3600 * 2)[0] == round(datum(2, 49, 100))
    with pytest.raises(FileExistsError):
        convert_tile(first, 48, 1, row, datum)


def test_apk_release_catalog_is_checked_inside_the_actual_archive(
    tmp_path: Path,
) -> None:
    import zipfile

    from sugarglider.offline_regions.release_catalog import verify_apk_catalog

    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b'{"schema_version":1,"regions":[]}')
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("assets/web/offline_region_catalog.json", b"old V1 catalog")
    with pytest.raises(ValueError, match="APK catalog differs"):
        verify_apk_catalog(apk, catalog)
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("assets/web/offline_region_catalog.json", catalog.read_bytes())
    verify_apk_catalog(apk, catalog)


@pytest.mark.parametrize(
    "fault", ["none", "corrupt", "redirect", "cookie", "encoding", "cors", "range"]
)
def test_https_audit_enforces_transport_contract_without_network(
    private_region: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import ssl

    import httpx

    from sugarglider.offline_regions.https_transport import (
        ANDROID_ORIGIN,
        verify_https_region,
    )

    manifest = verify_region(private_region)
    descriptors = {f.path: f for c in manifest.components.ordered for f in c.files}
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.headers["origin"] == ANDROID_ORIGIN
        assert request.headers["accept-encoding"] == "identity"
        assert (
            "cookie" not in request.headers and "authorization" not in request.headers
        )
        path = next(p for p in descriptors if request.url.path.endswith("/" + p))
        descriptor = descriptors[path]
        data = (private_region / path).read_bytes()
        headers = {
            "Content-Length": str(len(data)),
            "Access-Control-Allow-Origin": ANDROID_ORIGIN,
        }
        status = 200
        if "range" in request.headers:
            data = data[:127]
            headers.update(
                {
                    "Content-Length": "127",
                    "Content-Range": f"bytes 0-126/{descriptor.byte_size}",
                }
            )
            status = 200 if fault == "range" else 206
        elif fault == "corrupt":
            data = bytes([data[0] ^ 1]) + data[1:]
        elif fault == "redirect":
            status = 302
            headers["Location"] = "https://another.example/"
        elif fault == "cookie":
            headers["Set-Cookie"] = "unexpected=value"
        elif fault == "encoding":
            headers["Content-Encoding"] = "gzip"
        elif fault == "cors":
            headers["Access-Control-Allow-Origin"] = "*"
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(data))

    def client(
        *,
        verify: ssl.SSLContext,
        follow_redirects: bool,
        trust_env: bool,
        timeout: float,
    ) -> httpx.Client:
        assert verify.check_hostname and verify.verify_mode == ssl.CERT_REQUIRED
        assert not follow_redirects and not trust_env and timeout == 120.0
        return original_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", client)
    if fault == "none":
        result = verify_https_region(manifest, BASE)
        assert result["download_bytes"] == sum(
            f.byte_size for f in descriptors.values()
        )
    else:
        with pytest.raises(ValueError):
            verify_https_region(manifest, BASE)


def test_per_file_provenance_matches_the_source_hashes_and_distinguishes_geoids() -> (
    None
):
    pins = TerrainSources.model_validate_json(
        (ROOT / "offline-regions/sources/copernicus-2021-yvelines.json").read_bytes()
    )
    metadata = json.loads(
        (
            ROOT / "offline-regions/sources/copernicus-2021-yvelines-metadata.json"
        ).read_bytes()
    )
    files = {row["filename"]: row for row in metadata["files"]}
    assert set(files) == {pin.filename for pin in pins.files}
    for pin in pins.files:
        record = files[pin.filename]
        assert record["sha256"] == pin.sha256 and record["byte_size"] == pin.byte_size
        assert record["url"] == pin.url
        assert record["format"] == "GTiff" and record["compression"] == "DEFLATE"
        assert record["units"] == "metres"
        if pin.filename.startswith("us_nga_"):
            assert "geoid undulation" in record["dataset"]
            assert "OSGeo/PROJ-data" in record["license_evidence"]
        else:
            assert record["shape"] == [3600, 3600]
            assert record["vertical_reference"] == "EGM2008 physical height; EPSG:3855"
