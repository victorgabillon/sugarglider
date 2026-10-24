"""Closed supplementary notice inventory; documentary facts, never legal approval.

The code-owned registry is shared with the offline shell. A new source, wording,
document or edition needs a reviewed registry revision and new exact evidence.
"""

import json
from importlib.resources import files
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from sugarglider.offline_regions.models import (
    FileDescriptor,
    RegionalManifest,
    RelativePath,
    Sha256,
    StrictModel,
    canonical_json,
)
from sugarglider.offline_regions.publication_records import digest

NOTICE_FILE = "SOURCE_NOTICES.txt"
NOTICE_LIMIT = 131_072
type ShortText = Annotated[str, Field(min_length=1, max_length=4096)]


class NoticeLink(StrictModel):
    label: ShortText
    url: Annotated[str, Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def canonical_https(self) -> Self:
        parsed = urlsplit(self.url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(ord(c) <= 32 or ord(c) == 127 for c in self.url)
            or "\\" in self.url
        ):
            raise ValueError("notice links require canonical credential-free HTTPS")
        return self


class NoticeSection(StrictModel):
    source_id: Annotated[str, Field(pattern=r"^[a-z][a-z-]{0,31}$")]
    title: ShortText
    paragraphs: Annotated[tuple[ShortText, ...], Field(min_length=1, max_length=8)]
    links: Annotated[tuple[NoticeLink, ...], Field(max_length=6)]


class NoticeDocument(StrictModel):
    role: Annotated[str, Field(pattern=r"^[a-z][a-z-]{0,31}$")]
    source_url: Annotated[str, Field(min_length=1, max_length=500)]
    licence: ShortText
    text: Annotated[str, Field(min_length=1, max_length=32_768)]


class SupportInput(StrictModel):
    path: RelativePath
    byte_size: Annotated[int, Field(gt=0, le=1_000_000_000)]
    sha256: Sha256
    format: Literal["retained-support-input", "build-statistics-only"]


class NoticeRegistry(StrictModel):
    schema_version: Literal[1]
    inventory_id: Literal["yvelines-v2-notices-2026-10-23"]
    lineage_status: Literal["supported-incomplete"]
    map_payload: FileDescriptor
    source_assets: Annotated[
        tuple[SupportInput, ...], Field(min_length=7, max_length=7)
    ]
    sections: Annotated[tuple[NoticeSection, ...], Field(min_length=9, max_length=9)]
    documents: Annotated[
        tuple[NoticeDocument, ...], Field(min_length=13, max_length=13)
    ]
    reading: Annotated[tuple[ShortText, ...], Field(min_length=6, max_length=6)]


def notice_registry() -> NoticeRegistry:
    """Read packaged source, never an artifact-supplied path or runtime URL."""
    value = (
        files("sugarglider.offline_regions")
        .joinpath("notice_registry.json")
        .read_bytes()
    )
    if len(value) > NOTICE_LIMIT:
        raise ValueError("oversized packaged notice registry")
    return NoticeRegistry.model_validate_json(value)


def registry_sha256(registry: NoticeRegistry) -> str:
    return digest(canonical_json(registry.model_dump(mode="json")))


def notice_text(registry: NoticeRegistry | None = None) -> bytes:
    source = registry or notice_registry()
    lines = [
        "Sugarglider supplementary regional source notices",
        f"Inventory: {source.inventory_id}",
        f"Canonical registry SHA-256: {registry_sha256(source)}",
        "Proposed layered notice specification; final wording and combined rights "
        "require publisher review.",
        "Source recognition and these notices grant no publication authority.",
        "Map payload: "
        + canonical_json(source.map_payload.model_dump(mode="json")).decode().strip(),
    ]
    for section in source.sections:
        lines.extend(("", section.title, *section.paragraphs))
        lines.extend(f"{link.label}: {link.url}" for link in section.links)
    lines.extend(
        ("", "Retained support-input identities (not historical consumption receipts)")
    )
    lines.extend(
        canonical_json(pin.model_dump(mode="json")).decode().strip()
        for pin in source.source_assets
    )
    lines.extend(
        (
            "",
            "Reading the complete machine-readable regional databases",
            *source.reading,
        )
    )
    for document in source.documents:
        lines.extend(
            (
                "",
                f"{document.role} — {document.licence}",
                document.source_url,
                document.text,
            )
        )
    value = ("\n\n".join(lines) + "\n").encode("utf-8")
    if len(value) > NOTICE_LIMIT:
        raise ValueError("oversized supplementary notice document")
    return value


class NoticeDocumentIdentity(StrictModel):
    role: Annotated[str, Field(pattern=r"^[a-z][a-z-]{0,31}$")]
    byte_size: Annotated[int, Field(gt=0, le=32_768)]
    sha256: Sha256


def document_identities(source: NoticeRegistry) -> tuple[NoticeDocumentIdentity, ...]:
    return tuple(
        NoticeDocumentIdentity(
            role=d.role,
            byte_size=len(d.text.encode("utf-8")),
            sha256=digest(d.text.encode("utf-8")),
        )
        for d in source.documents
    )


class SupplementaryNotices(StrictModel):
    schema_version: Literal[1] = 1
    inventory_id: Literal["yvelines-v2-notices-2026-10-23"]
    registry_sha256: Sha256
    notice_text_sha256: Sha256
    map_payload: FileDescriptor
    source_ids: Annotated[tuple[ShortText, ...], Field(min_length=9, max_length=9)]
    documents: Annotated[
        tuple[NoticeDocumentIdentity, ...], Field(min_length=13, max_length=13)
    ]
    lineage_review: Literal["pending", "accept-documented-lineage-limit"]

    @model_validator(mode="after")
    def exact_code_owned_inventory(self) -> Self:
        source = notice_registry()
        if (
            self.inventory_id != source.inventory_id
            or self.registry_sha256 != registry_sha256(source)
            or self.notice_text_sha256 != digest(notice_text(source))
            or self.map_payload != source.map_payload
            or self.source_ids != tuple(s.source_id for s in source.sections)
            or self.documents != document_identities(source)
        ):
            raise ValueError(
                "unknown, missing or changed supplementary "
                "notice/source/document identity"
            )
        return self


def verify_notice_components(
    notices: SupplementaryNotices, private: RegionalManifest
) -> None:
    # The narrowly audited registry is not a licence classifier for arbitrary maps.
    if private.components.map.files[1] != notices.map_payload:
        raise ValueError("supplementary notice map payload differs from exact build")


def require_notice_review(notices: SupplementaryNotices) -> None:
    if notices.lineage_review != "accept-documented-lineage-limit":
        raise ValueError(
            "supplementary notices await explicit publisher lineage review"
        )


def propose_supplementary_notices() -> SupplementaryNotices:
    """Return a provisional inventory, without approval or a regional request."""
    source = notice_registry()
    return SupplementaryNotices(
        inventory_id=source.inventory_id,
        registry_sha256=registry_sha256(source),
        notice_text_sha256=digest(notice_text(source)),
        map_payload=source.map_payload,
        source_ids=tuple(s.source_id for s in source.sections),
        documents=document_identities(source),
        lineage_review="pending",
    )


def render_browser_registry() -> str:
    source = notice_registry().model_dump(mode="json")
    return (
        "// Generated from offline_regions/notice_registry.json; do not edit.\n"
        "export const DATA_NOTICES = Object.freeze("
        + json.dumps(source, ensure_ascii=False, indent=2)
        + ");\n"
    )
