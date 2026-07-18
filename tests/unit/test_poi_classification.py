"""Exact scenic, hydration, access, naming, and public-tag classification tests."""

import pytest

from sugarglider.pois.classification import access_status, classify_osm_tags


@pytest.mark.parametrize(
    ("tags", "category", "confidence", "fallback"),
    [
        ({"tourism": "viewpoint"}, "viewpoint", "primary", "Viewpoint"),
        ({"historic": "castle"}, "castle", "primary", "Castle"),
        ({"historic": "ruins"}, "ruins", "primary", "Historic ruins"),
        (
            {"historic": "archaeological_site"},
            "archaeological_site",
            "primary",
            "Archaeological site",
        ),
        (
            {"man_made": "tower", "tower:type": "observation"},
            "observation_tower",
            "primary",
            "Observation tower",
        ),
        (
            {"tourism": "attraction"},
            "tourism_attraction",
            "broad",
            "Tourist attraction",
        ),
    ],
)
def test_exact_scenic_categories(
    tags: dict[str, str], category: str, confidence: str, fallback: str
) -> None:
    classification = classify_osm_tags(tags)
    assert classification is not None
    assert classification.category == category
    assert classification.group == "scenic"
    assert classification.scenic_confidence == confidence
    assert classification.display_name == fallback
    assert classification.name_source == "category_fallback"
    assert classification.potability == "not_applicable"


@pytest.mark.parametrize(
    "tags",
    [
        {"tourism": "yes"},
        {"historic": "yes"},
        {"building": "historic"},
        {"man_made": "tower"},
        {"tower:type": "observation"},
    ],
)
def test_broad_or_incomplete_tags_are_not_invented_as_scenic(
    tags: dict[str, str],
) -> None:
    assert classify_osm_tags(tags) is None


@pytest.mark.parametrize(
    "tags",
    [
        {"amenity": "drinking_water"},
        {"man_made": "water_tap", "drinking_water": "yes"},
        {"amenity": "fountain", "drinking_water": "yes"},
        {"natural": "spring", "drinking_water": "yes"},
        {"man_made": "water_well", "drinking_water": "yes"},
        {"amenity": "water_point", "drinking_water": "yes"},
    ],
)
def test_exact_verified_drinking_water_combinations(tags: dict[str, str]) -> None:
    classification = classify_osm_tags(tags)
    assert classification is not None
    assert classification.category == "drinking_water"
    assert classification.group == "hydration"
    assert classification.potability == "verified"
    assert classification.display_name == "Drinking water"


def test_unknown_fountain_and_tap_are_distinct_from_verified_water() -> None:
    fountain = classify_osm_tags({"amenity": "fountain"})
    tap = classify_osm_tags({"man_made": "water_tap"})
    assert fountain is not None and tap is not None
    assert (fountain.category, fountain.potability, fountain.display_name) == (
        "fountain",
        "unknown",
        "Fountain — potability unknown",
    )
    assert (tap.category, tap.potability, tap.display_name) == (
        "water_tap",
        "unknown",
        "Water tap — potability unknown",
    )
    assert fountain.warnings == tap.warnings == ("potability_unknown",)


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"amenity": "fountain", "drinking_water": "unknown"}, "fountain"),
        ({"man_made": "water_tap", "drinking_water": "unknown"}, "water_tap"),
    ],
)
def test_explicit_unknown_fountain_and_tap_are_retained(
    tags: dict[str, str], category: str
) -> None:
    classification = classify_osm_tags(tags)
    assert classification is not None
    assert classification.category == category
    assert classification.potability == "unknown"
    assert classification.warnings == ("potability_unknown",)
    assert ("drinking_water", "unknown") in classification.tags


