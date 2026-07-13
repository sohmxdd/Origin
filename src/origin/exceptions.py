"""Custom structured exceptions for Origin."""

class OriginError(Exception):
    """Base exception for all Origin errors."""
    pass


class WorkspaceAlreadyInitializedError(OriginError):
    """Raised when trying to initialize a workspace that already has a .origin folder."""
    pass


class WorkspaceNotInitializedError(OriginError):
    """Raised when performing operations in a directory without a initialized .origin folder."""
    pass


class DecisionNotFoundError(OriginError):
    """Raised when a specified decision ID cannot be found."""
    pass


class DecisionNotActiveError(OriginError):
    """Raised when attempting to supersede a decision that is not currently active."""
    pass


class InvalidArtifactError(OriginError):
    """Raised when artifact validation fails."""
    pass
