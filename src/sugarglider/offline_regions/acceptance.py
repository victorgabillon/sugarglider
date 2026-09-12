"""Verify Work's public bytes and prepare a guided Fairphone acceptance directory.

This command never installs an APK, changes phone state, or runs device scenarios.
The generated checklist keeps every physical result NOT RUN until observed.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sugarglider.planning.models import PLAN_REQUEST_ADAPTER

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "https://appassets.androidplatform.net"
JDK = Path("/usr/lib/jvm/java-17-openjdk-amd64/bin")
TOOL = ROOT.parent / "sugarglider-v1-artifacts/work-publication-code2/tools"
BUNDLETOOL = TOOL / "bundletool-1.18.3.jar"
BUNDLETOOL_SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"


class FileIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    byte_size: int = Field(ge=0, le=950_000_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Publication(BaseModel):
    base_url: str
    region_id: str
    build_id: str
    files: list[FileIdentity]


class Observation(BaseModel):
    url: str
    status: int
    bytes: int
    sha256: str
    content_type: str | None
    content_length: str | None
    content_encoding: str | None
    allow_origin: str | None
    seconds: float


class RequestCase(BaseModel):
    case: str = Field(pattern=r"^[a-z_]+$")
    request: dict[str, object]


class RequestFixtures(BaseModel):
    cases: list[RequestCase]


def public_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        value != value.strip()
        or len(value) > 2048
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or any(character.isspace() for character in value)
    ):
        raise ValueError("Use an exact public HTTPS URL without credentials or query")
    return value


def observe(
    client: httpx.Client,
    url: str,
    *,
    limit: int,
    expected: FileIdentity | None,
    cors: bool,
    capture: bool = False,
) -> tuple[Observation, bytes]:
    public_url(url)
    started = time.monotonic()
    digest = hashlib.sha256()
    size = 0
    captured = bytearray()
    with client.stream(
        "GET",
        url,
        headers={"Origin": ORIGIN, "Accept-Encoding": "identity"},
        follow_redirects=False,
    ) as response:
        if response.status_code != 200 or str(response.url) != url:
            raise ValueError("Hosted file must return direct HTTP 200 without redirect")
        encoding = response.headers.get("content-encoding")
        if encoding is not None and encoding.lower().strip() != "identity":
            raise ValueError("Hosted transfer must preserve identity entity bytes")
        if cors and response.headers.get("access-control-allow-origin") not in {
            "*",
            ORIGIN,
        }:
            raise ValueError("Hosted file lacks the required bundled-origin CORS grant")
        declared = response.headers.get("content-length")
        if expected is not None and declared is not None:
            if not declared.strip().isdigit() or int(declared) != expected.byte_size:
                raise ValueError("Hosted Content-Length differs from prepared size")
        for chunk in response.iter_raw(chunk_size=1_048_576):
            size += len(chunk)
            if size > limit or time.monotonic() - started > 900:
                raise ValueError("Hosted transfer exceeds the bounded acceptance read")
            digest.update(chunk)
            if capture:
                captured.extend(chunk)
        actual = digest.hexdigest()
        if expected is not None and (
            size != expected.byte_size or actual != expected.sha256
        ):
            raise ValueError("Hosted bytes differ from the verified prepared file")
        return Observation(
            url=url,
            status=response.status_code,
            bytes=size,
            sha256=actual,
            content_type=response.headers.get("content-type"),
            content_length=declared,
            content_encoding=encoding,
            allow_origin=response.headers.get("access-control-allow-origin"),
            seconds=round(time.monotonic() - started, 3),
        ), bytes(captured)


def inspect_signed_bundle(path: Path) -> dict[str, object]:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Signed AAB input must be an existing file")
    with BUNDLETOOL.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != BUNDLETOOL_SHA256:
            raise ValueError("The pinned official bundletool has changed")
    subprocess.run(
        [str(JDK / "java"), "-jar", str(BUNDLETOOL), "validate", f"--bundle={path}"],
        check=True,
        capture_output=True,
        timeout=180,
    )
    signature = subprocess.run(
        [str(JDK / "jarsigner"), "-J-Duser.language=en", "-verify", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if "jar verified." not in signature.stdout.lower():
        raise ValueError("The supplied AAB has no verified JAR signature")
    certificate = subprocess.run(
        [
            str(JDK / "keytool"),
            "-J-Duser.language=en",
            "-printcert",
            "-jarfile",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    fingerprints = re.findall(r"SHA256:\s*([A-Fa-f0-9:]{95})", certificate.stdout)
    if not fingerprints:
        raise ValueError("The AAB signer fingerprint could not be identified")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest,
        "public_certificate_sha256": sorted(set(fingerprints)),
        "expected_upload_identity_comparison": "REQUIRES_PUBLISHER_CONFIRMATION",
        "installed_play_signing_identity_comparison": "NOT_PERFORMED",
        "installed_on_phone": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-url", required=True, type=public_url)
    parser.add_argument("--privacy-url", required=True, type=public_url)
    parser.add_argument("--signed-aab", type=Path)
    args = parser.parse_args()
    publication = Publication.model_validate_json(
        (ROOT / "deploy/regions/github-pages/yvelines-publication.json").read_text()
    )
    if args.catalog_url != publication.base_url + "catalog.json":
        raise ValueError("Catalog URL differs from the prepared immutable layout")
    output = Path(tempfile.mkdtemp(prefix="sugarglider-v1-final-acceptance-"))
    observed: list[Observation] = []
    started = time.monotonic()
    report: dict[str, object] = {
        "status": "PREFLIGHT_INCOMPLETE",
        "physical_acceptance": "NOT_RUN",
        "catalog_url": args.catalog_url,
        "privacy_url": args.privacy_url,
        "region_id": publication.region_id,
        "build_id": publication.build_id,
        "device_state_changed": False,
    }
    try:
        with httpx.Client(
            timeout=30, follow_redirects=False, trust_env=False
        ) as client:
            for item in publication.files:
                if item.path == ".nojekyll":
                    continue  # Deployment flag, not a runtime download endpoint.
                if time.monotonic() - started > 1800:
                    raise ValueError(
                        "Public-file preflight exceeded its total deadline"
                    )
                result, content = observe(
                    client,
                    publication.base_url + item.path,
                    limit=item.byte_size,
                    expected=item,
                    cors=(
                        item.path == "catalog.json"
                        or (
                            item.path.startswith("regions/")
                            and "/routing/" not in item.path
                        )
                    ),
                    capture=item.path == "catalog.json",
                )
                observed.append(result)
                if item.path == "catalog.json":
                    (output / "verified-catalog.json").write_bytes(content)
            policy, content = observe(
                client,
                args.privacy_url,
                limit=65_536,
                expected=None,
                cors=False,
                capture=True,
            )
            decoded = content.decode("utf-8")
            if (
                "{{" in decoded
                or "}}" in decoded
                or 'data-policy-status="approved"' not in decoded
                or "sugarglider" not in decoded.lower()
                or "privacy" not in decoded.lower()
                or not (policy.content_type or "").startswith("text/html")
            ):
                raise ValueError("Public privacy page is not the completed HTML policy")
            report["privacy_observation"] = policy.model_dump()
        if args.signed_aab is not None:
            report["signed_bundle"] = inspect_signed_bundle(args.signed_aab)
        else:
            report["signed_bundle"] = "NOT_SUPPLIED"
        shutil.copyfile(
            ROOT / "tests/fixtures/v1_yvelines_requests.json", output / "requests.json"
        )
        fixtures = RequestFixtures.model_validate_json(
            (output / "requests.json").read_text()
        )
        directory = output / "requests"
        directory.mkdir()
        for case in fixtures.cases:
            request = PLAN_REQUEST_ADAPTER.validate_python(case.request)
            with (directory / f"{case.case}.json").open("x") as stream:
                stream.write(request.model_dump_json(indent=2) + "\n")
        shutil.copyfile(
            ROOT / "docs/v1-final-device-acceptance.md", output / "CHECKLIST.md"
        )
        report["status"] = "PUBLIC_BYTES_VERIFIED_DEVICE_NOT_RUN"
    except BaseException:
        report["status"] = "PREFLIGHT_FAILED_DEVICE_NOT_RUN"
        raise
    finally:
        report["hosted_files"] = [item.model_dump() for item in observed]
        report["seconds"] = round(time.monotonic() - started, 3)
        (output / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Acceptance directory: {output}")


if __name__ == "__main__":
    main()