def test_unrecognized_fountain_potability_is_retained_with_warning() -> None:
    classification = classify_osm_tags(
        {"amenity": "fountain", "drinking_water": "seasonal"}
    )
    assert classification is not None
    assert classification.category == "fountain"
    assert classification.potability == "unknown"
    assert classification.display_name == "Fountain — potability unknown"
    assert classification.warnings == (
        "potability_unknown",
        "potability_value_unrecognized",
    )
    assert ("drinking_water", "seasonal") in classification.tags


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"amenity": "drinking_water", "drinking_water": "no"}, "drinking_water"),
        ({"amenity": "fountain", "drinking_water": "no"}, "fountain"),
        ({"man_made": "water_tap", "drinking_water": "no"}, "water_tap"),
        ({"natural": "spring", "drinking_water": "no"}, "drinking_water"),
    ],
)
def test_explicit_no_is_never_verified(tags: dict[str, str], category: str) -> None:
    classification = classify_osm_tags(tags)
    assert classification is not None
    assert classification.category == category
    assert classification.potability == "non_potable"
    assert "mapped_non_potable" in classification.warnings


def test_untyped_drinking_water_tag_does_not_create_a_source() -> None:
    assert classify_osm_tags({"drinking_water": "yes"}) is None
    assert classify_osm_tags({"drinking_water": "no"}) is None


def test_multiple_matches_use_fixed_priority_and_castle_retains_ruins() -> None:
    verified_viewpoint = classify_osm_tags(
        {
            "tourism": "viewpoint",
            "historic": "castle",
            "amenity": "drinking_water",
        }
    )
    assert verified_viewpoint is not None
    assert verified_viewpoint.category == "drinking_water"
    assert verified_viewpoint.secondary_categories == ("viewpoint", "castle")

    castle = classify_osm_tags(
        {"historic": "castle", "ruins": "yes", "tourism": "attraction"}
    )
    assert castle is not None
    assert castle.category == "castle"
    assert castle.secondary_categories == ("tourism_attraction",)
    assert castle.ruins

    scenic_non_potable = classify_osm_tags(
        {
            "tourism": "viewpoint",
            "amenity": "fountain",
            "drinking_water": "no",
        }
    )
    assert scenic_non_potable is not None
    assert scenic_non_potable.category == "viewpoint"
    assert scenic_non_potable.secondary_categories == ("fountain",)
    assert scenic_non_potable.potability == "non_potable"


@pytest.mark.parametrize("ruins_value", ["yes", "true", "1"])
def test_ruined_castle_metadata_is_independent_of_primary_category(
    ruins_value: str,
) -> None:
    ruined_water = classify_osm_tags(
        {
            "historic": "castle",
            "ruins": ruins_value,
            "amenity": "drinking_water",
        }
    )
    assert ruined_water is not None
    assert ruined_water.category == "drinking_water"
    assert ruined_water.secondary_categories == ("castle",)
    assert ruined_water.ruins


def test_ruins_boolean_does_not_reclassify_ordinary_castles_or_historic_ruins() -> None:
    castle = classify_osm_tags({"historic": "castle"})
    historic_ruins = classify_osm_tags({"historic": "ruins", "ruins": "yes"})
    assert castle is not None and historic_ruins is not None
    assert not castle.ruins
    assert historic_ruins.category == "ruins"
    assert not historic_ruins.ruins


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("yes", "public"),
        ("public", "public"),
        ("no", "private"),
        ("private", "private"),
        ("customers", "restricted"),
        ("permissive", "restricted"),
        ("destination", "restricted"),
        ("delivery", "restricted"),
        ("designated", "restricted"),
        ("forestry", "unknown"),
        ("", "unknown"),
    ],
)
def test_access_status_mapping(value: str, expected: str) -> None:
    tags = {} if not value else {"access": value}
    assert access_status(tags) == expected


def test_unicode_name_and_stable_public_subset_are_preserved() -> None:
    classification = classify_osm_tags(
        {
            "tourism": "viewpoint",
            "name": "Belvédère de l’Étoile",
            "operator": "Ville de Marly-le-Roi",
            "opening_hours": "Mo-Su 08:00-20:00",
            "access": "yes",
            "source": "survey",
            "description": "not public",
        }
    )
    assert classification is not None
    assert classification.display_name == "Belvédère de l’Étoile"
    assert classification.name_source == "name"
    assert classification.tags == (
        ("access", "yes"),
        ("name", "Belvédère de l’Étoile"),
        ("opening_hours", "Mo-Su 08:00-20:00"),
        ("operator", "Ville de Marly-le-Roi"),
        ("tourism", "viewpoint"),
    )
