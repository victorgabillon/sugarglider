"""Expected failures while building, loading, or querying local POI indexes."""


class PoiIndexError(ValueError):
    """Base class for a configured POI index that cannot be used."""


class PoiIndexMissingError(PoiIndexError):
    """The configured POI index path does not exist."""


class PoiIndexFormatError(PoiIndexError):
    """The POI index is corrupt, unsupported, or internally inconsistent."""


class PoiIndexBuildError(PoiIndexError):
    """The local OSM source cannot be converted to a POI index."""


class PoiSearchLimitError(ValueError):
    """A POI query exceeds the configured public result limit."""
