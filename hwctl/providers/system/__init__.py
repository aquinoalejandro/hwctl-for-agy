"""System providers for host telemetry."""

from hwctl.providers.system.linux import LinuxSystemProvider
from hwctl.providers.system.windows import WindowsSystemProvider

__all__ = ["WindowsSystemProvider", "LinuxSystemProvider"]
