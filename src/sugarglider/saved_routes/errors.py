"""Expected saved-route persistence failures."""


class SavedRouteError(Exception):
    """Base class for safe saved-route failures."""


class SavedRouteNotFoundError(SavedRouteError):
    """An unlisted slug does not identify a stored snapshot."""


class SavedRouteTooLargeError(SavedRouteError):
    """A canonical snapshot exceeds the configured persistence limit."""


class SavedRouteInvalidSnapshotError(SavedRouteError):
    """A request/candidate pair is not a trustworthy canonical snapshot."""


class SavedRouteStorageError(SavedRouteError):
    """The configured snapshot store could not complete an operation."""


class SavedRouteCollisionExhaustedError(SavedRouteStorageError):
    """Bounded public-slug allocation exhausted every retry."""
