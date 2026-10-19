"""A working offline route and a failed UID diagnostic are independent facts."""

import json

import pytest
from pydantic import ValidationError

from sugarglider.offline_regions.offline_acceptance import (
    FirstPartyChecks,
    OfflineChecks,
    OfflineReviewEvidence,
    ReviewEnvironment,
    UidMeasurement,
    assess_offline_review,
)


def receipt(tx: int = 12720, rx: int = 13152) -> OfflineReviewEvidence:
    return OfflineReviewEvidence(
        schema_version=1,
        package_id="io.github.victorgabillon.sugarglider.v2audittest",
        apk_sha256="a" * 64,
        environment=ReviewEnvironment(
            region_server_available=False,
            internet_permission=True,
            webview_network_loads_blocked=False,
            device_connectivity="connected",
        ),
        offline_checks=OfflineChecks.model_validate(
            dict.fromkeys(OfflineChecks.model_fields, True)
        ),
        first_party_checks=FirstPartyChecks.model_validate(
            dict.fromkeys(FirstPartyChecks.model_fields, True)
        ),
        platform_network=UidMeasurement(
            uid=12345,
            pid=100,
            android_api=36,
            webview_provider="synthetic test provider",
            tx_before_bytes=100,
            rx_before_bytes=200,
            tx_after_bytes=100 + tx,
            rx_after_bytes=200 + rx,
        ),
    )


@pytest.mark.parametrize("tx,rx", [(12720, 13152), (1, 0), (0, 1)])
def test_nonzero_diagnostic_remains_failed_without_overriding_offline_results(
    tx: int, rx: int
) -> None:
    result = assess_offline_review(receipt(tx, rx))
    assert result.offline_functionality == "passed_within_scope"
    assert result.first_party_controls == "passed_within_scope"
    assert result.strict_zero_diagnostic == "failed"
    assert (result.uid_tx_bytes, result.uid_rx_bytes) == (tx, rx)
    assert result.platform_disclosure == "review_required"
    assert result.public_release == "not_authorized"


@pytest.mark.parametrize("name", OfflineChecks.model_fields)
def test_silence_cannot_pass_a_missing_functional_check(name: str) -> None:
    data = receipt(0, 0).model_dump()
    data["offline_checks"][name] = False
    result = assess_offline_review(OfflineReviewEvidence.model_validate(data))
    assert result.offline_functionality == "failed"
    assert result.failed_offline_checks == (name,)
    assert result.strict_zero_diagnostic == "passed"
    assert result.platform_disclosure == "review_required"
    assert result.public_release == "not_authorized"


@pytest.mark.parametrize("name", FirstPartyChecks.model_fields)
def test_offline_success_never_waives_first_party_controls(name: str) -> None:
    data = receipt().model_dump()
    data["first_party_checks"][name] = False
    result = assess_offline_review(OfflineReviewEvidence.model_validate(data))
    assert result.offline_functionality == "passed_within_scope"
    assert result.first_party_controls == "failed"
    assert result.failed_first_party_checks == (name,)


@pytest.mark.parametrize(
    "environment,scope",
    [
        ({"device_connectivity": "disconnected"}, "device_disconnected"),
        ({"internet_permission": False}, "research_app_without_internet_permission"),
        ({"webview_network_loads_blocked": True}, "webview_network_loads_blocked"),
        ({}, "region_server_unavailable"),
        ({"region_server_available": True}, "connected_control"),
    ],
)
def test_narrow_denial_controls_never_become_device_disconnection(
    environment: dict[str, str | bool], scope: str
) -> None:
    data = receipt().model_dump()
    data["environment"].update(environment)
    result = assess_offline_review(OfflineReviewEvidence.model_validate(data))
    assert result.measured_scope == scope
    assert result.offline_functionality == (
        "not_established" if scope == "connected_control" else "passed_within_scope"
    )


@pytest.mark.parametrize("value", [None, -1, "0", True])
def test_unavailable_or_malformed_counters_are_never_zero(value: object) -> None:
    data = receipt().model_dump()
    data["platform_network"]["tx_before_bytes"] = value
    with pytest.raises(ValidationError):
        OfflineReviewEvidence.model_validate(data)


def test_counter_reset_missing_checks_and_extra_authority_are_rejected() -> None:
    data = receipt().model_dump()
    data["platform_network"]["tx_after_bytes"] = 99
    with pytest.raises(ValidationError, match="monotonic"):
        OfflineReviewEvidence.model_validate(data)
    data = receipt().model_dump()
    del data["offline_checks"]["local_map"]
    with pytest.raises(ValidationError):
        OfflineReviewEvidence.model_validate(data)
    data = receipt().model_dump()
    data["route_coordinates"] = [[2, 48]]
    with pytest.raises(ValidationError):
        OfflineReviewEvidence.model_validate(data)
    data = receipt().model_dump()
    data["publication_allowed"] = True
    with pytest.raises(ValidationError):
        OfflineReviewEvidence.model_validate(data)


def test_unknown_view_setting_is_not_inferred_from_missing_internet_permission() -> (
    None
):
    data = receipt(0, 0).model_dump()
    data["environment"].update(
        internet_permission=False, webview_network_loads_blocked=None
    )
    restored = OfflineReviewEvidence.model_validate(data)
    assert restored.environment.webview_network_loads_blocked is None
    result = assess_offline_review(restored)
    assert result.measured_scope == "research_app_without_internet_permission"
    assert result.platform_disclosure == "review_required"


def test_receipt_round_trip_is_deterministic_and_metadata_only() -> None:
    original = receipt()
    restored = OfflineReviewEvidence.model_validate_json(original.model_dump_json())
    assert assess_offline_review(original) == assess_offline_review(restored)
    assert json.loads(assess_offline_review(original).model_dump_json())["uid_tx_bytes"]
