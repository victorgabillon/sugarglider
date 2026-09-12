"""Prepare a verified static publication directory; never upload or deploy it."""

import argparse
import hashlib
import html
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from sugarglider.offline_regions.models import RegionalManifest, canonical_json
from sugarglider.offline_regions.validation import verify_region

ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
OSM_URL = "https://www.openstreetmap.org/copyright"
SOURCE_URL = "https://github.com/victorgabillon/sugarglider"


def distribution_base_url(value: str) -> str:
    """Keep the same explicit HTTPS directory form accepted by the app."""
    parsed = urlsplit(value)
    if (
        len(value) > 1_500
        or parsed.scheme != "https"
        or not re.fullmatch(r"[a-z0-9.-]+(?::[1-9][0-9]{0,4})?", parsed.netloc)
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/")
        or value != f"https://{parsed.netloc}{parsed.path}"
        or any(
            not re.fullmatch(r"[A-Za-z0-9._~-]+", part) or ".." in part or part == "."
            for part in parsed.path[1:-1].split("/")
            if parsed.path != "/"
        )
    ):
        raise ValueError("base URL must be a canonical credential-free HTTPS directory")
    if parsed.port is not None and not 1 <= parsed.port <= 65_535:
        raise ValueError("invalid distribution port")
    return value


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _notice(manifest: RegionalManifest, relative: str) -> str:
    return f"""Sugarglider regional data: {manifest.display_name}

Map data © OpenStreetMap contributors.
Regional map, routing, places and nature databases are available under the
Open Data Commons Open Database License (ODbL) 1.0: {ODBL_URL}
Attribution and source licensing information: {OSM_URL}

Region ID: {manifest.region_id}
Immutable build ID: {manifest.build_id}
Coverage [west, south, east, north]: {list(manifest.bounds)}
Manifest: {relative}/manifest.json

Coverage follows these rectangular bounds, not administrative borders. Mapped
data does not establish current access, opening, conditions, potability or safe
passage. Routing profiles are preferences over mapped data, not guarantees.

All four generated databases are supplied in the format used by the app. The
manifest records the configured local OSM PBF input's SHA-256, header coverage,
build tools and every component's size and SHA-256. No input PBF is included.
No source timestamp, download URL or completeness beyond that record is asserted.
The build/transformation source is available at {SOURCE_URL}
(offline_regions, map-packs, routing extraction, pois and nature build modules).

HTTP delivery must preserve the exact stored file bytes. Serve gzip index files
as files, without Content-Encoding transformation. Public CORS access is needed
for the bundled Android web origin. See docs/pr42-static-distribution.md in the
source repository for the hosting contract and publication verification steps.
"""


