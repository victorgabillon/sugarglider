"""Validate offline review receipts without turning UID silence into approval.

This is evidence-report tooling, never part of routing or a release authorization.
It checks receipt consistency; it cannot attest that a physical test was executed.
"""

import argparse
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Nonnegative = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
type MeasuredScope = Literal[
    "device_disconnected",
    "research_app_without_internet_permission",
    "webview_network_loads_blocked",
    "region_server_unavailable",
    "connected_control",
]


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class OfflineChecks(ReviewRecord):
    verified_region: bool
    cold_start: bool
    warm_start: bool
    six_profiles: bool
    waypoint_open_and_loop: bool
    auto_tour: bool
    local_map: bool
    local_places_and_nature: bool
    ign_elevation_and_chart: bool
    candidate_and_region_switching: bool
    cancellation_and_retry: bool
    gpx_and_android_save: bool
    restart_with_installed_data: bool
    missing_coverage_fails: bool
    optional_online_failure_visible: bool


class FirstPartyChecks(ReviewRecord):
    no_routing_server_fallback: bool
    no_automatic_route_upload: bool
    no_automatic_location_upload: bool
    no_unintended_remote_api: bool
    downloads_only_by_explicit_action: bool
    local_only_release_policy: bool


class ReviewEnvironment(ReviewRecord):
    region_server_available: bool
    internet_permission: bool
    webview_network_loads_blocked: bool | None
    device_connectivity: Literal["connected", "disconnected", "not_measured"]


class UidMeasurement(ReviewRecord):
    uid: Nonnegative
    pid: Annotated[int, Field(gt=0)]
    android_api: Annotated[int, Field(ge=26)]
    webview_provider: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    tx_before_bytes: Nonnegative
    rx_before_bytes: Nonnegative
    tx_after_bytes: Nonnegative
    rx_after_bytes: Nonnegative

    @model_validator(mode="after")
    def monotonic_counters(self) -> Self:
        if (
            self.tx_after_bytes < self.tx_before_bytes
            or self.rx_after_bytes < self.rx_before_bytes
        ):
            raise ValueError("UID counters must be available and monotonic")
        return self


class OfflineReviewEvidence(ReviewRecord):
    schema_version: Literal[1]
    package_id: Annotated[
        str,
        StringConstraints(
            pattern=r"^io\.github\.victorgabillon\.sugarglider\.v2audit[a-z0-9]{1,16}$"
        ),
    ]
    apk_sha256: Sha256
    environment: ReviewEnvironment
    offline_checks: OfflineChecks
    first_party_checks: FirstPartyChecks
    platform_network: UidMeasurement


class OfflineReviewResult(ReviewRecord):
    schema_version: Literal[1] = 1
    offline_functionality: Literal["passed_within_scope", "failed", "not_established"]
    measured_scope: MeasuredScope
    first_party_controls: Literal["passed_within_scope", "failed"]
    failed_offline_checks: tuple[str, ...]
    failed_first_party_checks: tuple[str, ...]
    strict_zero_diagnostic: Literal["passed", "failed"]
    uid_tx_bytes: Nonnegative
    uid_rx_bytes: Nonnegative
    platform_disclosure: Literal["review_required"] = "review_required"
    public_release: Literal["not_authorized"] = "not_authorized"


def assess_offline_review(evidence: OfflineReviewEvidence) -> OfflineReviewResult:
    environment = evidence.environment
    measured_scope: MeasuredScope
    if environment.device_connectivity == "disconnected":
        measured_scope = "device_disconnected"
    elif not environment.internet_permission:
        measured_scope = "research_app_without_internet_permission"
    elif environment.webview_network_loads_blocked:
        measured_scope = "webview_network_loads_blocked"
    elif not environment.region_server_available:
        measured_scope = "region_server_unavailable"
    else:
        measured_scope = "connected_control"
    offline_failures = tuple(
        name
        for name, passed in evidence.offline_checks.model_dump().items()
        if not passed
    )
    first_party_failures = tuple(
        name
        for name, passed in evidence.first_party_checks.model_dump().items()
        if not passed
    )
    network = evidence.platform_network
    tx = network.tx_after_bytes - network.tx_before_bytes
    rx = network.rx_after_bytes - network.rx_before_bytes
    return OfflineReviewResult.model_validate(
        {
            "offline_functionality": (
                "failed"
                if offline_failures
                else "not_established"
                if measured_scope == "connected_control"
                else "passed_within_scope"
            ),
            "measured_scope": measured_scope,
            "first_party_controls": (
                "failed" if first_party_failures else "passed_within_scope"
            ),
            "failed_offline_checks": offline_failures,
            "failed_first_party_checks": first_party_failures,
            "strict_zero_diagnostic": "passed" if tx == rx == 0 else "failed",
            "uid_tx_bytes": tx,
            "uid_rx_bytes": rx,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    path: Path = args.receipt
    if not 1 <= path.stat().st_size <= 65_536:
        parser.error("receipt must contain at most 65,536 bytes of review metadata")
    evidence = OfflineReviewEvidence.model_validate_json(path.read_bytes())
    print(assess_offline_review(evidence).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
