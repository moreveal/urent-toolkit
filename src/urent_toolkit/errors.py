class UrentError(RuntimeError):
    """Base error raised by Urent Toolkit."""


class AuthenticationError(UrentError):
    """Raised when an authentication stage cannot be completed."""


class ConfigurationError(UrentError):
    """Raised when required configuration is missing or invalid."""
