"""Closed notice identities and complete publication gates, synthetic authority only."""

import html
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_pr101_ign_publication import (
    BASE,
    ApprovalArguments,
    IGNFixture,
    build_synthetic_ign,
    synthetic_approval,
)

from sugarglider.offline_regions import source_notices
from sugarglider.offline_regions.distribution import prepare_distribution
from sugarglider.offline_regions.ign_publication import (
    IGNCompletePublicationBasis,
    IGNPublicationEvidence,
    prepare_ign_request,
)
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import (
    digest,
    parse_publication_evidence,
    verify_approval,
)
from sugarglider.offline_regions.release_catalog import preflight_catalog
from sugarglider.offline_regions.source_notices import (
    NOTICE_FILE,
    NoticeLink,
    SupplementaryNotices,
    notice_registry,
    notice_text,
    propose_supplementary_notices,
    render_browser_registry,
)
from sugarglider.offline_regions.unpack_distribution import unpack_distribution
from sugarglider.offline_regions.validation import verify_region

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> IGNFixture:
    fixture = build_synthetic_ign(tmp_path)
    # Only this test's in-memory registry recognizes tiny synthetic map bytes.
    # No production switch, alternate trust file or real approval is introduced.
    registry = notice_registry().model_copy(
        update={
            "map_payload": fixture.evidence.basis.private_manifest.components.map.files[
                1
            ]
        }
    )
    monkeypatch.setattr(source_notices, "notice_registry", lambda: registry)
    notices = propose_supplementary_notices().model_copy(
        update={"lineage_review": "accept-documented-lineage-limit"}
    )
    evidence = prepare_ign_request(
        fixture.region,
        fixture.originals,
        fixture.prepared,
        fixture.conversion,
        fixture.graph,
        fixture.legal,
        fixture.evidence.basis.legal_evidence,
        fixture.evidence.basis.notices,
        fixture.pbf,
        supplementary_notices=notices,
    )
    return replace(fixture, evidence=evidence)


def authority(fixture: IGNFixture, directory: Path) -> ApprovalArguments:
    evidence, approval = directory / "evidence.json", directory / "approval.json"
    evidence.write_bytes(canonical_json(fixture.evidence.model_dump(mode="json")))
    value = synthetic_approval(fixture.evidence)
    approval.write_bytes(value)
    return dict(
        evidence_path=evidence,
        approval_path=approval,
        trusted_approval_sha256=digest(value),
    )


def test_shared_offline_registry_and_real_unknown_map_gate(tmp_path: Path) -> None:
    from sugarglider.offline_regions import unpack_distribution as unpacker

    assert unpacker.NOTICE_FILE == NOTICE_FILE
    assert unpacker.NOTICE_LIMIT == source_notices.NOTICE_LIMIT
    assert (
        ROOT / "src/sugarglider/web/static/data_notice_registry.js"
    ).read_text() == render_browser_registry()
    proposed = propose_supplementary_notices()
    assert proposed.lineage_review == "pending"
    assert proposed.notice_text_sha256 == digest(notice_text())
    assert b"2020 v100 or 2021 v200 as a verified edition" in notice_text()
    fixture = build_synthetic_ign(tmp_path)
    with pytest.raises(ValueError, match="map payload"):
        IGNCompletePublicationBasis(
            **fixture.evidence.basis.model_dump(exclude={"schema_version"}),
            supplementary_notices=proposed,
        )


def test_existing_packaged_runtime_notices_remain_exact() -> None:
    source = notice_registry()
    paths = {
        "maplibre-runtime": "vendor/maplibre-gl-6.4.1/LICENSE.txt",
        "pmtiles-runtime": "vendor/pmtiles-4.5.0/LICENSE.txt",
        "protomaps-runtime": "vendor/protomaps-basemaps-5.7.2/LICENSE.md",
        "noble-runtime": "vendor/noble-hashes-2.4.0/LICENSE",
        "open-sans": "fonts/Open Sans Semibold/LICENSE.txt",
    }
    for role, path in paths.items():
        document = next(d for d in source.documents if d.role == role)
        assert document.text == (ROOT / "src/sugarglider/web/static" / path).read_text()


