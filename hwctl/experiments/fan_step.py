"""Controlled step experiment runner for GPU fans.

Executes a sequence of target fan speeds, holds for specified durations,
and captures sensor telemetry at regular sampling intervals.
Strictly returns empirical data without diagnosing faults.
"""

from datetime import datetime, timezone
import time
from typing import Callable, List, Optional

from hwctl.core.logger import audit_logger
from hwctl.core.models import ControlledTestResult, GpuSensors, TestStepResult, current_iso_timestamp
from hwctl.core.safety import RollbackManager, SafetyGuard, SafetyWatchdog
from hwctl.providers.base import BaseGpuProvider


class FanStepExperiment:
    """Executes fan response curve experiments for consumption by Antigravity."""

    def __init__(
        self,
        gpu_provider: BaseGpuProvider,
        adapter_index: int = 0,
        rollback_manager: Optional[RollbackManager] = None,
    ):
        self.gpu = gpu_provider
        self.adapter_index = adapter_index
        self.rollback = rollback_manager or RollbackManager()

    def run(
        self,
        steps: Optional[List[float]] = None,
        hold_duration_seconds: float = 5.0,
        sample_interval_seconds: float = 1.0,
        restore_on_finish: bool = True,
        on_step_progress: Optional[Callable[[int, int, float], None]] = None,
    ) -> ControlledTestResult:
        """Runs the step experiment.

        Args:
            steps: List of target percentages (e.g. [25.0, 50.0, 75.0, 100.0]).
            hold_duration_seconds: Time in seconds to hold each fan target.
            sample_interval_seconds: Sampling frequency for sensor data during hold.
            restore_on_finish: If True, resets fan control to automatic when done or on error.
            on_step_progress: Optional callback invoked as (current_step, total_steps, target_pct).
        """
        target_steps = steps if steps is not None else [25.0, 50.0, 75.0, 100.0]

        # Validate parameters against safety boundaries
        for s in target_steps:
            SafetyGuard.validate_fan_percent(s)
        SafetyGuard.validate_duration(hold_duration_seconds)

        start_iso = current_iso_timestamp()
        step_results: List[TestStepResult] = []
        restored = False
        error_info = None

        # Capture initial state for rollback
        initial_status = self.gpu.get_gpu_fan_status(self.adapter_index)
        self.rollback.capture_state(
            state={"fan": initial_status.to_dict()},
            rollback_action=lambda: self.gpu.reset_gpu_fan_control(self.adapter_index),
        )

        # Setup safety watchdog (total test timeout + safety buffer)
        total_max_time = (len(target_steps) * hold_duration_seconds) + 15.0
        watchdog = SafetyWatchdog(
            timeout_seconds=total_max_time,
            reset_callback=lambda: self.gpu.reset_gpu_fan_control(self.adapter_index),
        )
        watchdog.start()

        audit_logger.log_event(
            event_type="experiment",
            tool="fan_step_experiment.run",
            parameters={
                "steps": target_steps,
                "hold_duration_seconds": hold_duration_seconds,
                "restore_on_finish": restore_on_finish,
            },
        )

        try:
            total_count = len(target_steps)
            for idx, target_pct in enumerate(target_steps):
                if on_step_progress:
                    on_step_progress(idx + 1, total_count, target_pct)

                # Set target fan percentage
                self.gpu.set_gpu_fan_percent(target_pct, self.adapter_index)
                initial_sensors = self.gpu.get_gpu_sensors(self.adapter_index)

                # Hold and sample sensors
                samples: List[GpuSensors] = []
                elapsed = 0.0
                while elapsed < hold_duration_seconds:
                    sleep_time = min(sample_interval_seconds, hold_duration_seconds - elapsed)
                    time.sleep(sleep_time)
                    elapsed += sleep_time
                    reading = self.gpu.get_gpu_sensors(self.adapter_index)
                    samples.append(reading)

                final_sensors = samples[-1] if samples else initial_sensors

                step_results.append(
                    TestStepResult(
                        step_index=idx + 1,
                        target_percent=target_pct,
                        hold_duration_seconds=hold_duration_seconds,
                        initial_sensors=initial_sensors,
                        final_sensors=final_sensors,
                        samples=samples,
                    )
                )

        except Exception as e:
            error_info = {"type": type(e).__name__, "message": str(e)}
            audit_logger.log_event(
                event_type="experiment",
                tool="fan_step_experiment.run",
                error=error_info,
            )
        finally:
            watchdog.cancel()
            if restore_on_finish:
                self.rollback.execute_rollback()
                restored = True
            else:
                self.rollback.clear()

        end_iso = current_iso_timestamp()

        result = ControlledTestResult(
            success=(error_info is None),
            test_name="gpu_fan_step_test",
            start_time=start_iso,
            end_time=end_iso,
            restored_original_state=restored,
            steps=step_results,
            error=error_info,
        )

        audit_logger.log_event(
            event_type="experiment",
            tool="fan_step_experiment.run",
            result={"success": result.success, "steps_completed": len(step_results)},
        )

        return result
