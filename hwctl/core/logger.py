"""Structured audit logging for hwctl.

Writes machine-readable JSONL logs to track tool invocations, parameters,
state transitions (before/after), and outcomes.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional


class AuditLogger:
    """Manages audit trail for all hardware queries and mutations."""

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir is None:
            # Default to logs directory relative to current working directory or package
            self.log_dir = Path("logs")
        else:
            self.log_dir = Path(log_dir)

        self.log_file = self.log_dir / "audit_hwctl.jsonl"
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to create log directory {self.log_dir}: {e}\n")

    def log_event(
        self,
        event_type: str,
        tool: str,
        parameters: Optional[Dict[str, Any]] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Appends a structured event entry to the JSONL audit log."""
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,  # "query", "action", "experiment", "safety_intervention"
            "tool": tool,
            "parameters": parameters or {},
        }

        if before_state is not None:
            record["before_state"] = before_state
        if after_state is not None:
            record["after_state"] = after_state
        if result is not None:
            record["result"] = result
        if error is not None:
            record["error"] = error
        if duration_ms is not None:
            record["duration_ms"] = round(duration_ms, 2)

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to write to audit log {self.log_file}: {e}\n")


# Global singleton instance
audit_logger = AuditLogger()
