"""Real HTTPS delivery audit with explicit CA/origin and bounded streamed reads."""

import hashlib
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from sugarglider.offline_regions.distribution import distribution_base_url
from sugarglider.offline_regions.models import RegionalManifest

ANDROID_ORIGIN = "https://appassets.androidplatform.net"


def verify_https_region(
    manifest: RegionalManifest, base_url: str, *, ca_file: Path | None = None
) -> dict[str, int | str]:
    base = distribution_base_url(base_url)
    url = f"{base}regions/{manifest.region_id}/{manifest.build_id}/"
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HTTPS origin must be explicit and credential-free")
    context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    descriptors = [f for c in manifest.components.ordered for f in c.files]
    total = 0
    with httpx.Client(
        verify=context, follow_redirects=False, trust_env=False, timeout=120.0
    ) as client:
        for file in descriptors:
            target = url + file.path
            expected_headers = {"Accept-Encoding": "identity", "Origin": ANDROID_ORIGIN}
            with client.stream("GET", target, headers=expected_headers) as response:
                if (
                    response.status_code != 200
                    or str(response.url) != target
                    or response.headers.get("set-cookie")
                    or response.headers.get("content-encoding")
                    or response.headers.get("access-control-allow-origin")
                    != ANDROID_ORIGIN
                    or response.headers.get("access-control-allow-credentials")
                    or response.headers.get("content-length") != str(file.byte_size)
                ):
                    raise ValueError("HTTPS delivery headers/origin mismatch")
                count = 0
                checksum = hashlib.sha256()
                for chunk in response.iter_raw(65_536):
                    count += len(chunk)
                    if count > file.byte_size:
                        raise ValueError("HTTPS response exceeds descriptor")
                    checksum.update(chunk)
                if count != file.byte_size or checksum.hexdigest() != file.sha256:
                    raise ValueError(
                        "HTTPS delivered bytes differ from immutable component"
                    )
                total += count
            # Range support matters for PMTiles random access; inspect actual bytes.
            if file.format == "pmtiles-v3-mvt":
                with client.stream(
                    "GET", target, headers={**expected_headers, "Range": "bytes=0-126"}
                ) as response:
                    if (
                        response.status_code != 206
                        or str(response.url) != target
                        or response.headers.get("set-cookie")
                        or response.headers.get("access-control-allow-origin")
                        != ANDROID_ORIGIN
                        or response.headers.get("access-control-allow-credentials")
                        or response.headers.get("content-length") != "127"
                        or response.headers.get("content-range")
                        != f"bytes 0-126/{file.byte_size}"
                        or response.headers.get("content-encoding")
                    ):
                        raise ValueError("HTTPS PMTiles range contract failed")
                    header = bytearray()
                    for chunk in response.iter_raw(128):
                        header.extend(chunk)
                        if len(header) > 127:
                            raise ValueError("HTTPS PMTiles range exceeds budget")
                    if len(header) != 127 or header[:8] != b"PMTiles\x03":
                        raise ValueError("HTTPS PMTiles range bytes failed")
    return {
        "origin": f"{parsed.scheme}://{parsed.netloc}",
        "files": len(descriptors),
        "download_bytes": total,
        "tls": "verified-explicit-CA" if ca_file else "verified-system-CA",
    }
