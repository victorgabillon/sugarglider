"""Backend-neutral routing failures shared by routing consumers."""


class RoutingError(Exception):
    """Base class for expected routing failures."""


class RoutingUnavailableError(RoutingError):
    """The configured routing backend could not be reached."""


class RoutingProfileUnavailableError(RoutingError):
    """A valid public profile is not loaded by the routing backend."""


class RoutingTimeoutError(RoutingError):
    """The configured routing backend exceeded its timeout."""


class RoutingPointError(RoutingError):
    """One or more user or generated points could not be routed."""


class RoutingUpstreamError(RoutingError):
    """The routing backend returned an invalid or unexpected response."""
