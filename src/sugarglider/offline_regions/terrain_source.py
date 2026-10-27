"""Pinned public-source acquisition. Download permission is not publication approval."""

import hashlib
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import httpx
from pydantic import Field, model_validator

from sugarglider.offline_regions.models import RelativePath, Sha256, StrictModel

COPERNICUS_ATTRIBUTION = (
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus "
    "Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European "
    "Union and ESA; all rights reserved"
)
COPERNICUS_DISCLAIMER = (
    "The organisations in charge of the Copernicus programme by law or by "
    "delegation do not incur any liability for any use of the Copernicus WorldDEM-30"
)
COPERNICUS_LICENSE = (
    "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/"
    "resources/license/License-COPDEM-30.pdf"
)


class SourceFile(StrictModel):
    filename: RelativePath
    url: Annotated[str, Field(pattern=r"^https://[^\s?#@]+$", max_length=2048)]
    byte_size: Annotated[int, Field(gt=0, le=90_000_000)]
    sha256: Sha256
    acquired_at: str
    last_modified: str | None
    etag: str | None
    version_id: str | None


IGN_LICENSE = "https://www.etalab.gouv.fr/licence-ouverte-open-licence/"
IGN_ATTRIBUTION = "IGN — RGE ALTI® 5 m; Licence Ouverte / Open Licence 2.0"


class IGNArchive(SourceFile):
    # Departmental deliveries exceed the old individual COG download limit.
    byte_size: Annotated[int, Field(gt=0, le=1_000_000_000)]

    @model_validator(mode="after")
    def official_archive(self) -> Self:
        if not re.fullmatch(
            r"RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D[0-9]{3}_"
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.7z",
            self.filename,
        ):
            raise ValueError("expected mainland RGE ALTI 5 m delivery identity")
        delivery = self.filename.removesuffix(".7z")
        date.fromisoformat(delivery[-10:])
        if (
            not 20 <= len(self.acquired_at) <= 40
            or datetime.fromisoformat(self.acquired_at).tzinfo is None
        ):
            raise ValueError("IGN acquisition timestamp requires a timezone")
        if self.url != (
            "https://data.geopf.fr/telechargement/download/RGEALTI/"
            f"{delivery}/{self.filename}"
        ):
            raise ValueError("IGN source URL/delivery mismatch")
        return self


class IGNSources(StrictModel):
    schema_version: Literal[1] = 1
    product: Literal["IGN-RGE-ALTI-5M"]
    horizontal_crs: Literal["EPSG:2154"]
    vertical_crs: Literal["EPSG:5720"]  # IGN69 normal heights, not EGM96.
    surface: Literal["DTM"]
    license_url: Literal["https://www.etalab.gouv.fr/licence-ouverte-open-licence/"]
    files: Annotated[tuple[IGNArchive, ...], Field(min_length=1, max_length=24)]

    @model_validator(mode="after")
    def unique_departments(self) -> Self:
        departments = [p.filename.split("_")[5] for p in self.files]
        if len(set(departments)) != len(departments):
            raise ValueError("duplicate IGN department or ambiguous source vintages")
        return self


class TerrainSources(StrictModel):
    schema_version: Literal[1] = 1
    product: Literal["COP-DEM_GLO-30-DGED-COG"]
    release: Literal["2021"]
    horizontal_crs: Literal["EPSG:4326"]
    vertical_crs: Literal["EPSG:3855"]
    surface: Literal["DSM"]
    license_url: Literal[
        "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/"
        "resources/license/License-COPDEM-30.pdf"
    ]
    files: Annotated[tuple[SourceFile, ...], Field(min_length=6, max_length=11)]

    @property
    def raster_tiles(self) -> tuple[tuple[int, int], ...]:
        """The bounded rectangular source grid, including its south/east halo."""
        return tuple(
            sorted(
                (
                    int(pin.filename.split("_")[4][1:]),
                    int(pin.filename.split("_")[6][1:]),
                )
                for pin in self.files
                if pin.filename.startswith("Copernicus_DSM_COG_10_N")
            )
        )

    @model_validator(mode="after")
    def complete_product(self) -> Self:
        tiles: list[tuple[int, int]] = []
        for pin in self.files:
            match = re.fullmatch(
                r"Copernicus_DSM_COG_10_N([0-8][0-9])_00_E([01][0-9]{2})_00_DEM\.tif",
                pin.filename,
            )
            if match is not None:
                lat, lon = int(match[1]), int(match[2])
                if lon >= 180:
                    raise ValueError("unsupported Copernicus source longitude")
                tiles.append((lat, lon))
        if not tiles:
            raise ValueError("incomplete Copernicus source grid")
        south, north = min(t[0] for t in tiles), max(t[0] for t in tiles)
        west, east = min(t[1] for t in tiles), max(t[1] for t in tiles)
        if south == north or west == east:
            raise ValueError("incomplete south/east source halo")
        expected = {}
        for lat in range(south, north + 1):
            for lon in range(west, east + 1):
                name = f"Copernicus_DSM_COG_10_N{lat:02}_00_E{lon:03}_00_DEM"
                expected[name + ".tif"] = (
                    f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
                )
        for name in ("us_nga_egm08_25.tif", "us_nga_egm96_15.tif"):
            expected[name] = "https://cdn.proj.org/" + name
        if {p.filename: p.url for p in self.files} != expected or len(
            {p.filename for p in self.files}
        ) != len(expected):
            raise ValueError("incomplete, duplicate or mismatched product source URLs")
        return self


def verify_source(directory: Path, pin: SourceFile) -> Path:
    from sugarglider.offline_regions.models import contained_path

    path = contained_path(directory, pin.filename)
    if not path.is_file() or path.stat().st_size != pin.byte_size:
        raise ValueError("source size mismatch")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != pin.sha256:
            raise ValueError("source hash mismatch")
    return path


def acquire_sources(pins: TerrainSources | IGNSources, output: Path) -> None:
    """Explicit bounded HTTPS GETs, fresh directory, no auth, redirects or cookies."""
    if len({pin.filename for pin in pins.files}) != len(pins.files):
        raise ValueError("duplicate source files")
    if output.is_symlink() or any(p.is_symlink() for p in output.absolute().parents):
        raise ValueError("symlink acquisition output")
    if (
        shutil.disk_usage(output.parent).free
        < sum(pin.byte_size for pin in pins.files) + 65_536
    ):
        raise ValueError("insufficient disk for pinned source acquisition")
    output.mkdir()  # An incomplete acquisition is never reused implicitly.
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=90.0) as client:
        for pin in pins.files:
            target = output / pin.filename
            if "/" in pin.filename:
                raise ValueError("source filename must be a basename")
            with client.stream(
                "GET", pin.url, headers={"Accept-Encoding": "identity"}
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-encoding")
                    or response.headers.get("set-cookie")
                    or response.headers.get("content-length") != str(pin.byte_size)
                ):
                    raise ValueError("unexpected source HTTPS response")
                count = 0
                with target.open("xb") as stream:
                    for chunk in response.iter_raw(65_536):
                        count += len(chunk)
                        if count > pin.byte_size:
                            raise ValueError("source exceeds pin")
                        stream.write(chunk)
            verify_source(output, pin)
