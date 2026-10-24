"""Detached, exact-build publication authorization. Never grants legal approval.

The trusted approval digest must be supplied independently by the release operator.
An approval found beside an artifact is not trusted automatically. Read-only facts,
an unsigned request and an approved release copy are three separate operations.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, TypeAdapter, model_validator

from sugarglider.offline_regions.elevation_component import ElevationManifest
from sugarglider.offline_regions.ign_publication import (
    IGNCompletePublicationBasis,
    IGNPublicationEvidence,
    authorize_ign_manifest,
    verify_ign_records,
)
from sugarglider.offline_regions.models import (
    FileDescriptor,
    RegionalManifest,
    Sha256,
    StrictModel,
    build_identity,
    canonical_json,
)
from sugarglider.offline_regions.publication_records import (
    bounded_record as bounded_record,
)
from sugarglider.offline_regions.publication_records import (
    digest as digest,
)
from sugarglider.offline_regions.terrain_source import (
    COPERNICUS_ATTRIBUTION,
    COPERNICUS_DISCLAIMER,
    TerrainSources,
    verify_source,
)
from sugarglider.offline_regions.validation import verify_region


class PublicationEvidence(StrictModel):
    upstream_product: Literal["COP-DEM_GLO-30-DGED"] = "COP-DEM_GLO-30-DGED"
    license_document_sha256: Literal[
        "9cd37d37ea654bbcaf0a2e059e6a3a5b5f76072824d8dd860ccf274ada8951bd"
    ] = "9cd37d37ea654bbcaf0a2e059e6a3a5b5f76072824d8dd860ccf274ada8951bd"
    schema_version: Literal[1] = 1
    private_build_id: Sha256
    release_build_id: Sha256
    graph_sha256: Sha256
    transformation_sha256: Sha256
    graph_build_record_sha256: Sha256
    sources: TerrainSources
    derived_tiles: tuple[FileDescriptor, ...]
    transformation: Literal["cop-dem-cog-egm96-v1"]
    output_vertical_crs: Literal["EPSG:5773"]
    geoid_license: Literal["US-NGA-Public-Domain"]
    geoid_license_evidence: Literal[
        "https://github.com/OSGeo/PROJ-data/blob/master/us_nga/us_nga_README.txt"
    ]
    attribution: Annotated[str, Field(min_length=1, max_length=2048)]
    disclaimer: Annotated[str, Field(min_length=1, max_length=2048)]
    obligations: Literal[
        "COPDEM-30-articles-4-6-7-9; ODbL-1.0; no-endorsement; subsequent-users"
    ]


type ReleaseEvidence = PublicationEvidence | IGNPublicationEvidence


def parse_publication_evidence(value: bytes) -> ReleaseEvidence:
    from sugarglider.offline_regions.publication_records import unique_object

    if not 0 < len(value) <= 32_768:
        raise ValueError("publication evidence exceeds limit")
    json.loads(value, object_pairs_hook=unique_object)
    return TypeAdapter(ReleaseEvidence).validate_json(value)


class OperatorApproval(StrictModel):
    schema_version: Literal[1] = 1
    decision: Literal["approve-publication"]
    operator: Annotated[str, Field(min_length=1, max_length=120)]
    approved_at: Annotated[str, Field(min_length=20, max_length=40)]
    evidence_sha256: Sha256
    release_build_id: Sha256
    scope: Literal["exact-regional-build-and-derived-DEM-enriched-graph"]
    license_terms_accepted: StrictBool

    @model_validator(mode="after")
    def explicit_human_acceptance(self) -> Self:
        if not self.license_terms_accepted or self.operator.strip() != self.operator:
            raise ValueError("operator must explicitly accept the reviewed terms")
        if any(ord(c) < 32 or ord(c) == 127 for c in self.operator):
            raise ValueError("invalid operator identity")
        timestamp = datetime.fromisoformat(self.approved_at)
        if timestamp.tzinfo is None:
            raise ValueError("approval timestamp must include its timezone")
        return self


def release_manifests(
    directory: Path, private: RegionalManifest, *, ign_basis_sha256: str | None = None
) -> tuple[RegionalManifest, bytes]:
    """Read-only preview; the operator reviews this exact proposed build ID."""
    if private.publication_allowed:
        raise ValueError("expected a private research build")
    elevation = ElevationManifest.model_validate_json(
        (directory / "elevation/manifest.json").read_bytes()
    )
    ign = elevation.vertical_datum == "IGN69" and ign_basis_sha256 is not None
    if not ign and (elevation.provenance_status, elevation.vertical_datum) != (
        "documented",
        "EGM96",
    ):
        raise ValueError("source provenance/vertical datum remain unresolved")
    if not ign and ign_basis_sha256 is not None:
        raise ValueError("IGN authorization cannot label another source")
    elevation_payload = elevation.model_dump(mode="json")
    elevation_payload["publication_allowed"] = True
    if ign:
        elevation_payload["publication_basis_sha256"] = ign_basis_sha256
    elevation_bytes = canonical_json(
        ElevationManifest.model_validate_json(
            canonical_json(elevation_payload)
        ).model_dump(mode="json")
    )
    payload = private.model_dump(mode="json", exclude={"build_id"})
    payload["publication_allowed"] = True
    file = payload["components"]["elevation"]["files"][0]
    file["byte_size"], file["sha256"] = len(elevation_bytes), digest(elevation_bytes)
    payload["build_id"] = build_identity(payload)
    return RegionalManifest.model_validate_json(
        canonical_json(payload)
    ), elevation_bytes


def verify_evidence(
    evidence: PublicationEvidence,
    private: RegionalManifest,
    proposed: RegionalManifest,
    originals: Path,
    transformation_record: Path,
    graph_build_record: Path,
) -> None:
    if (
        evidence.private_build_id != private.build_id
        or evidence.release_build_id != proposed.build_id
        or evidence.graph_sha256 != private.components.routing.files[1].sha256
        or evidence.derived_tiles != private.components.elevation.files[1:]
        or evidence.attribution != COPERNICUS_ATTRIBUTION
        or evidence.disclaimer != COPERNICUS_DISCLAIMER
        or evidence.transformation_sha256
        != digest(bounded_record(transformation_record))
        or evidence.graph_build_record_sha256
        != digest(bounded_record(graph_build_record))
    ):
        raise ValueError("publication evidence does not match exact source/build")
    for pin in evidence.sources.files:
        verify_source(originals, pin)

    from sugarglider.offline_regions.terrain_conversion import geoid_pipeline

    if (
        transformation_record.stat().st_size > 32_768
        or graph_build_record.stat().st_size > 32_768
    ):
        raise ValueError("oversized terrain verification record")
    transformed = json.loads(bounded_record(transformation_record))
    built = json.loads(bounded_record(graph_build_record))
    expected_tiles = [
        {
            "path": f.path.removeprefix("elevation/skadi/"),
            "sha256": f.sha256,
            "byte_size": f.byte_size,
        }
        for f in evidence.derived_tiles
    ]
    actual_tiles = [
        {key: tile[key] for key in ("path", "sha256", "byte_size")}
        for tile in transformed.get("tiles", [])
    ]
    if (
        transformed.get("sources") != evidence.sources.model_dump(mode="json")
        or transformed.get("algorithm") != evidence.transformation
        or transformed.get("output_vertical_crs") != evidence.output_vertical_crs
        or transformed.get("input_vertical_crs") != evidence.sources.vertical_crs
        or transformed.get("pipeline") != geoid_pipeline(originals)
        or actual_tiles != expected_tiles
        or built.get("graph_sha256") != evidence.graph_sha256
        or built.get("source_pbf_sha256") != private.source.sha256
        or built.get("valhalla_image") != private.tools.valhalla_image
        or built.get("enrichment")
        != "valhalla_build_tiles; additional_data.elevation; network=none"
        or built.get("dem_tiles")
        != [f.model_dump(mode="json") for f in evidence.derived_tiles]
    ):
        raise ValueError("source/transformation/DEM-enriched graph binding mismatch")


def verify_approval(
    evidence: ReleaseEvidence, approval_bytes: bytes, trusted_approval_sha256: str
) -> OperatorApproval:
    if digest(approval_bytes) != trusted_approval_sha256:
        raise ValueError("operator approval is not independently authorized")
    if isinstance(evidence, IGNPublicationEvidence) and isinstance(
        evidence.basis, IGNCompletePublicationBasis
    ):
        from sugarglider.offline_regions.source_notices import require_notice_review

        require_notice_review(evidence.basis.supplementary_notices)
    approval = OperatorApproval.model_validate_json(approval_bytes)
    if (
        approval.evidence_sha256
        != digest(canonical_json(evidence.model_dump(mode="json")))
        or approval.release_build_id != evidence.release_build_id
    ):
        raise ValueError("operator approval does not match evidence/build")
    return approval


def prepare_approved_region(
    private_directory: Path,
    output: Path,
    evidence: ReleaseEvidence,
    originals: Path,
    transformation_record: Path,
    graph_build_record: Path,
    *,
    approval_bytes: bytes,
    trusted_approval_sha256: str,
    prepared: Path | None = None,
    legal_directory: Path | None = None,
    osm_pbf: Path | None = None,
) -> RegionalManifest:
    private = verify_region(private_directory)
    proposed, elevation_bytes = release_manifests(
        private_directory,
        private,
        ign_basis_sha256=evidence.basis_sha256
        if isinstance(evidence, IGNPublicationEvidence)
        else None,
    )
    if isinstance(evidence, IGNPublicationEvidence):
        if prepared is None or legal_directory is None or osm_pbf is None:
            raise ValueError(
                "IGN approval requires preparation, legal evidence and OSM bytes"
            )
        verify_ign_records(
            evidence,
            private_directory,
            originals,
            prepared,
            transformation_record,
            graph_build_record,
            legal_directory,
            osm_pbf,
        )
        authorize_ign_manifest(proposed, evidence)
    else:
        verify_evidence(
            evidence,
            private,
            proposed,
            originals,
            transformation_record,
            graph_build_record,
        )
    verify_approval(evidence, approval_bytes, trusted_approval_sha256)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if output.resolve() != output.absolute() or output.absolute().is_relative_to(
        private_directory.absolute()
    ):
        raise ValueError("approved copy must be outside the immutable private region")
    output.mkdir()
    try:
        shutil.copytree(private_directory, output, dirs_exist_ok=True)
        (output / "elevation/manifest.json").write_bytes(elevation_bytes)
        (output / "manifest.json").write_bytes(
            canonical_json(proposed.model_dump(mode="json"))
        )
        if verify_region(output) != proposed:
            raise ValueError("approved copy failed verification")
    except BaseException:
        shutil.rmtree(output)
        raise
    return proposed


def authorize_release_manifest(
    manifest: RegionalManifest,
    evidence: ReleaseEvidence,
    approval_bytes: bytes,
    trusted_approval_sha256: str,
    *,
    elevation: ElevationManifest | None = None,
) -> None:
    verify_approval(evidence, approval_bytes, trusted_approval_sha256)
    if isinstance(evidence, IGNPublicationEvidence):
        if (
            elevation is None
            or elevation.vertical_datum != "IGN69"
            or elevation.derivation != evidence.basis.derivation
            or elevation.publication_basis_sha256 != evidence.basis_sha256
            or not elevation.publication_allowed
        ):
            raise ValueError(
                "IGN release metadata does not match source-specific basis"
            )
        authorize_ign_manifest(manifest, evidence)
        return
    if elevation is not None and elevation.vertical_datum != "EGM96":
        raise ValueError("Copernicus approval cannot authorize another terrain source")
    if (
        not manifest.publication_allowed
        or manifest.build_id != evidence.release_build_id
        or manifest.components.routing.files[1].sha256 != evidence.graph_sha256
        or manifest.components.elevation.files[1:] != evidence.derived_tiles
        or evidence.attribution != COPERNICUS_ATTRIBUTION
        or evidence.disclaimer != COPERNICUS_DISCLAIMER
    ):
        raise ValueError("release authorization does not match regional bytes")


def prepare_publication_request(
    private_directory: Path,
    documented_output: Path,
    sources: TerrainSources,
    originals: Path,
    transformation_record: Path,
    graph_build_record: Path,
) -> PublicationEvidence:
    """Verify facts and create a fresh PRIVATE documented copy, without approval.

    The request is portable evidence; the transformation's local paths remain in
    the private original record. Existing research bytes are never edited.
    """
    private = verify_region(private_directory)
    if private.publication_allowed:
        raise ValueError("expected private build")
    elevation = ElevationManifest.model_validate_json(
        (private_directory / "elevation/manifest.json").read_bytes()
    )
    if elevation.derivation is not None or elevation.vertical_datum == "IGN69":
        raise ValueError("IGN69 requires the source-specific IGN request path")
    documented = ElevationManifest.model_validate_json(
        canonical_json(
            elevation.model_copy(
                update={"provenance_status": "documented", "vertical_datum": "EGM96"}
            ).model_dump(mode="json")
        )
    )
    elevation_bytes = canonical_json(documented.model_dump(mode="json"))
    payload = private.model_dump(mode="json", exclude={"build_id"})
    descriptor = payload["components"]["elevation"]["files"][0]
    descriptor["byte_size"], descriptor["sha256"] = (
        len(elevation_bytes),
        digest(elevation_bytes),
    )
    payload["build_id"] = build_identity(payload)
    captured = RegionalManifest.model_validate_json(canonical_json(payload))
    # Compute the proposed public identity entirely in memory; no public artifact
    # is created until an independently authorized exact-build approval exists.
    proposed_elevation = canonical_json(
        documented.model_copy(update={"publication_allowed": True}).model_dump(
            mode="json"
        )
    )
    proposed_payload = captured.model_dump(mode="json", exclude={"build_id"})
    proposed_payload["publication_allowed"] = True
    entry = proposed_payload["components"]["elevation"]["files"][0]
    entry["byte_size"], entry["sha256"] = (
        len(proposed_elevation),
        digest(proposed_elevation),
    )
    proposed_payload["build_id"] = build_identity(proposed_payload)
    proposed = RegionalManifest.model_validate_json(canonical_json(proposed_payload))
    evidence = PublicationEvidence(
        private_build_id=captured.build_id,
        release_build_id=proposed.build_id,
        graph_sha256=captured.components.routing.files[1].sha256,
        transformation_sha256=digest(bounded_record(transformation_record)),
        graph_build_record_sha256=digest(bounded_record(graph_build_record)),
        sources=sources,
        derived_tiles=captured.components.elevation.files[1:],
        transformation="cop-dem-cog-egm96-v1",
        output_vertical_crs="EPSG:5773",
        geoid_license="US-NGA-Public-Domain",
        geoid_license_evidence="https://github.com/OSGeo/PROJ-data/blob/master/us_nga/us_nga_README.txt",
        attribution=COPERNICUS_ATTRIBUTION,
        disclaimer=COPERNICUS_DISCLAIMER,
        obligations=(
            "COPDEM-30-articles-4-6-7-9; ODbL-1.0; no-endorsement; subsequent-users"
        ),
    )
    verify_evidence(
        evidence,
        captured,
        proposed,
        originals,
        transformation_record,
        graph_build_record,
    )
    if documented_output.exists() or documented_output.is_symlink():
        raise FileExistsError(documented_output)
    shutil.copytree(private_directory, documented_output)
    (documented_output / "elevation/manifest.json").write_bytes(elevation_bytes)
    (documented_output / "manifest.json").write_bytes(
        canonical_json(captured.model_dump(mode="json"))
    )
    if verify_region(documented_output) != captured:
        raise ValueError("documented private copy failed verification")
    return evidence
