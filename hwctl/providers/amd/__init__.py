"""AMD GPU providers."""

from hwctl.providers.amd.linux import AmdLinuxProvider
from hwctl.providers.amd.provider import AmdGpuProvider

__all__ = ["AmdGpuProvider", "AmdLinuxProvider"]
