"""Strict public outing model tests."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sugarglider.outings.models import (
    OutingCreateRequest,
    OutingJoinRequest,
    OutingParticipantJoined,
    OutingParticipantSnapshot,
    OutingSnapshot,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)
SLUG = "abcdefghijklmnopqrstuv"
PARTICIPANT_ID = "participant_public_id1"
TOKEN = "capability-token-with-at-least-thirty-two-characters"


def test_create_request_trims_bounded_text() -> None:
    request = OutingCreateRequest(
        title="  Forest and gravel day  ",
        participant_display_name="  Victor  ",
        saved_route_slug=SLUG,
    )
    assert request.title == "Forest and gravel day"
    assert request.participant_display_name == "Victor"
    assert request.participant_avatar_key == "blue"


def test_avatar_keys_are_strict_and_backward_compatible() -> None:
    created = OutingCreateRequest(
        title="Forest and gravel day",
        participant_display_name="Victor",
        participant_avatar_key="forest",
        saved_route_slug=SLUG,
    )
    joined = OutingJoinRequest(
        display_name="Élodie",
        avatar_key="mask",
        saved_route_slug=SLUG,
    )
    legacy_join = OutingJoinRequest(
        display_name="Legacy",
        saved_route_slug=SLUG,
    )
    assert created.participant_avatar_key == "forest"
    assert joined.avatar_key == "mask"
    assert legacy_join.avatar_key == "blue"
    with pytest.raises(ValidationError):
        OutingCreateRequest(
            title="Outing",
            participant_display_name="Victor",
            participant_avatar_key="purple",  # type: ignore[arg-type]
            saved_route_slug=SLUG,
        )
    with pytest.raises(ValidationError):
        OutingJoinRequest(
            display_name="Victor",
            avatar_key="unknown",  # type: ignore[arg-type]
            saved_route_slug=SLUG,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "x" * 121),
        ("title", "outing\nsecret"),
        ("title", "outing\u202esecret"),
        ("participant_display_name", " "),
        ("participant_display_name", "x" * 81),
        ("participant_display_name", "name\x7f"),
        ("participant_display_name", "name\u200b"),
        ("saved_route_slug", "short"),
    ],
)
def test_create_request_rejects_invalid_bounded_fields(field: str, value: str) -> None:
    payload = {
        "title": "Outing",
        "participant_display_name": "Victor",
        "saved_route_slug": SLUG,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        OutingCreateRequest.model_validate(payload)


def test_models_reject_unknown_fields_and_schema_versions() -> None:
    with pytest.raises(ValidationError):
        OutingCreateRequest.model_validate(
            {
                "schema_version": 2,
                "title": "Outing",
                "participant_display_name": "Victor",
                "saved_route_slug": SLUG,
            }
        )
    with pytest.raises(ValidationError):
        OutingCreateRequest.model_validate(
            {
                "title": "Outing",
                "participant_display_name": "Victor",
                "saved_route_slug": SLUG,
                "unknown": True,
            }
        )


def test_slug_participant_id_and_token_are_strict() -> None:
    with pytest.raises(ValidationError):
        OutingSnapshot(
            slug="invalid!",
            title="Outing",
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            max_participants=8,
            participants=(),
        )
    with pytest.raises(ValidationError):
        OutingParticipantJoined.model_validate(
            {
                "outing": {
                    "slug": SLUG,
                    "title": "Outing",
                    "created_at": NOW,
                    "expires_at": NOW + timedelta(days=1),
                    "max_participants": 8,
                    "participants": [],
                },
                "participant_id": "short",
                "participant_token": TOKEN,
            }
        )
    with pytest.raises(ValidationError):
        OutingParticipantJoined.model_validate(
            {
                "outing": {
                    "slug": SLUG,
                    "title": "Outing",
                    "created_at": NOW,
                    "expires_at": NOW + timedelta(days=1),
                    "max_participants": 8,
                    "participants": [],
                },
                "participant_id": PARTICIPANT_ID,
                "participant_token": "short",
            }
        )


def test_zero_participant_outing_is_a_normal_public_snapshot() -> None:
    outing = OutingSnapshot(
        slug=SLUG,
        title="Outing",
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
        max_participants=8,
        participants=(),
    )
    assert outing.participants == ()


def test_public_snapshot_models_expose_no_capability_fields() -> None:
    forbidden = {
        "owner_token",
        "join_token",
        "participant_token",
        "owner_token_hash",
        "join_token_hash",
        "participant_token_hash",
    }
    assert forbidden.isdisjoint(OutingSnapshot.model_fields)
    assert forbidden.isdisjoint(OutingParticipantSnapshot.model_fields)
