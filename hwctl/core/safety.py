"""Safety, validation, and rollback management for hardware interactions.

Prevents out-of-bound configurations, maintains rollback state, and registers
emergency failsafes to guarantee hardware remains protected.
"""

import atexit
from datetime import datetime, timezone
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

from hwctl.core.exceptions import InvalidParameterError, SafetyViolationError
from hwctl.core.logger import audit_logger


class SafetyGuard:
    """Enforces parameter bounds and operating guardrails."""

    MIN_FAN_PERCENT = 0.0
    MAX_FAN_PERCENT = 100.0
    MAX_TEST_DURATION_SECONDS = 300.0  # 5 minutes absolute cap
    MIN_STEP_DURATION_SECONDS = 1.0

    @classmethod
    def validate_fan_percent(cls, percent: float) -> float:
        """Validates that requested fan percent is within [0.0, 100.0]."""
        if percent is None:
            raise InvalidParameterError("Fan percent cannot be None")
        try:
            val = float(percent)
        except (ValueError, TypeError):
            raise InvalidParameterError(f"Fan percent must be numeric, got: {percent}")

        if val < cls.MIN_FAN_PERCENT or val > cls.MAX_FAN_PERCENT:
            raise SafetyViolationError(
                f"Requested fan speed {val}% is out of safe range [{cls.MIN_FAN_PERCENT}, {cls.MAX_FAN_PERCENT}]."
            )
        return val

    @classmethod
    def validate_duration(cls, seconds: float) -> float:
        """Validates test/hold duration bounds."""
        if seconds is None or seconds < cls.MIN_STEP_DURATION_SECONDS:
            raise InvalidParameterError(
                f"Duration must be at least {cls.MIN_STEP_DURATION_SECONDS} second(s), got: {seconds}"
            )
        if seconds > cls.MAX_TEST_DURATION_SECONDS:
            raise SafetyViolationError(
                f"Duration {seconds}s exceeds maximum safety limit of {cls.MAX_TEST_DURATION_SECONDS}s."
            )
        return seconds


class RollbackManager:
    """Manages reversible state snapshots and executes rollbacks on demand or upon exit."""

    def __init__(self):
        self._initial_state: Optional[Dict[str, Any]] = None
        self._rollback_action: Optional[Callable[[], Any]] = None
        self._lock = threading.Lock()
        self._is_active = False

        # Register exit handler to ensure hardware is never left in an unmanaged state
        atexit.register(self.emergency_rollback)

    def capture_state(self, state: Dict[str, Any], rollback_action: Callable[[], Any]) -> None:
        """Records the initial hardware state and rollback callable prior to mutation."""
        with self._lock:
            if not self._is_active:
                self._initial_state = dict(state)
                self._rollback_action = rollback_action
                self._is_active = True
                audit_logger.log_event(
                    event_type="safety_intervention",
                    tool="rollback_manager.capture_state",
                    parameters={"captured_state": self._initial_state},
                )

    def execute_rollback(self) -> bool:
        """Restores the initial hardware state."""
        with self._lock:
            if not self._is_active or self._rollback_action is None:
                return False

            try:
                self._rollback_action()
                audit_logger.log_event(
                    event_type="safety_intervention",
                    tool="rollback_manager.execute_rollback",
                    parameters={"restored_state": self._initial_state},
                    result={"success": True},
                )
                self._is_active = False
                self._initial_state = None
                self._rollback_action = None
                return True
            except Exception as e:
                audit_logger.log_event(
                    event_type="safety_intervention",
                    tool="rollback_manager.execute_rollback",
                    error={"message": str(e)},
                    result={"success": False},
                )
                return False

    def clear(self) -> None:
        """Clears active rollback tracking without reverting (when action is finalized cleanly)."""
        with self._lock:
            self._is_active = False
            self._initial_state = None
            self._rollback_action = None

    def emergency_rollback(self) -> None:
        """Invoked on process exit to guarantee return to default automatic state."""
        if self._is_active:
            sys.stderr.write("[SAFETY] Process terminating with active hardware override. Restoring safe state...\n")
            self.execute_rollback()


class SafetyWatchdog:
    """Background watchdog thread that enforces maximum timeout on manual fan override."""

    def __init__(self, timeout_seconds: float, reset_callback: Callable[[], Any]):
        self.timeout_seconds = timeout_seconds
        self.reset_callback = reset_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        start_time = time.time()
        while not self._stop_event.is_set():
            if time.time() - start_time >= self.timeout_seconds:
                sys.stderr.write(
                    f"[SAFETY WATCHDOG] Override timeout ({self.timeout_seconds}s) reached. Resetting to automatic fan control.\n"
                )
                try:
                    self.reset_callback()
                except Exception as e:
                    sys.stderr.write(f"[SAFETY WATCHDOG] Error during watchdog reset: {e}\n")
                break
            time.sleep(0.5)
