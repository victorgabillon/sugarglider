"""Expected failures while building or loading local nature indexes."""


class NatureIndexError(ValueError):
    """Base class for a configured nature index that cannot be used."""


class NatureIndexMissingError(NatureIndexError):
    """The configured index path does not exist."""


class NatureIndexFormatError(NatureIndexError):
    """The index is corrupt, unsupported, or geometrically invalid."""


class NatureIndexBuildError(NatureIndexError):
    """The local OSM source cannot be converted to an index."""
