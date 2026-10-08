"""Data models and schemas for hwctl.

All models provide deterministic dictionary serialization for JSON emission.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def current_iso_timestamp() -> str:
    """Returns current UTC ISO-8601 formatted timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FanStatus:
    """Current fan metrics and control state."""
    target_percent: Optional[float] = None
    current_percent: Optional[float] = None
    rpm: Optional[int] = None
    control_mode: str = "unknown"  # "auto", "manual", "unknown"
    min_percent: float = 0.0
    max_percent: float = 100.0
    min_rpm: Optional[int] = None
    max_rpm: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class GpuSensors:
    """Real-time sensor readings for a GPU."""
    temperature_c: Optional[float] = None
    hotspot_c: Optional[float] = None
    usage_percent: Optional[float] = None
    vram_usage_percent: Optional[float] = None
    vram_used_mb: Optional[float] = None
    power_w: Optional[float] = None
    core_clock_mhz: Optional[float] = None
    memory_clock_mhz: Optional[float] = None
    voltage_mv: Optional[float] = None
    fan: FanStatus = field(default_factory=FanStatus)
    timestamp: str = field(default_factory=current_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Clean top-level None values
        cleaned = {k: v for k, v in data.items() if v is not None and k != "fan"}
        cleaned["fan"] = self.fan.to_dict()
        return cleaned


@dataclass
class GpuInfo:
    """Static or semi-static GPU hardware identification and capabilities."""
    adapter_index: int = 0
    vendor: str = "AMD"
    model: str = "Unknown"
    sub_vendor: Optional[str] = None
    vram_mb: Optional[int] = None
    driver_version: Optional[str] = None
    driver_date: Optional[str] = None
    vbios_version: Optional[str] = None
    device_id: Optional[str] = None
    power_limit_w: Optional[float] = None
    thermal_limit_c: Optional[float] = None
    is_primary: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ProcessInfo:
    """Information on running process of interest (e.g. GPU monitoring or heavy loads)."""
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    is_hardware_tool: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemInfo:
    """Operating system and host hardware overview."""
    os_name: str
    os_version: str
    os_build: str
    cpu_model: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    ram_total_mb: float
    ram_available_mb: float
    motherboard_vendor: Optional[str] = None
    motherboard_product: Optional[str] = None
    relevant_processes: List[ProcessInfo] = field(default_factory=list)
    timestamp: str = field(default_factory=current_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["relevant_processes"] = [p if isinstance(p, dict) else p.to_dict() for p in self.relevant_processes]
        return d


@dataclass
class ActionResult:
    """Standardized result returned by any hardware action."""
    success: bool
    action: str
    timestamp: str = field(default_factory=current_iso_timestamp)
    requested_percent: Optional[float] = None
    reported_percent: Optional[float] = None
    reported_rpm: Optional[int] = None
    temperature_c: Optional[float] = None
    hotspot_c: Optional[float] = None
    power_w: Optional[float] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "timestamp": self.timestamp,
        }
        if self.requested_percent is not None:
            result["requested_percent"] = self.requested_percent
        if self.reported_percent is not None:
            result["reported_percent"] = self.reported_percent
        if self.reported_rpm is not None:
            result["reported_rpm"] = self.reported_rpm
        if self.temperature_c is not None:
            result["temperature_c"] = self.temperature_c
        if self.hotspot_c is not None:
            result["hotspot_c"] = self.hotspot_c
        if self.power_w is not None:
            result["power_w"] = self.power_w
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class TestStepResult:
    """Result of a single step within a controlled experiment."""
    step_index: int
    target_percent: float
    hold_duration_seconds: float
    initial_sensors: GpuSensors
    final_sensors: GpuSensors
    samples: List[GpuSensors] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "target_percent": self.target_percent,
            "hold_duration_seconds": self.hold_duration_seconds,
            "initial_sensors": self.initial_sensors.to_dict(),
            "final_sensors": self.final_sensors.to_dict(),
            "samples_count": len(self.samples),
            "samples": [s.to_dict() for s in self.samples],
        }


@dataclass
class ControlledTestResult:
    """Aggregate result of a controlled multi-step test."""
    success: bool
    test_name: str
    start_time: str
    end_time: str
    restored_original_state: bool
    steps: List[TestStepResult] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "test_name": self.test_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "restored_original_state": self.restored_original_state,
            "steps": [s.to_dict() for s in self.steps],
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class EnvironmentHealth:
    """Readiness and permission checks of the host environment."""
    is_admin: bool
    adl_available: bool
    opencl_available: bool
    active_gpu_vendor: str
    conflicting_processes: List[str]
    notes: List[str]
    timestamp: str = field(default_factory=current_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ThermalSample:
    """Time-series sensor point during a thermal stress test."""
    elapsed_seconds: float
    temperature_c: Optional[float]
    hotspot_c: Optional[float]
    rpm: Optional[int]
    fan_percent: Optional[float]
    usage_percent: Optional[float]
    power_w: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ThermalStressResult:
    """Outcome of a controlled thermal load test."""
    success: bool
    duration_seconds: float
    aborted_by_safety: bool
    abort_reason: Optional[str]
    samples: List[ThermalSample] = field(default_factory=list)
    initial_temperature: Optional[float] = None
    final_temperature: Optional[float] = None
    peak_temperature: Optional[float] = None
    initial_rpm: Optional[int] = None
    final_rpm: Optional[int] = None
    peak_rpm: Optional[int] = None
    timestamp: str = field(default_factory=current_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["samples"] = [s if isinstance(s, dict) else s.to_dict() for s in self.samples]
        return d


@dataclass
class SensorTimeSeries:
    """Collection of sensor readings taken at regular intervals over a time window."""
    sample_count: int
    duration_seconds: float
    interval_seconds: float
    samples: List[GpuSensors] = field(default_factory=list)
    statistics: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=current_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "sample_count": self.sample_count,
            "duration_seconds": self.duration_seconds,
            "interval_seconds": self.interval_seconds,
            "samples": [s.to_dict() for s in self.samples],
            "timestamp": self.timestamp,
        }
        if self.statistics:
            d["statistics"] = self.statistics
        return d


@dataclass
class SnapshotComparison:
    """Result of comparing two diagnostic snapshots for temporal anomaly detection."""
    baseline_timestamp: str
    current_timestamp: str
    deltas: Dict[str, Any] = field(default_factory=dict)
    anomalies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_timestamp": self.baseline_timestamp,
            "current_timestamp": self.current_timestamp,
            "deltas": self.deltas,
            "anomalies": self.anomalies,
        }