def prepare_distribution(
    source: Path,
    output: Path,
    *,
    base_url: str,
    description: str,
    retain_directory: Path | None = None,
) -> Path:
    """Verify source, exclusively create output, and package exact component bytes."""
    base = distribution_base_url(base_url)
    if not 1 <= len(description) <= 500 or description.strip() != description:
        raise ValueError("description must contain 1..500 trimmed characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in description):
        raise ValueError("description contains control characters")
    source, output = source.absolute(), output.absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("symbolic-link output path is not allowed")
    if output.exists():
        raise FileExistsError(output)
    if not output.parent.is_dir() or output.resolve().is_relative_to(source.resolve()):
        raise ValueError("output requires an existing parent outside the source region")
    manifest = verify_region(source)
    sources = [(source, manifest)]
    if retain_directory is not None:
        retained = verify_region(retain_directory)
        if (
            retained.region_id != manifest.region_id
            or retained.build_id == manifest.build_id
        ):
            raise ValueError("retain one different version of the same region")
        if output.resolve().is_relative_to(retain_directory.resolve()):
            raise ValueError("output must remain outside the retained region")
        sources.append((retain_directory, retained))
    relative = f"regions/{manifest.region_id}/{manifest.build_id}"
    names = [
        "manifest.json",
        *(
            file.path
            for component in manifest.components.ordered
            for file in component.files
        ),
    ]
    total = sum((source / name).stat().st_size for name in names)
    publication_total = sum(
        (directory / name).stat().st_size for directory, _ in sources for name in names
    )
    if publication_total + 65_536 > 950_000_000:
        raise ValueError("publication exceeds the static host size budget")
    if shutil.disk_usage(output.parent).free < publication_total * 2 + 65_536:
        raise ValueError("insufficient free space for the site and publication archive")
    output.mkdir()  # Exclusive ownership; never replace or reuse an existing output.
    try:
        site = output / "site"
        for directory, captured in sources:
            target_region = site / "regions" / captured.region_id / captured.build_id
            target_region.mkdir(parents=True)
            for name in names:
                target = target_region / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(directory / name, target)
            copied = verify_region(target_region)
            if (
                copied != captured
                or (target_region / "manifest.json").read_bytes()
                != (directory / "manifest.json").read_bytes()
            ):
                raise ValueError("source changed while preparing distribution")
        offering = {
            "region_id": manifest.region_id,
            "display_name": manifest.display_name,
            "description": description,
            "build_id": manifest.build_id,
            "bounds": manifest.bounds,
            "download_bytes": sum(
                file.byte_size
                for component in manifest.components.ordered
                for file in component.files
            ),
            "manifest_url": f"{base}{relative}/manifest.json",
        }
        (site / "catalog.json").write_bytes(
            canonical_json({"schema_version": 1, "regions": [offering]})
        )
        (site / "README.txt").write_text(_notice(manifest, relative), encoding="utf-8")
        if len(sources) > 1:
            with (site / "README.txt").open("a", encoding="utf-8") as notice:
                notice.write(
                    "\nPrevious version retained under the same data license: "
                    + sources[1][1].build_id
                    + "\n"
                )
        (site / ".nojekyll").write_bytes(b"")
        (site / "index.html").write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Sugarglider offline regions</title>"
            "<h1>Sugarglider offline regions</h1>"
            f"<h2>{html.escape(manifest.display_name)}</h2>"
            f"<p>{html.escape(description)}</p><p>About {total / 1_000_000:.1f} MB.</p>"
            f'<p>Map data © <a href="{OSM_URL}">OpenStreetMap contributors</a>. '
            f'Regional databases are available under the <a href="{ODBL_URL}">'
            "Open Database License (ODbL) 1.0</a>.</p>"
            '<p><a href="README.txt">Data attribution and build information</a></p>'
            f'<p><a href="{relative}/manifest.json">Immutable regional manifest</a></p>'
            '<p><a href="catalog.json">Regional catalog</a></p></html>\n',
            encoding="utf-8",
        )
        archive = output / "sugarglider-regions-static.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path in sorted(site.rglob("*")):
                if not path.is_file():
                    continue
                member = zipfile.ZipInfo(
                    path.relative_to(site).as_posix(), (1980, 1, 1, 0, 0, 0)
                )
                member.external_attr = 0o100644 << 16
                with path.open("rb") as reader, bundle.open(member, "w") as writer:
                    shutil.copyfileobj(reader, writer, length=1_048_576)
        (output / "report.json").write_bytes(
            canonical_json(
                {
                    "publication": "not published",
                    "base_url": base,
                    "region_id": manifest.region_id,
                    "build_id": manifest.build_id,
                    "regional_bytes": total,
                    "publication_regional_bytes": publication_total,
                    "retained_build_ids": [item.build_id for _, item in sources[1:]],
                    "archive_bytes": archive.stat().st_size,
                    "archive_sha256": _sha256(archive),
                    "files": [
                        {
                            "path": path.relative_to(site).as_posix(),
                            "byte_size": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                        for path in sorted(site.rglob("*"))
                        if path.is_file()
                    ],
                }
            )
        )
        return output
    except BaseException:
        shutil.rmtree(output)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-directory", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--retain-directory", type=Path)
    arguments = parser.parse_args()
    try:
        output = prepare_distribution(
            arguments.region_directory,
            arguments.output_directory,
            base_url=arguments.base_url,
            description=arguments.description,
            retain_directory=arguments.retain_directory,
        )
    except (ValueError, OSError) as error:
        print(f"static-distribution: {error}", file=sys.stderr)
        return 1
    print(f"Prepared, not published: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
