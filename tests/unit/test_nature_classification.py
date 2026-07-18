"""Exact, deterministic OSM tag classification for the local nature index."""

import pytest

from sugarglider.nature.classification import (
    AGRICULTURE_TAGS,
    OPEN_NATURAL_TAGS,
    PARK_OR_PROTECTED_TAGS,
    URBAN_TAGS,
    WATER_TAGS,
    WOODLAND_TAGS,
    classify_osm_tags,
    relevant_tags,
)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        *((tag, "woodland") for tag in sorted(WOODLAND_TAGS)),
        *((tag, "open_natural") for tag in sorted(OPEN_NATURAL_TAGS)),
        *((tag, "agriculture") for tag in sorted(AGRICULTURE_TAGS)),
        *((tag, "water") for tag in sorted(WATER_TAGS)),
        *((tag, "urban") for tag in sorted(URBAN_TAGS)),
    ],
)
def test_every_primary_tag_is_accepted(tag: tuple[str, str], expected: str) -> None:
    classification = classify_osm_tags(dict((tag,)))
    assert classification is not None
    assert classification.primary_class == expected
    assert not classification.park_or_protected


@pytest.mark.parametrize("tag", sorted(PARK_OR_PROTECTED_TAGS))
def test_park_and_protection_are_independent(tag: tuple[str, str]) -> None:
    classification = classify_osm_tags(dict((tag,)))
    assert classification is not None
    assert classification.primary_class is None
    assert classification.park_or_protected


@pytest.mark.parametrize(
    "tags",
    [
        {"natural": "woods"},
        {"landuse": "farm"},
        {"leisure": "playground"},
        {"boundary": "administrative"},
        {"waterway": "river"},
        {"amenity": "bicycle_parking"},
    ],
)
def test_near_matches_are_rejected(tags: dict[str, str]) -> None:
    assert classify_osm_tags(tags) is None


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (
            {"landuse": "farmland", "natural": "wood"},
            "woodland",
        ),
        (
            {"landuse": "forest", "natural": "water"},
            "water",
        ),
        (
            {"landuse": "residential", "natural": "water"},
            "urban",
        ),
        (
            {"landuse": "meadow", "amenity": "parking"},
            "urban",
        ),
    ],
)
def test_conflicts_use_fixed_priority(tags: dict[str, str], expected: str) -> None:
    classification = classify_osm_tags(tags)
    assert classification is not None
    assert classification.primary_class == expected


def test_relevant_tags_are_filtered_and_sorted() -> None:
    assert list(
        relevant_tags({"name": "ignored", "natural": "wood", "leisure": "park"}).items()
    ) == [("leisure", "park"), ("natural", "wood")]
