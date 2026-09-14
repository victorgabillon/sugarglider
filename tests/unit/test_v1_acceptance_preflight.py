import hashlib
from pathlib import Path

import httpx
import pytest

from sugarglider.offline_regions.acceptance import (
    ORIGIN,
    FileIdentity,
    RequestFixtures,
    observe,
    public_url,
)
from sugarglider.planning.models import PLAN_REQUEST_ADAPTER

URL = "https://example.test/catalog.json"
CONTENT = b'{"fixture":true}\n'
IDENTITY = FileIdentity(
    path="catalog.json",
    byte_size=len(CONTENT),
    sha256=hashlib.sha256(CONTENT).hexdigest(),
)


def test_preflight_observes_exact_bytes_without_following_redirects() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(CONTENT),
            headers={
                "Access-Control-Allow-Origin": ORIGIN,
                "Content-Type": "application/json",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result, content = observe(
            client,
            URL,
            limit=len(CONTENT),
            expected=IDENTITY,
            cors=True,
            capture=True,
        )
    assert content == CONTENT
    assert result.sha256 == IDENTITY.sha256
    assert result.bytes == len(CONTENT)
    assert len(requests) == 1
    assert requests[0].headers["accept-encoding"] == "identity"
    assert requests[0].headers["origin"] == ORIGIN


def test_preflight_does_not_reuse_host_response_cookies() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(CONTENT),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Set-Cookie": "host_session=fixture; Path=/; Secure",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        for _ in range(2):
            observe(client, URL, limit=len(CONTENT), expected=IDENTITY, cors=True)
    assert len(requests) == 2
    assert all("cookie" not in request.headers for request in requests)
    assert all("authorization" not in request.headers for request in requests)


@pytest.mark.parametrize(
    ("status", "headers", "body", "message"),
    [
        (302, {"Location": "/other"}, CONTENT, "without redirect"),
        (200, {}, CONTENT, "CORS"),
        (200, {"Access-Control-Allow-Origin": "*"}, b"altered", "differ"),
        (200, {"Access-Control-Allow-Origin": "*"}, CONTENT + b"x", "bounded"),
        (200, {"Content-Encoding": "gzip"}, CONTENT, "identity"),
        (
            200,
            {"Access-Control-Allow-Origin": "*", "Content-Length": "1"},
            CONTENT,
            "Content-Length",
        ),
    ],
)
def test_preflight_rejects_unusable_publication(
    status: int,
    headers: dict[str, str],
    body: bytes,
    message: str,
) -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(body))

    with httpx.Client(
        transport=httpx.MockTransport(respond),
        follow_redirects=True,
    ) as client:
        with pytest.raises(ValueError, match=message):
            observe(client, URL, limit=len(CONTENT), expected=IDENTITY, cors=True)
    assert calls == [URL]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/",
        "https://user:password@example.test/",
        "https://example.test/?secret=fixture",
        "https://example.test/#fragment",
    ],
)
def test_preflight_inputs_cannot_carry_authority(url: str) -> None:
    with pytest.raises(ValueError, match="exact public HTTPS"):
        public_url(url)


def test_prepared_yvelines_requests_satisfy_canonical_models() -> None:
    source = Path(__file__).resolve().parents[1] / "fixtures/v1_yvelines_requests.json"
    fixtures = RequestFixtures.model_validate_json(source.read_text())
    requests = [
        PLAN_REQUEST_ADAPTER.validate_python(case.request) for case in fixtures.cases
    ]
    assert len({case.case for case in fixtures.cases}) == len(requests) == 6
    assert {request.routing_profile for request in requests} == {"hike", "city_bike"}
