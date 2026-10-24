"""IGN69 exact-build facts for independent human review, never legal approval.

The basis is computed before the proposed public manifest, avoiding a circular
hash. The detached operator approval then binds the entire evidence, including
that proposed build. Readers validate metadata; exporters validate authority.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from sugarglider.offline_regions.elevation_component import (
    ElevationManifest,
    IGNDerivation,
)
from sugarglider.offline_regions.models import (
    FileDescriptor,
    RegionalManifest,
    RelativePath,
    Sha256,
    StrictModel,
    canonical_json,
    contained_path,
)
from sugarglider.offline_regions.publication_records import bounded_record, digest
from sugarglider.offline_regions.terrain_ign import PreparedIGN
from sugarglider.offline_regions.terrain_source import IGN_ATTRIBUTION, verify_source

LEGAL_URLS = {
    "ign-product": "https://www.data.gouv.fr/api/1/datasets/rge-alti-r/",
    "open-licence": (
        "https://www.etalab.gouv.fr/wp-content/uploads/2017/04/"
        "ETALAB-Licence-Ouverte-v2.0.pdf"
    ),
    "odbl": "https://opendatacommons.org/licenses/odbl/odbl-10.txt",
    "osm-attribution": "https://osmfoundation.org/wiki/Licence/Attribution_Guidelines",
    "osm-collective": (
        "https://osmfoundation.org/wiki/Licence/Community_Guidelines/"
        "Collective_Database_Guideline_Guideline"
    ),
}


def require_ign_v2_namespace(base: str) -> None:
    if "v2" not in urlsplit(base).path.split("/"):
        raise ValueError(
            "IGN distribution requires a separate /v2/ namespace; retain V1"
        )


class LegalDocument(StrictModel):
    role: Literal[
        "ign-product", "open-licence", "odbl", "osm-attribution", "osm-collective"
    ]
    url: str
    path: RelativePath
    byte_size: Annotated[int, Field(gt=0, le=8_388_608)]
    sha256: Sha256

    @model_validator(mode="after")
    def official_url(self) -> Self:
        if self.url != LEGAL_URLS[self.role]:
            raise ValueError("legal evidence must identify the official document")
        return self


class IGNLegalEvidence(StrictModel):
    schema_version: Literal[1] = 1
    status: Literal["evidence-for-human-review-not-authorization"]
    retrieved_at: str
    documents: Annotated[tuple[LegalDocument, ...], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def complete_documents(self) -> Self:
        if (
            {d.role for d in self.documents} != set(LEGAL_URLS)
            or len({d.path for d in self.documents}) != 5
            or not 20 <= len(self.retrieved_at) <= 40
            or datetime.fromisoformat(self.retrieved_at).tzinfo is None
        ):
            raise ValueError("incomplete legal evidence or retrieval identity")
        return self


class IGNNotices(StrictModel):
    ign: Literal["IGN — RGE ALTI® 5 m; Licence Ouverte / Open Licence 2.0"]
    osm: Literal["© OpenStreetMap contributors; ODbL 1.0"]
    source_editions: Annotated[tuple[str, ...], Field(min_length=1, max_length=24)]
    heights: Literal["NGF-IGN69 normal heights (EPSG:5720); no vertical conversion"]
    modifications: Literal[
        "5 m point grids to 1 arc-second HGT; bilinear; integer quantization; "
        "DEM-enriched Valhalla graph"
    ]
    database_offer: Literal["entire-derived-databases-in-regional-components"]
    database_terms: Literal["ODbL-1.0; IGN contents under Licence Ouverte 2.0"]
    no_endorsement: Literal["No IGN or OpenStreetMap endorsement; no warranty"]


class IGNPublicationBasis(StrictModel):
    schema_version: Literal[1] = 1
    upstream_product: Literal["IGN-RGE-ALTI-5M"] = "IGN-RGE-ALTI-5M"
    private_manifest: RegionalManifest
    derivation: IGNDerivation
    graph_build_record_sha256: Sha256
    legal_evidence: IGNLegalEvidence
    notices: IGNNotices
    output_vertical_crs: Literal["EPSG:5720"] = "EPSG:5720"

    @model_validator(mode="after")
    def exact_private_identity(self) -> Self:
        if (
            self.private_manifest.publication_allowed
            or len(self.private_manifest.components.elevation.files[1:]) != 4
            or self.notices.source_editions
            != tuple(p.filename for p in self.derivation.sources.files)
        ):
            raise ValueError(
                "IGN publication requires private four-tile source identity"
            )
        return self


class IGNPublicationEvidence(StrictModel):
    schema_version: Literal[2] = 2
    upstream_product: Literal["IGN-RGE-ALTI-5M"] = "IGN-RGE-ALTI-5M"
    private_build_id: Sha256
    release_build_id: Sha256
    graph_sha256: Sha256
    derived_tiles: tuple[FileDescriptor, ...]
    basis: IGNPublicationBasis

    @property
    def basis_sha256(self) -> str:
        return digest(canonical_json(self.basis.model_dump(mode="json")))

    @model_validator(mode="after")
    def exact_basis(self) -> Self:
        private = self.basis.private_manifest
        if (
            self.private_build_id != private.build_id
            or self.graph_sha256 != private.components.routing.files[1].sha256
            or self.derived_tiles != private.components.elevation.files[1:]
        ):
            raise ValueError("IGN evidence differs from exact private components")
        return self


def verify_ign_records(
    evidence: IGNPublicationEvidence,
    directory: Path,
    originals: Path,
    prepared: Path,
    transformation: Path,
    graph_record: Path,
    legal_directory: Path,
    osm_pbf: Path,
) -> None:
    """Independently rehash retained bytes. No download, rebuild or approval."""
    from sugarglider.offline_regions.elevation_hgt_probe import sha256_file
    from sugarglider.offline_regions.validation import verify_region

    basis = evidence.basis
    private = verify_region(directory)
    elevation = ElevationManifest.model_validate_json(
        bounded_record(directory / "elevation/manifest.json", 65_536)
    )
    if private != basis.private_manifest or elevation.derivation != basis.derivation:
        raise ValueError("IGN private build/derivation identity mismatch")
    for pin in basis.derivation.sources.files:
        verify_source(originals, pin)
    prepared_bytes = bounded_record(prepared / "prepared.json", 16 * 1024**2)
    if digest(prepared_bytes) != basis.derivation.prepared_sha256:
        raise ValueError("IGN preparation record mismatch")
    index = PreparedIGN.model_validate_json(prepared_bytes)
    if index.sources != basis.derivation.sources:
        raise ValueError("IGN preparation source mismatch")
    allowed = {p.sha256 for p in index.sources.files}
    if (
        len({g.path for g in index.grids}) != len(index.grids)
        or {g.source_archive_sha256 for g in index.grids} != allowed
    ):
        raise ValueError("duplicate IGN prepared grid")
    for grid in index.grids:
        if (
            grid.source_archive_sha256 not in allowed
            or sha256_file(contained_path(prepared, grid.path)) != grid.sha256
        ):
            raise ValueError("IGN prepared grid identity mismatch")
        # Preparation preserves the decoded originals beside lossless rasters.
        if (
            sha256_file(
                contained_path(prepared, str(Path(grid.path).with_suffix(".asc")))
            )
            != grid.original_ascii_sha256
        ):
            raise ValueError("IGN decoded source identity mismatch")
    transformed_bytes = bounded_record(transformation)
    if digest(transformed_bytes) != basis.derivation.transformation_sha256:
        raise ValueError("IGN transformation record mismatch")
    converted = json.loads(transformed_bytes)
    expected = [
        {
            "path": f.path.removeprefix("elevation/skadi/"),
            "sha256": f.sha256,
            "byte_size": f.byte_size,
        }
        for f in evidence.derived_tiles
    ]
    if (
        converted.get("algorithm") != basis.derivation.algorithm
        or converted.get("sources") != basis.derivation.sources.model_dump(mode="json")
        or converted.get("prepared_sha256") != basis.derivation.prepared_sha256
        or converted.get("input_vertical_crs") != "EPSG:5720"
        or converted.get("output_vertical_crs") != "EPSG:5720"
        or converted.get("vertical_operation")
        != "identity; IGN69 normal heights retained"
        or converted.get("interpolation")
        != "bilinear point nodes; all positive-weight nodes required"
        or converted.get("rounding") != "nearest integer ties to even; <=0.5 m"
        or converted.get("nodata") != -32768
        or [
            {k: t.get(k) for k in ("path", "sha256", "byte_size")}
            for t in converted.get("tiles", [])
        ]
        != expected
    ):
        raise ValueError("IGN conversion/datum/HGT identity mismatch")
    graph_bytes = bounded_record(graph_record)
    if digest(graph_bytes) != basis.graph_build_record_sha256:
        raise ValueError("IGN graph build record mismatch")
    built = json.loads(graph_bytes)
    if (
        built.get("private_build_id") != private.build_id
        or built.get("graph_sha256") != evidence.graph_sha256
        or built.get("source_pbf_sha256") != private.source.sha256
        or built.get("valhalla_image") != private.tools.valhalla_image
        or built.get("enrichment")
        != "valhalla_build_tiles; additional_data.elevation; network=none"
        or built.get("dem_tiles")
        != [f.model_dump(mode="json") for f in evidence.derived_tiles]
        or osm_pbf.is_symlink()
        or osm_pbf.stat().st_size != private.source.byte_size
        or sha256_file(osm_pbf) != private.source.sha256
    ):
        raise ValueError("IGN OSM/DEM-enriched graph binding mismatch")
    for document in basis.legal_evidence.documents:
        value = bounded_record(
            contained_path(legal_directory, document.path), 8 * 1024**2
        )
        if len(value) != document.byte_size or digest(value) != document.sha256:
            raise ValueError("IGN legal document identity mismatch")


def prepare_ign_request(
    directory: Path,
    originals: Path,
    prepared: Path,
    transformation: Path,
    graph_record: Path,
    legal_directory: Path,
    legal_evidence: IGNLegalEvidence,
    notices: IGNNotices,
    osm_pbf: Path,
) -> IGNPublicationEvidence:
    """Return unsigned facts; leave every private byte and publication flag intact."""
    from sugarglider.offline_regions.publication import release_manifests
    from sugarglider.offline_regions.validation import verify_region

    private = verify_region(directory)
    elevation = ElevationManifest.model_validate_json(
        bounded_record(directory / "elevation/manifest.json", 65_536)
    )
    if elevation.vertical_datum != "IGN69" or elevation.derivation is None:
        raise ValueError("expected documented IGN69 derivation")
    basis = IGNPublicationBasis(
        private_manifest=private,
        derivation=elevation.derivation,
        graph_build_record_sha256=digest(bounded_record(graph_record)),
        legal_evidence=legal_evidence,
        notices=notices,
    )
    proposed, _ = release_manifests(
        directory,
        private,
        ign_basis_sha256=digest(canonical_json(basis.model_dump(mode="json"))),
    )
    evidence = IGNPublicationEvidence(
        private_build_id=private.build_id,
        release_build_id=proposed.build_id,
        graph_sha256=private.components.routing.files[1].sha256,
        derived_tiles=private.components.elevation.files[1:],
        basis=basis,
    )
    verify_ign_records(
        evidence,
        directory,
        originals,
        prepared,
        transformation,
        graph_record,
        legal_directory,
        osm_pbf,
    )
    return evidence


def authorize_ign_manifest(
    manifest: RegionalManifest, evidence: IGNPublicationEvidence
) -> None:
    """Validate the complete proposed identity after detached approval verification."""
    private = evidence.basis.private_manifest
    if (
        not manifest.publication_allowed
        or manifest.build_id != evidence.release_build_id
    ):
        raise ValueError("IGN release authorization does not match build")
    old = private.model_dump(mode="json", exclude={"publication_allowed", "build_id"})
    new = manifest.model_dump(mode="json", exclude={"publication_allowed", "build_id"})
    # Only the elevation metadata descriptor may change for the approved copy.
    old["components"]["elevation"]["files"][0] = new["components"]["elevation"][
        "files"
    ][0]
    if old != new:
        raise ValueError("IGN release differs from approved five-component basis")


def ign_notice(evidence: IGNPublicationEvidence) -> str:
    notices = evidence.basis.notices
    return "\n".join(
        (
            IGN_ATTRIBUTION,
            notices.osm,
            notices.heights,
            notices.modifications,
            "IGN source editions (not per-cell acquisition dates): "
            + ", ".join(notices.source_editions),
            "Licence Ouverte 2.0: " + LEGAL_URLS["open-licence"],
            "ODbL 1.0: " + LEGAL_URLS["odbl"],
            "Free machine-readable offer: all complete derived databases are the "
            "regional components at the immutable manifest paths.",
            notices.database_terms,
            notices.no_endorsement,
        )
    )