def test_v3_exact_binding_is_deterministic_and_private_payloads_unchanged(
    complete: IGNFixture, tmp_path: Path
) -> None:
    fixture = complete
    assert isinstance(fixture.evidence.basis, IGNCompletePublicationBasis)
    wire = canonical_json(fixture.evidence.model_dump(mode="json"))
    assert len(wire) < 32_768
    assert parse_publication_evidence(wire) == fixture.evidence
    assert (
        fixture.evidence.schema_version == 3
        and fixture.evidence.basis.schema_version == 2
    )
    second = prepare_ign_request(
        fixture.region,
        fixture.originals,
        fixture.prepared,
        fixture.conversion,
        fixture.graph,
        fixture.legal,
        fixture.evidence.basis.legal_evidence,
        fixture.evidence.basis.notices,
        fixture.pbf,
        supplementary_notices=fixture.evidence.basis.supplementary_notices,
    )
    assert second == fixture.evidence
    before = {
        p.relative_to(fixture.region): p.read_bytes()
        for p in fixture.region.rglob("*")
        if p.is_file()
    }
    approved = fixture.approve(tmp_path / "approved")
    after = {
        p.relative_to(fixture.region): p.read_bytes()
        for p in fixture.region.rglob("*")
        if p.is_file()
    }
    assert before == after
    for name, value in before.items():
        if name.as_posix() not in {"manifest.json", "elevation/manifest.json"}:
            assert (approved / name).read_bytes() == value
    assert verify_region(approved).build_id == fixture.evidence.release_build_id
    kwargs = authority(fixture, tmp_path)
    output = prepare_distribution(
        approved,
        tmp_path / "distribution",
        base_url=BASE,
        description="<script>synthetic & escaped</script>",
        **kwargs,
    )
    assert (output / "site" / NOTICE_FILE).read_bytes() == notice_text()
    assert (
        html.escape("<script>synthetic & escaped</script>")
        in (output / "site/index.html").read_text()
    )
    assert "<script>" not in (output / "site/index.html").read_text()
    preflight_catalog(
        output / "site/catalog.json", output / "site", base_url=BASE, **kwargs
    )
    archive = output / "sugarglider-regions-static.zip"
    unpack_distribution(
        archive,
        tmp_path / "unpacked",
        digest(archive.read_bytes()),
        publication=True,
        **kwargs,
    )
    for component in fixture.evidence.basis.private_manifest.components.ordered:
        for file in component.files:
            assert (
                f'href="regions/{fixture.evidence.basis.private_manifest.region_id}/{fixture.evidence.release_build_id}/{file.path}"'
                in (output / "site/index.html").read_text()
            )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "unknown-source",
        "duplicate-source",
        "registry-hash",
        "notice-hash",
        "document-hash",
        "document-size",
        "document-missing",
        "document-duplicate",
        "map-version",
        "html",
        "url",
        "oversized",
        "schema",
    ],
)
def test_missing_or_changed_notices_fail_closed(change: str) -> None:
    value: dict[str, Any] = propose_supplementary_notices().model_dump(mode="json")
    if change == "missing":
        del value["notice_text_sha256"]
    elif change == "unknown-source":
        value["source_ids"][0] = "unknown-provider"
    elif change == "duplicate-source":
        value["source_ids"][0] = value["source_ids"][1]
    elif change == "registry-hash":
        value["registry_sha256"] = "0" * 64
    elif change == "notice-hash":
        value["notice_text_sha256"] = "0" * 64
    elif change == "document-hash":
        value["documents"][0]["sha256"] = "0" * 64
    elif change == "document-size":
        value["documents"][0]["byte_size"] += 1
    elif change == "document-missing":
        value["documents"].pop()
    elif change == "document-duplicate":
        value["documents"][0] = value["documents"][1]
    elif change == "map-version":
        value["map_payload"]["sha256"] = "0" * 64
    elif change == "html":
        value["source_ids"][0] = "<img src=x onerror=alert(1)>"
    elif change == "url":
        value["url"] = "javascript:alert(1)"
    elif change == "oversized":
        value["source_ids"][0] = "x" * 4097
    elif change == "schema":
        value["schema_version"] = True
    with pytest.raises(ValueError):
        SupplementaryNotices.model_validate_json(canonical_json(value))


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://user:password@esa-worldcover.org/",
        "https://esa-worldcover.org/?token=x",
        "https://esa-worldcover.org/#x",
        "https://esa-worldcover.org/\n",
        "http://esa-worldcover.org/",
    ],
)
def test_notice_link_validation(url: str) -> None:
    with pytest.raises(ValueError):
        NoticeLink(label="source", url=url)


