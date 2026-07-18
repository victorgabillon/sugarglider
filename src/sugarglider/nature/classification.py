"""Pure deterministic classification of selected OpenStreetMap area tags."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

type PrimaryNatureClass = Literal[
    "woodland",
    "open_natural",
    "agriculture",
    "water",
    "urban",
]

# Developed and water land cover win first so overlapping broad natural or
# agricultural polygons never conceal a more specific mapped primary use.
PRIMARY_CLASS_PRIORITY: tuple[PrimaryNatureClass, ...] = (
    "urban",
    "water",
    "woodland",
    "open_natural",
    "agriculture",
)

WOODLAND_TAGS = frozenset({("natural", "wood"), ("landuse", "forest")})
OPEN_NATURAL_TAGS = frozenset(
    {
        ("natural", "grassland"),
        ("natural", "heath"),
        ("natural", "scrub"),
        ("natural", "fell"),
        ("natural", "wetland"),
        ("natural", "beach"),
        ("landuse", "meadow"),
        ("landuse", "grass"),
    }
)
AGRICULTURE_TAGS = frozenset(
    {
        ("landuse", "farmland"),
        ("landuse", "orchard"),
        ("landuse", "vineyard"),
        ("landuse", "plant_nursery"),
    }
)
WATER_TAGS = frozenset(
    {
        ("natural", "water"),
        ("waterway", "riverbank"),
        ("landuse", "reservoir"),
        ("landuse", "basin"),
    }
)
URBAN_TAGS = frozenset(
    {
        ("landuse", "residential"),
        ("landuse", "commercial"),
        ("landuse", "retail"),
        ("landuse", "industrial"),
        ("landuse", "construction"),
        ("landuse", "brownfield"),
        ("landuse", "landfill"),
        ("landuse", "railway"),
        ("landuse", "garages"),
        ("amenity", "parking"),
    }
)
PARK_OR_PROTECTED_TAGS = frozenset(
    {
        ("leisure", "park"),
        ("leisure", "nature_reserve"),
        ("boundary", "national_park"),
        ("boundary", "protected_area"),
    }
)
RELEVANT_TAG_KEYS = frozenset(
    {
        key
        for key, _value in (
            *WOODLAND_TAGS,
            *OPEN_NATURAL_TAGS,
            *AGRICULTURE_TAGS,
            *WATER_TAGS,
            *URBAN_TAGS,
            *PARK_OR_PROTECTED_TAGS,
        )
    }
)

_PRIMARY_TAGS: dict[PrimaryNatureClass, frozenset[tuple[str, str]]] = {
    "woodland": WOODLAND_TAGS,
    "open_natural": OPEN_NATURAL_TAGS,
    "agriculture": AGRICULTURE_TAGS,
    "water": WATER_TAGS,
    "urban": URBAN_TAGS,
}


@dataclass(frozen=True)
class NatureClassification:
    """Selected primary class plus an independent park/protection overlay."""

    primary_class: PrimaryNatureClass | None
    park_or_protected: bool


def classify_osm_tags(tags: Mapping[str, str]) -> NatureClassification | None:
    """Classify exact accepted OSM tag pairs with the documented fixed priority."""
    tag_pairs = frozenset(tags.items())
    primary = next(
        (
            category
            for category in PRIMARY_CLASS_PRIORITY
            if tag_pairs & _PRIMARY_TAGS[category]
        ),
        None,
    )
    park_or_protected = bool(tag_pairs & PARK_OR_PROTECTED_TAGS)
    if primary is None and not park_or_protected:
        return None
    return NatureClassification(primary, park_or_protected)


def relevant_tags(tags: Mapping[str, str]) -> dict[str, str]:
    """Keep only classification-relevant original tags in stable key order."""
    return {key: tags[key] for key in sorted(tags.keys() & RELEVANT_TAG_KEYS)}
