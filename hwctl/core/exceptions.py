"""Structured error handling for hwctl."""

from typing import Any, Dict, Optional


class HwctlError(Exception):
    """Base exception for all hwctl errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class HardwareNotFoundError(HwctlError):
    """Raised when no compatible hardware or adapter could be identified."""

    def __init__(self, message: str = "Target GPU hardware not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="HARDWARE_NOT_FOUND", details=details)


class DriverError(HwctlError):
    """Raised when the vendor driver DLL or subsystem is missing or inaccessible."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="DRIVER_ERROR", details=details)


class FanControlUnavailableError(HwctlError):
    """Raised when fan control is not exposed or supported by hardware/driver."""

    def __init__(self, message: str = "The GPU does not expose writable fan control", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="FAN_CONTROL_UNAVAILABLE", details=details)


class InvalidParameterError(HwctlError):
    """Raised when input parameters fail validation checks."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="INVALID_PARAMETER", details=details)


class SafetyViolationError(HwctlError):
    """Raised when an operation exceeds safe operating bounds or violates guardrails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="SAFETY_VIOLATION", details=details)


class PermissionDeniedError(HwctlError):
    """Raised when an operation requires administrative elevation or driver permissions."""

    def __init__(self, message: str = "Operation requires administrative privileges", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="PERMISSION_DENIED", details=details)


class ActionTimeoutError(HwctlError):
    """Raised when an action or experiment exceeds the allowed timeout duration."""

    def __init__(self, message: str = "Operation timed out", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="ACTION_TIMEOUT", details=details)


class UnsupportedFeatureError(HwctlError):
    """Raised when a specific feature (like hotspot temp or fan RPM) is unsupported by hardware."""

    def __init__(self, feature_name: str, message: Optional[str] = None):
        msg = message or f"Feature '{feature_name}' is not supported on this device/driver."
        super().__init__(message=msg, code="FEATURE_UNSUPPORTED", details={"feature": feature_name})