@pytest.mark.parametrize(
    "target",
    [
        "old-version",
        "missing-supplement",
        "unknown-field",
        "new-basis-old-version",
        "old-basis-new-version",
        "duplicate-json",
    ],
)
def test_explicit_versions_and_duplicate_fields(
    complete: IGNFixture, target: str
) -> None:
    value: dict[str, Any] = complete.evidence.model_dump(mode="json")
    if target == "old-version":
        value["schema_version"] = 2
    elif target == "missing-supplement":
        del value["basis"]["supplementary_notices"]
    elif target == "unknown-field":
        value["basis"]["supplementary_notices"]["approval"] = True
    elif target == "new-basis-old-version":
        value["basis"]["schema_version"] = 1
    elif target == "old-basis-new-version":
        del value["basis"]["supplementary_notices"]
        value["basis"]["schema_version"] = 1
    wire = canonical_json(value)
    if target == "duplicate-json":
        wire = wire.replace(
            b'"schema_version":3', b'"schema_version":2,"schema_version":3', 1
        )
    with pytest.raises(ValueError):
        parse_publication_evidence(wire)


def test_old_approval_wrong_pin_and_pending_lineage_fail(
    complete: IGNFixture, tmp_path: Path
) -> None:
    assert isinstance(complete.evidence.basis, IGNCompletePublicationBasis)
    core = prepare_ign_request(
        complete.region,
        complete.originals,
        complete.prepared,
        complete.conversion,
        complete.graph,
        complete.legal,
        complete.evidence.basis.legal_evidence,
        complete.evidence.basis.notices,
        complete.pbf,
    )
    assert core.release_build_id != complete.evidence.release_build_id
    old_approval = synthetic_approval(core)
    with pytest.raises(ValueError, match="evidence/build"):
        verify_approval(complete.evidence, old_approval, digest(old_approval))
    approval = synthetic_approval(complete.evidence)
    with pytest.raises(ValueError, match="independently"):
        verify_approval(complete.evidence, approval, "0" * 64)
    value = complete.evidence.model_dump(mode="json")
    value["basis"]["supplementary_notices"]["lineage_review"] = "pending"
    pending = IGNPublicationEvidence.model_validate_json(canonical_json(value))
    approval = synthetic_approval(pending)
    with pytest.raises(ValueError, match="publisher lineage review"):
        verify_approval(pending, approval, digest(approval))
    with pytest.raises(ValueError):
        replace(complete, evidence=pending).approve(tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()


@pytest.mark.parametrize(
    "part",
    [
        "SOURCE_NOTICES.txt",
        "README.txt",
        "index.html",
        "missing",
        "oversized",
        "shadow-path",
    ],
)
def test_packaged_and_catalog_notice_integrity(
    complete: IGNFixture, tmp_path: Path, part: str
) -> None:
    approved = complete.approve(tmp_path / "approved")
    kwargs = authority(complete, tmp_path)
    output = prepare_distribution(
        approved,
        tmp_path / "distribution",
        base_url=BASE,
        description="SYNTHETIC TEST ONLY",
        **kwargs,
    )
    path = (
        output
        / "site"
        / (
            part
            if part in {"SOURCE_NOTICES.txt", "README.txt", "index.html"}
            else NOTICE_FILE
        )
    )
    if part == "missing":
        path.unlink()
    elif part == "oversized":
        path.write_bytes(b"x" * 131_073)
    else:
        path.write_bytes(path.read_bytes() + b"\nUNAPPROVED replacement notice")
    with pytest.raises((ValueError, OSError)):
        preflight_catalog(
            output / "site/catalog.json", output / "site", base_url=BASE, **kwargs
        )
    archive = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(output / "sugarglider-regions-static.zip") as original,
        zipfile.ZipFile(archive, "w") as changed,
    ):
        for member in original.infolist():
            if part == "missing" and member.filename == NOTICE_FILE:
                continue
            payload = original.read(member)
            if member.filename == path.name and part != "shadow-path":
                payload = path.read_bytes()
            changed.writestr(member, payload)
        if part == "shadow-path":
            entry = zipfile.ZipInfo("notices/SOURCE_NOTICES.txt")
            entry.external_attr = 0o100644 << 16
            changed.writestr(entry, notice_text())
    with pytest.raises((ValueError, OSError)):
        unpack_distribution(
            archive,
            tmp_path / "forbidden",
            digest(archive.read_bytes()),
            publication=True,
            **kwargs,
        )
    assert not (tmp_path / "forbidden").exists()


