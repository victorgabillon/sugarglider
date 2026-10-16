"""Strict V2 five-component regions; independent pack schemas remain separate."""

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
    ValidationInfo,
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

    @model_validator(mode="after")
    def explicit_wire_fields(self, info: ValidationInfo) -> Self:
        # Constructors may use defaults; serialized regional data must state every
        # field, matching the browser's exact field sets at each nested object.
        if info.mode == "json" and self.model_fields_set != set(
            type(self).model_fields
        ):
            raise ValueError("serialized component fields must be explicit")
        return self

    @field_validator("publication_allowed", mode="before", check_fields=False)
    @classmethod
    def boolean_publication_flag(cls, value: object) -> bool:
        if type(value) is not bool:
            raise ValueError("publication flag must be a boolean")
        return value

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
    engine_version: Literal["3.9.1"] = "3.9.1"
    access_modes: tuple[Literal["foot"], Literal["bicycle"]] = ("foot", "bicycle")


class IndexSpec(StrictModel):
    component_id: Identifier


class RegionSpec(StrictModel):
    schema_version: Literal[2]
    region_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    bounds: RegionBounds
    map: MapSpec
    routing: RoutingSpec
    pois: IndexSpec
    nature: IndexSpec
    elevation: IndexSpec

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.component_ids)) != 5:
            raise ValueError("duplicate component identities")
        return self

    @property
    def component_ids(self) -> tuple[str, str, str, str, str]:
        return (
            self.map.pack_id,
            self.routing.pack_id,
            self.pois.component_id,
            self.nature.component_id,
            self.elevation.component_id,
        )


class SourceIdentity(StrictModel):
    basename: RelativePath
    byte_size: Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
    sha256: Sha256
    header_bounds: tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat]
    coverage_evidence: Literal["osm-header-bounds"] = "osm-header-bounds"
    source_url: Annotated[str, Field(max_length=2048)] | None = None

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
    pipeline_version: Literal[2] = 2
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
    valhalla_image: Literal[
        "ghcr.io/valhalla/valhalla:3.9.1@sha256:"
        "18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a"
    ] = (
        "ghcr.io/valhalla/valhalla:3.9.1@sha256:"
        "18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a"
    )
    poi_index_schema: Literal[2] = 2
    poi_classifier: Literal["1", "2", "3"] = "3"
    nature_index_schema: Literal[1] = 1
    python_version: Annotated[str, Field(min_length=1, max_length=80)]
    osmium_version: Annotated[str, Field(min_length=1, max_length=80)]
    shapely_version: Annotated[str, Field(min_length=1, max_length=80)]


type FileFormat = Literal[
    "map-manifest-v1",
    "pmtiles-v3-mvt",
    "routing-manifest-v2",
    "valhalla-3.9.1-elevation-tar",
    "poi-index-v2-gzip-json",
    "nature-index-v1-gzip-json",
    "elevation-manifest-v1",
    "skadi-hgt-gzip-v1",
]


class FileDescriptor(StrictModel):
    path: RelativePath
    byte_size: Annotated[int, Field(gt=0)]
    sha256: Sha256
    format: FileFormat


class Component(StrictModel):
    component_id: Identifier
    files: Annotated[tuple[FileDescriptor, ...], Field(min_length=1, max_length=17)]


class Components(StrictModel):
    map: Component
    routing: Component
    pois: Component
    nature: Component
    elevation: Component

    @model_validator(mode="after")
    def fixed_layout(self) -> Self:
        for kind, component in zip(
            ("map", "routing", "pois", "nature", "elevation"), self.ordered, strict=True
        ):
            for index, file in enumerate(component.files):
                maximum = (
                    32 * 1024 * 1024
                    if kind in ("pois", "nature")
                    else (65_536 if index == 0 else 26_982_978)
                    if kind == "elevation"
                    else (16_384 if index == 0 else 2**31)
                )
                if file.byte_size > maximum:
                    raise ValueError("regional file exceeds component budget")
        expected = (
            ("map/manifest.json", "map/basemap.pmtiles"),
            ("routing/manifest.json", "routing/valhalla_tiles.tar"),
            ("pois/index.json.gz",),
            ("nature/index.json.gz",),
        )
        formats = (
            ("map-manifest-v1", "pmtiles-v3-mvt"),
            ("routing-manifest-v2", "valhalla-3.9.1-elevation-tar"),
            ("poi-index-v2-gzip-json",),
            ("nature-index-v1-gzip-json",),
        )
        for component, paths, types in zip(
            self.ordered[:4], expected, formats, strict=True
        ):
            if (
                tuple(file.path for file in component.files) != paths
                or tuple(file.format for file in component.files) != types
            ):
                raise ValueError("incorrect component paths/formats")
        elevation = self.elevation.files
        if (
            len(elevation) < 2
            or (elevation[0].path, elevation[0].format)
            != ("elevation/manifest.json", "elevation-manifest-v1")
            or any(file.format != "skadi-hgt-gzip-v1" for file in elevation[1:])
            or tuple(file.path for file in elevation[1:])
            != tuple(sorted({file.path for file in elevation[1:]}))
        ):
            raise ValueError("invalid elevation component layout")
        if len({component.component_id for component in self.ordered}) != 5:
            raise ValueError("duplicate component identities")
        return self

    @property
    def ordered(self) -> tuple[Component, Component, Component, Component, Component]:
        return self.map, self.routing, self.pois, self.nature, self.elevation


class RegionalManifest(StrictModel):
    schema_version: Literal[2] = 2
    publication_allowed: Literal[False] = False
    region_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    bounds: RegionBounds
    source: SourceIdentity
    tools: Toolchain
    components: Components
    build_id: Sha256

    @model_validator(mode="after")
    def content_identity(self) -> Self:
        from sugarglider.offline_regions.elevation_layout import elevation_paths

        if tuple(file.path for file in self.components.elevation.files[1:]) != (
            elevation_paths(self.bounds)
        ):
            raise ValueError("elevation tiles do not exactly cover regional bounds")
        if self.build_id != build_identity(
            self.model_dump(mode="json", exclude={"build_id"})
        ):
            raise ValueError("regional build ID does not match manifest content")
        sw, ss, se, sn = self.source.header_bounds
        w, s, e, n = self.bounds
        if not (-180 <= sw <= w < e <= se <= 180 and -90 <= ss <= s < n <= sn <= 90):
            raise ValueError("source header does not cover manifest bounds")
        return self


def _canonical_value(value: object) -> object:
    # V2 treats signed zero as the same coordinate. JSON.stringify erases its
    # sign on message/worker boundaries; it must not change a build identity.
    if isinstance(value, float) and value == 0:
        return 0.0
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            _canonical_value(value),
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
