"""Native GPU stress generator and controlled thermal load experiments.

Leverages OpenCL.dll when available on Windows to generate real compute load
without needing third-party applications (FurMark, games, 3DMark).
Includes an emergency thermal tripwire to protect hardware if temperatures exceed safe limits.
"""

import ctypes
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from hwctl.core.logger import audit_logger
from hwctl.core.models import (
    GpuSensors,
    ThermalSample,
    ThermalStressResult,
    current_iso_timestamp,
)
from hwctl.core.safety import SafetyGuard
from hwctl.providers.base import BaseGpuProvider


class OpenCLStressWorker:
    """Dispatches a continuous compute kernel to place the GPU under load."""

    def __init__(self):
        self._cl = None
        self._ctx = None
        self._queue = None
        self._kernel = None
        self._dev = None
        self._available = False
        self._init_opencl()

    @property
    def is_available(self) -> bool:
        return self._available

    def _init_opencl(self) -> None:
        try:
            cl = ctypes.cdll.LoadLibrary("OpenCL.dll")
            # Bind function prototypes
            cl.clGetPlatformIDs.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
            cl.clGetDeviceIDs.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
            cl.clCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
            cl.clCreateContext.restype = ctypes.c_void_p
            cl.clCreateCommandQueue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_int)]
            cl.clCreateCommandQueue.restype = ctypes.c_void_p
            cl.clCreateProgramWithSource.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_int)]
            cl.clCreateProgramWithSource.restype = ctypes.c_void_p
            cl.clBuildProgram.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p]
            cl.clCreateKernel.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
            cl.clCreateKernel.restype = ctypes.c_void_p
            cl.clEnqueueNDRangeKernel.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
            cl.clFinish.argtypes = [ctypes.c_void_p]

            p = (ctypes.c_void_p * 1)()
            cl.clGetPlatformIDs(1, p, None)
            dev = (ctypes.c_void_p * 1)()
            cl.clGetDeviceIDs(p[0], 0xFFFFFFFF, 1, dev, None)

            err = ctypes.c_int(0)
            ctx = cl.clCreateContext(None, 1, dev, None, None, ctypes.byref(err))
            queue = cl.clCreateCommandQueue(ctx, dev[0], 0, ctypes.byref(err))

            # Stress kernel: arithmetic intensity loop (FMA/sin/cos)
            src = b"""
            __kernel void gpu_stress(__global float *buf) {
                int id = get_global_id(0);
                float x = (float)id * 0.001f;
                for (int i = 0; i < 4000; i++) {
                    x = sin(x) * cos(x) + x * 0.999f;
                }
                buf[id] = x;
            }
            """
            src_p = ctypes.c_char_p(src)
            src_len = ctypes.c_size_t(len(src))
            prog = cl.clCreateProgramWithSource(ctx, 1, ctypes.byref(src_p), ctypes.byref(src_len), ctypes.byref(err))
            cl.clBuildProgram(prog, 1, dev, None, None, None)
            kern = cl.clCreateKernel(prog, b"gpu_stress", ctypes.byref(err))

            self._cl = cl
            self._ctx = ctx
            self._queue = queue
            self._kernel = kern
            self._dev = dev
            self._available = True
        except Exception as e:
            self._available = False

    def execute_burst(self) -> None:
        """Executes a compute burst on the GPU."""
        if not self._available:
            return

        global_work = (ctypes.c_size_t * 1)(65536)
        local_work = (ctypes.c_size_t * 1)(256)
        for _ in range(8):
            self._cl.clEnqueueNDRangeKernel(
                self._queue, self._kernel, 1, None, global_work, local_work, 0, None, None
            )
        self._cl.clFinish(self._queue)


