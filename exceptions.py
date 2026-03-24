"""Custom exception hierarchy for Android MCP Server."""


class ADBError(Exception):
    """Base exception for all ADB-related errors."""
    pass


class DeviceNotFoundError(ADBError):
    """Raised when the specified device is not found or no devices are connected."""
    pass


class ElementNotFoundError(ADBError):
    """Raised when a UI element cannot be found on screen."""
    pass


class ADBTimeoutError(ADBError):
    """Raised when an ADB operation times out."""
    pass


class ADBCommandError(ADBError):
    """Raised when an ADB shell command fails."""
    pass
