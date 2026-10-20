"""Explicit loopback HTTPS acceptance with synthetic IGN bytes and authority only.

Run separately from the network-free unit suite. No device, publication or trust
store changes. Output and the three-day test CA remain in a fresh private folder.
"""

import argparse
import importlib.util
import json
import shutil
import ssl
import subprocess
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
from test_pr101_ign_publication import (
    ApprovalArguments,
    build_synthetic_ign,
    synthetic_approval,
)

from sugarglider.offline_regions.distribution import prepare_distribution
from sugarglider.offline_regions.https_transport import (
    ANDROID_ORIGIN,
    verify_https_region,
)
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import digest
from sugarglider.offline_regions.release_catalog import preflight_catalog
from sugarglider.offline_regions.validation import verify_region

ROOT = Path(__file__).resolve().parents[2]


def run(output: Path) -> dict[str, object]:
    output.mkdir(mode=0o700)
    fixture_root = output / "synthetic"
    fixture_root.mkdir()
    fixture = build_synthetic_ign(fixture_root)
    approved = fixture.approve(output / "synthetic-approved")
    manifest = verify_region(approved)
    evidence, approval = output / "evidence.json", output / "approval.json"
    evidence.write_bytes(canonical_json(fixture.evidence.model_dump(mode="json")))
    approval_bytes = synthetic_approval(fixture.evidence)
    approval.write_bytes(approval_bytes)
    kwargs: ApprovalArguments = dict(
        evidence_path=evidence,
        approval_path=approval,
        trusted_approval_sha256=digest(approval_bytes),
    )
    ca = output / "ca"
    subprocess.run(
        ["sh", str(ROOT / "scripts/create_private_v2_test_ca.sh"), str(ca)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    module_spec = importlib.util.spec_from_file_location(
        "private_https", ROOT / "scripts/serve_private_v2_https.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    hosting = output / "hosting"
    hosting.mkdir()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(module.PrivateHandler, directory=str(hosting))
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(ca / "server.pem", ca / "server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    base = f"https://localhost:{server.server_port}/v2/"
    distribution = prepare_distribution(
        approved,
        output / "distribution",
        base_url=base,
        description="SYNTHETIC IGN acceptance only",
        **kwargs,
    )
    shutil.copytree(distribution / "site", hosting / "v2")
    preflight_catalog(
        hosting / "v2/catalog.json", hosting / "v2", base_url=base, **kwargs
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results: dict[str, object] = {
        "scope": "SYNTHETIC ONLY; no real IGN approval",
        "components": 5,
        "hgt_tiles": 4,
    }
    try:
        results["first_audit"] = verify_https_region(
            manifest, base, ca_file=ca / "ca.pem"
        )
        headers = {"Origin": ANDROID_ORIGIN, "Accept-Encoding": "identity"}
        tls = ssl.create_default_context(cafile=str(ca / "ca.pem"))
        with httpx.Client(
            verify=tls, follow_redirects=False, trust_env=False
        ) as client:
            url = (
                base
                + f"regions/{manifest.region_id}/{manifest.build_id}/"
                + "map/basemap.pmtiles"
            )
            response = client.options(
                url,
                headers={
                    **headers,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Range",
                },
            )
            assert response.status_code == 204
            assert response.headers["access-control-allow-origin"] == ANDROID_ORIGIN
            assert "Range" in response.headers["access-control-allow-headers"]
            # Abandon one response, then retry against the unchanged immutable path.
            with client.stream("GET", url, headers=headers) as stream:
                assert stream.status_code == 200
                next(stream.iter_raw(16))
            response = client.get(url, headers={**headers, "Range": "bytes=0-126"})
            assert response.status_code == 206 and len(response.content) == 127
            assert client.get(base + "regions/", headers=headers).status_code == 403
        results["cors_preflight_range_interruption_retry_no_listing"] = "passed"
        target = hosting / "v2/regions" / manifest.region_id / manifest.build_id
        hgt = target / manifest.components.elevation.files[1].path
        original = hgt.read_bytes()
        for fault in ("corrupt", "incomplete"):
            if fault == "corrupt":
                hgt.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            else:
                hgt.unlink()
            try:
                verify_https_region(manifest, base, ca_file=ca / "ca.pem")
            except ValueError:
                results[fault + "_rejected"] = True
            else:
                raise AssertionError(fault + " accepted")
            finally:
                hgt.write_bytes(original)
        results["recovery_audit"] = verify_https_region(
            manifest, base, ca_file=ca / "ca.pem"
        )
        catalog = hosting / "v2/catalog.json"
        catalog_bytes = catalog.read_bytes()
        changed = json.loads(catalog_bytes)
        changed["regions"][0]["build_id"] = "f" * 64
        catalog.write_bytes(canonical_json(changed))
        try:
            preflight_catalog(catalog, hosting / "v2", base_url=base, **kwargs)
        except ValueError:
            results["wrong_build_rejected"] = True
        else:
            raise AssertionError("wrong build accepted")
        finally:
            catalog.write_bytes(catalog_bytes)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    # A new server process-equivalent actor reopens the retained site and CA.
    restarted = ThreadingHTTPServer(
        ("127.0.0.1", server.server_port),
        partial(module.PrivateHandler, directory=str(hosting)),
    )
    restarted.socket = context.wrap_socket(restarted.socket, server_side=True)
    thread = threading.Thread(target=restarted.serve_forever, daemon=True)
    thread.start()
    try:
        results["restart_audit"] = verify_https_region(
            manifest, base, ca_file=ca / "ca.pem"
        )
    finally:
        restarted.shutdown()
        restarted.server_close()
        thread.join()
    results["private_region_still_unauthorized"] = not verify_region(
        fixture.region
    ).publication_allowed
    (output / "result.json").write_bytes(canonical_json(results))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
