"""Strict PR39 region specifications and distribution manifests (not pack schemas)."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    field_validator,
    model_validator,
)

from sugarglider.osm_build_bounds import validate_bounds


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value) or ".." in value:
        raise ValueError("invalid component/region ID")
    return value


def safe_path(value: str) -> str:
    if not value or any(
        not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", part) or ".." in part
        for part in value.split("/")
    ):
        raise ValueError("expected a safe relative POSIX path")
    return value


type Identifier = Annotated[str, AfterValidator(safe_id)]
type RelativePath = Annotated[str, AfterValidator(safe_path)]
type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type RegionBounds = Annotated[
    tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat],
    AfterValidator(validate_bounds),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator(
        "schema_version",
        "pipeline_version",
        "poi_index_schema",
        "nature_index_schema",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def integer_versions(cls, value: object) -> int:
        # Literal[1] alone also accepts True/1.0 in Pydantic, even in strict mode.
        if type(value) is not int:
            raise ValueError("schema/version must be an integer")
        return value


class MapSpec(StrictModel):
    pack_id: Identifier
    template: RelativePath


class RoutingSpec(StrictModel):
    pack_id: Identifier
    engine: Literal["valhalla"] = "valhalla"
    engine_version: Literal["3.6.3"] = "3.6.3"
    access_modes: tuple[Literal["foot"], Literal["bicycle"]] = ("foot", "bicycle")


class IndexSpec(StrictModel):
    component_id: Identifier


class RegionSpec(StrictModel):
    schema_version: Literal[1]
    region_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    bounds: RegionBounds
    map: MapSpec
    routing: RoutingSpec
    pois: IndexSpec
    nature: IndexSpec

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.component_ids)) != 4:
            raise ValueError("duplicate component identities")
        return self

    @property
    def component_ids(self) -> tuple[str, str, str, str]:
        return (
            self.map.pack_id,
            self.routing.pack_id,
            self.pois.component_id,
            self.nature.component_id,
        )


class SourceIdentity(StrictModel):
    basename: RelativePath
    byte_size: Annotated[int, Field(gt=0)]
    sha256: Sha256
    header_bounds: tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat]
    coverage_evidence: Literal["osm-header-bounds"] = "osm-header-bounds"
    source_url: str | None = None

    @model_validator(mode="after")
    def basename_only(self) -> Self:
        if "/" in self.basename:
            raise ValueError("source basename must not contain a directory")
        if self.source_url is not None and not re.fullmatch(
            r"https?://[^\s]+", self.source_url
        ):
            raise ValueError("source URL must be an explicitly supplied HTTP(S) URL")
        return self


class Toolchain(StrictModel):
    pipeline_version: Literal[1] = 1
    protomaps_revision: Literal["3ea8293a28131c3dc63f1bb20827bdb8a76df06f"] = (
        "3ea8293a28131c3dc63f1bb20827bdb8a76df06f"
    )
    protomaps_archive_sha256: Literal[
        "7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807"
    ] = "7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807"
    map_build_image: Literal[
        "maven:3.9.13-eclipse-temurin-21-alpine@sha256:"
        "194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132"
    ] = (
        "maven:3.9.13-eclipse-temurin-21-alpine@sha256:"
        "194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132"
    )
    valhalla_image: Literal["ghcr.io/valhalla/valhalla:3.6.3"] = (
        "ghcr.io/valhalla/valhalla:3.6.3"
    )
    poi_index_schema: Literal[2] = 2
    poi_classifier: Literal["1", "2"] = "2"
    nature_index_schema: Literal[1] = 1
    python_version: str
    osmium_version: str
    shapely_version: str


type FileFormat = Literal[
    "map-manifest-v1",
    "pmtiles-v3-mvt",
    "routing-manifest-v2",
    "valhalla-3.6.3-tar",
    "poi-index-v2-gzip-json",
    "nature-index-v1-gzip-json",
]


class FileDescriptor(StrictModel):
    path: RelativePath
    byte_size: Annotated[int, Field(gt=0)]
    sha256: Sha256
    format: FileFormat


class Component(StrictModel):
    component_id: Identifier
    files: Annotated[tuple[FileDescriptor, ...], Field(min_length=1, max_length=2)]


class Components(StrictModel):
    map: Component
    routing: Component
    pois: Component
    nature: Component

    @model_validator(mode="after")
    def fixed_layout(self) -> Self:
        expected = (
            ("map/manifest.json", "map/basemap.pmtiles"),
            ("routing/manifest.json", "routing/valhalla_tiles.tar"),
            ("pois/index.json.gz",),
            ("nature/index.json.gz",),
        )
        formats = (
            ("map-manifest-v1", "pmtiles-v3-mvt"),
            ("routing-manifest-v2", "valhalla-3.6.3-tar"),
            ("poi-index-v2-gzip-json",),
            ("nature-index-v1-gzip-json",),
        )
        for component, paths, types in zip(
            self.ordered, expected, formats, strict=True
        ):
            if (
                tuple(file.path for file in component.files) != paths
                or tuple(file.format for file in component.files) != types
            ):
                raise ValueError("incorrect component paths/formats")
        if len({component.component_id for component in self.ordered}) != 4:
            raise ValueError("duplicate component identities")
        return self

    @property
    def ordered(self) -> tuple[Component, Component, Component, Component]:
        return self.map, self.routing, self.pois, self.nature


class RegionalManifest(StrictModel):
    schema_version: Literal[1] = 1
    region_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    bounds: RegionBounds
    source: SourceIdentity
    tools: Toolchain
    components: Components
    build_id: Sha256

    @model_validator(mode="after")
    def content_identity(self) -> Self:
        if self.build_id != build_identity(
            self.model_dump(mode="json", exclude={"build_id"})
        ):
            raise ValueError("regional build ID does not match manifest content")
        sw, ss, se, sn = self.source.header_bounds
        w, s, e, n = self.bounds
        if not (-180 <= sw <= w < e <= se <= 180 and -90 <= ss <= s < n <= sn <= 90):
            raise ValueError("source header does not cover manifest bounds")
        return self


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def build_identity(value: object) -> str:
    # A locator is informational; changing a URL cannot change content identity.
    if isinstance(value, dict) and isinstance(value.get("source"), dict):
        value = {
            **value,
            "source": {
                key: item
                for key, item in value["source"].items()
                if key != "source_url"
            },
        }
    return hashlib.sha256(canonical_json(value)).hexdigest()


def contained_path(root: Path, relative: str) -> Path:
    """Reject symlinks in every existing path segment, even in-root links."""
    safe_path(relative)
    if root.is_symlink():
        raise ValueError("symbolic-link root is not allowed")
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("symbolic-link artifact/path is not allowed")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes root")
    return candidate
