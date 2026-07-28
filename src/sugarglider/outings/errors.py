"""Typed outing application errors."""


class OutingError(Exception):
    """Base class for expected outing failures."""


class OutingNotFoundError(OutingError):
    """The outing or supplied capability must remain undisclosed."""


class OutingFullError(OutingError):
    """An authorized join cannot exceed the outing capacity."""


class OutingCandidateInvalidError(OutingError):
    """A copied request/candidate pair failed neutral trust validation."""


class OutingRouteTooLargeError(OutingError):
    """A participant route exceeds the configured persistence bound."""


class OutingStorageError(OutingError):
    """Outing persistence is disabled, unavailable, or corrupt."""


class OutingCollisionExhaustedError(OutingStorageError):
    """Bounded generation could not produce unique public identifiers."""
