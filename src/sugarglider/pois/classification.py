"""Exact deterministic classification of supported scenic and hydration OSM tags."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sugarglider.pois.models import (
    AccessStatus,
    NameSource,
    PoiCategory,
    PoiGroup,
    Potability,
    PublicTags,
    ScenicConfidence,
)

CLASSIFIER_VERSION: Literal["1"] = "1"

SCENIC_CATEGORY_PRIORITY: tuple[PoiCategory, ...] = (
    "viewpoint",
    "observation_tower",
    "castle",
    "archaeological_site",
    "ruins",
    "tourism_attraction",
)
POI_CATEGORY_PRIORITY: tuple[PoiCategory, ...] = (
    "drinking_water",
    *SCENIC_CATEGORY_PRIORITY,
    "fountain",
    "water_tap",
)

FALLBACK_NAMES: dict[PoiCategory, str] = {
    "viewpoint": "Viewpoint",
    "castle": "Castle",
    "ruins": "Historic ruins",
    "archaeological_site": "Archaeological site",
    "observation_tower": "Observation tower",
    "tourism_attraction": "Tourist attraction",
    "drinking_water": "Drinking water",
    "fountain": "Fountain — potability unknown",
    "water_tap": "Water tap — potability unknown",
}

PUBLIC_TAG_KEYS = frozenset(
    {
        "name",
        "tourism",
        "historic",
        "ruins",
        "man_made",
        "tower:type",
        "amenity",
        "drinking_water",
        "natural",
        "access",
        "fee",
        "opening_hours",
        "seasonal",
        "indoor",
        "bottle",
        "operator",
    }
)

_PUBLIC_ACCESS_VALUES = frozenset({"yes", "public"})
_PRIVATE_ACCESS_VALUES = frozenset({"no", "private"})
_RESTRICTED_ACCESS_VALUES = frozenset(
    {"customers", "permissive", "destination", "delivery", "designated"}
)
_POTABLE_CONTEXTS = (
    ("man_made", "water_tap"),
    ("amenity", "fountain"),
    ("natural", "spring"),
    ("man_made", "water_well"),
    ("amenity", "water_point"),
)
_HYDRATION_CONTEXTS = frozenset(
    {
        ("amenity", "drinking_water"),
        *_POTABLE_CONTEXTS,
    }
)


@dataclass(frozen=True)
class PoiClassification:
    """One primary map class plus explainable secondary and safety metadata."""

    category: PoiCategory
    secondary_categories: tuple[PoiCategory, ...]
    group: PoiGroup
    display_name: str
    name_source: NameSource
    scenic_confidence: ScenicConfidence
    potability: Potability
    access_status: AccessStatus
    ruins: bool
    tags: PublicTags
    warnings: tuple[str, ...]


def classify_osm_tags(tags: Mapping[str, str]) -> PoiClassification | None:
    """Classify only the documented exact OSM combinations and fixed priority."""
    normalized = {key: value.strip() for key, value in tags.items()}
    scenic = _scenic_categories(normalized)
    hydration = _hydration_category(normalized)
    hydration_categories = (hydration[0],) if hydration is not None else ()
    categories = (
        (*hydration_categories, *scenic)
        if hydration is not None and hydration[1] == "verified"
        else (*scenic, *hydration_categories)
    )
    if not categories:
        return None
    category = categories[0]
    secondary = tuple(value for value in categories[1:] if value != category)
    access = access_status(normalized)
    potability = hydration[1] if hydration is not None else "not_applicable"
    scenic_confidence: ScenicConfidence = (
        "primary"
        if any(value != "tourism_attraction" for value in scenic)
        else "broad"
        if scenic
        else "none"
    )
    group: PoiGroup = (
        "hydration"
        if category in {"drinking_water", "fountain", "water_tap"}
        else "scenic"
    )
    supplied_name = normalized.get("name", "").strip()
    name_source: NameSource = "name" if supplied_name else "category_fallback"
    display_name = supplied_name or _fallback_name(category, potability)
    warnings = set[str]()
    if potability == "unknown":
        warnings.add("potability_unknown")
        if normalized.get("drinking_water") not in {None, "unknown"}:
            warnings.add("potability_value_unrecognized")
    elif potability == "non_potable":
        warnings.add("mapped_non_potable")
    if access == "private":
        warnings.add("access_private")
    elif access == "restricted":
        warnings.add("access_restricted")
    return PoiClassification(
        category=category,
        secondary_categories=secondary,
        group=group,
        display_name=display_name,
        name_source=name_source,
        scenic_confidence=scenic_confidence,
        potability=potability,
        access_status=access,
        ruins=(
            normalized.get("historic") == "castle"
            and normalized.get("ruins") in {"yes", "true", "1"}
        ),
        tags=relevant_tags(normalized),
        warnings=tuple(sorted(warnings)),
    )


def access_status(tags: Mapping[str, str]) -> AccessStatus:
    """Map explicit access vocabulary without assuming missing access is public."""
    value = tags.get("access", "").strip().lower()
    if value in _PRIVATE_ACCESS_VALUES:
        return "private"
    if value in _RESTRICTED_ACCESS_VALUES:
        return "restricted"
    if value in _PUBLIC_ACCESS_VALUES:
        return "public"
    return "unknown"


def relevant_tags(tags: Mapping[str, str]) -> PublicTags:
    """Return only the stable, sorted classification and popup tag subset."""
    return tuple((key, tags[key]) for key in sorted(tags.keys() & PUBLIC_TAG_KEYS))


def _scenic_categories(tags: Mapping[str, str]) -> tuple[PoiCategory, ...]:
    matches: set[PoiCategory] = set()
    if tags.get("tourism") == "viewpoint":
        matches.add("viewpoint")
    if tags.get("man_made") == "tower" and tags.get("tower:type") == "observation":
        matches.add("observation_tower")
    historic = tags.get("historic")
    if historic == "castle":
        matches.add("castle")
    elif historic == "archaeological_site":
        matches.add("archaeological_site")
    elif historic == "ruins":
        matches.add("ruins")
    if tags.get("tourism") == "attraction":
        matches.add("tourism_attraction")
    return tuple(
        category for category in SCENIC_CATEGORY_PRIORITY if category in matches
    )


def _hydration_category(
    tags: Mapping[str, str],
) -> tuple[PoiCategory, Potability] | None:
    pairs = frozenset(tags.items())
    potable = tags.get("drinking_water")
    recognized = bool(pairs & _HYDRATION_CONTEXTS)
    if potable == "no":
        if not recognized:
            return None
        return _water_form(tags), "non_potable"
    if tags.get("amenity") == "drinking_water" or (
        potable == "yes" and bool(pairs & frozenset(_POTABLE_CONTEXTS))
    ):
        return "drinking_water", "verified"
    if tags.get("amenity") == "fountain":
        return "fountain", "unknown"
    if tags.get("man_made") == "water_tap":
        return "water_tap", "unknown"
    return None


def _water_form(tags: Mapping[str, str]) -> PoiCategory:
    if tags.get("amenity") == "fountain":
        return "fountain"
    if tags.get("man_made") == "water_tap":
        return "water_tap"
    return "drinking_water"


def _fallback_name(category: PoiCategory, potability: Potability) -> str:
    if potability == "non_potable":
        if category == "fountain":
            return "Fountain — mapped non-potable"
        if category == "water_tap":
            return "Water tap — mapped non-potable"
        return "Water source — mapped non-potable"
    return FALLBACK_NAMES[category]