def test_registry_revision_changes_notice_and_approval_basis(
    complete: IGNFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = source_notices.notice_registry()
    previous = propose_supplementary_notices()
    section = source.sections[1].model_copy(
        update={
            "paragraphs": (
                *source.sections[1].paragraphs,
                "New reviewed edition would require new evidence.",
            )
        }
    )
    modified = source.model_copy(
        update={"sections": (source.sections[0], section, *source.sections[2:])}
    )
    monkeypatch.setattr(source_notices, "notice_registry", lambda: modified)
    with pytest.raises(ValueError):
        SupplementaryNotices.model_validate_json(
            canonical_json(previous.model_dump(mode="json"))
        )
    next_proposal = propose_supplementary_notices()
    assert next_proposal.registry_sha256 != previous.registry_sha256
    assert next_proposal.notice_text_sha256 != previous.notice_text_sha256


@pytest.mark.parametrize("part", ["README.txt", "index.html", "SOURCE_NOTICES.txt"])
def test_legacy_approval_cannot_smuggle_expanded_hosted_notices(
    complete: IGNFixture, tmp_path: Path, part: str
) -> None:
    core = prepare_ign_request(
        complete.region,
        complete.originals,
        complete.prepared,
        complete.conversion,
        complete.graph,
        complete.legal,
        complete.evidence.basis.legal_evidence,
        complete.evidence.basis.notices,
        complete.pbf,
    )
    legacy = replace(complete, evidence=core)
    approved = legacy.approve(tmp_path / "approved")
    kwargs = authority(legacy, tmp_path)
    output = prepare_distribution(
        approved,
        tmp_path / "distribution",
        base_url=BASE,
        description="SYNTHETIC legacy evidence",
        **kwargs,
    )
    path = output / "site" / part
    original = path.read_bytes() if path.exists() else b""
    path.write_bytes(original + b"\nUnreviewed expanded licence claim")
    with pytest.raises((ValueError, OSError)):
        preflight_catalog(
            output / "site/catalog.json", output / "site", base_url=BASE, **kwargs
        )
    archive = tmp_path / "legacy-mutated.zip"
    with (
        zipfile.ZipFile(output / "sugarglider-regions-static.zip") as old,
        zipfile.ZipFile(archive, "w") as changed,
    ):
        for member in old.infolist():
            changed.writestr(
                member,
                path.read_bytes() if member.filename == part else old.read(member),
            )
        if part == NOTICE_FILE:
            member = zipfile.ZipInfo(NOTICE_FILE)
            member.external_attr = 0o100644 << 16
            changed.writestr(member, path.read_bytes())
    with pytest.raises(ValueError):
        unpack_distribution(
            archive,
            tmp_path / "forbidden",
            digest(archive.read_bytes()),
            publication=True,
            **kwargs,
        )
    assert not (tmp_path / "forbidden").exists()