class GpuStressGenerator:
    """Manages background stress thread with auto-timeout safeguards."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._worker = OpenCLStressWorker()
        self._is_running = False

    @property
    def has_hardware_acceleration(self) -> bool:
        return self._worker.is_available

    def is_running(self) -> bool:
        return self._is_running

    def start(self, duration_seconds: float = 30.0) -> None:
        """Starts stress in a background worker with maximum duration timeout."""
        if self._is_running:
            return

        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, args=(duration_seconds,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signals worker to stop immediately."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._is_running = False

    def _run_loop(self, max_duration: float) -> None:
        start_time = time.time()
        try:
            while not self._stop_event.is_set():
                if time.time() - start_time >= max_duration:
                    break

                if self._worker.is_available:
                    self._worker.execute_burst()
                else:
                    # Synthetic fallback: lightweight loop
                    time.sleep(0.01)
        finally:
            self._is_running = False


class ThermalStressExperiment:
    """Executes a controlled thermal stress test.

    Applies load, continuously samples temperatures and fan RPM, and aborts
    immediately if safety thermal thresholds are breached.
    """

    def __init__(self, gpu_provider: BaseGpuProvider, adapter_index: int = 0):
        self.gpu = gpu_provider
        self.adapter_index = adapter_index
        self.stress_gen = GpuStressGenerator()

    def run(
        self,
        duration_seconds: float = 20.0,
        sample_interval_seconds: float = 1.0,
        emergency_temp_c: float = 90.0,
        emergency_hotspot_c: float = 105.0,
    ) -> ThermalStressResult:
        duration = SafetyGuard.validate_duration(duration_seconds)

        # Baseline sample
        baseline = self.gpu.get_gpu_sensors(self.adapter_index)
        initial_temp = baseline.temperature_c
        initial_rpm = baseline.fan.rpm

        samples: List[ThermalSample] = []
        aborted = False
        abort_reason = None

        audit_logger.log_event(
            event_type="experiment",
            tool="thermal_stress_experiment.run",
            parameters={
                "duration_seconds": duration,
                "emergency_temp_c": emergency_temp_c,
                "emergency_hotspot_c": emergency_hotspot_c,
            },
        )

        # Notify mock provider if running in simulation
        if hasattr(self.gpu, "set_simulated_load"):
            self.gpu.set_simulated_load(True)

        self.stress_gen.start(duration_seconds=duration + 5.0)
        start_time = time.time()

        try:
            while (time.time() - start_time) < duration:
                time.sleep(sample_interval_seconds)
                elapsed = round(time.time() - start_time, 2)
                sensors = self.gpu.get_gpu_sensors(self.adapter_index)

                sample = ThermalSample(
                    elapsed_seconds=elapsed,
                    temperature_c=sensors.temperature_c,
                    hotspot_c=sensors.hotspot_c,
                    rpm=sensors.fan.rpm,
                    fan_percent=sensors.fan.current_percent,
                    usage_percent=sensors.usage_percent,
                    power_w=sensors.power_w,
                )
                samples.append(sample)

                # Emergency thermal tripwire
                if sensors.temperature_c and sensors.temperature_c >= emergency_temp_c:
                    aborted = True
                    abort_reason = f"CORE_TEMP_TRIP: {sensors.temperature_c}C >= {emergency_temp_c}C"
                    break

                if sensors.hotspot_c and sensors.hotspot_c >= emergency_hotspot_c:
                    aborted = True
                    abort_reason = f"HOTSPOT_TEMP_TRIP: {sensors.hotspot_c}C >= {emergency_hotspot_c}C"
                    break

        finally:
            self.stress_gen.stop()
            if hasattr(self.gpu, "set_simulated_load"):
                self.gpu.set_simulated_load(False)

            # Ensure fan is restored to auto/safe
            self.gpu.reset_gpu_fan_control(self.adapter_index)

        final_sensors = self.gpu.get_gpu_sensors(self.adapter_index)
        final_temp = final_sensors.temperature_c
        final_rpm = final_sensors.fan.rpm

        temps = [s.temperature_c for s in samples if s.temperature_c is not None]
        rpms = [s.rpm for s in samples if s.rpm is not None]

        result = ThermalStressResult(
            success=not aborted,
            duration_seconds=round(time.time() - start_time, 2),
            aborted_by_safety=aborted,
            abort_reason=abort_reason,
            samples=samples,
            initial_temperature=initial_temp,
            final_temperature=final_temp,
            peak_temperature=max(temps) if temps else initial_temp,
            initial_rpm=initial_rpm,
            final_rpm=final_rpm,
            peak_rpm=max(rpms) if rpms else initial_rpm,
        )

        audit_logger.log_event(
            event_type="experiment",
            tool="thermal_stress_experiment.run",
            result={
                "success": result.success,
                "aborted": aborted,
                "samples_count": len(samples),
                "peak_temperature": result.peak_temperature,
                "peak_rpm": result.peak_rpm,
            },
        )

        return result
