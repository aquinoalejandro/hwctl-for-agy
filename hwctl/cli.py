"""Command Line Interface for Antigravity AI Agent.

Outputs pure, structured JSON to stdout for predictable agent parsing.
"""

import argparse
import json
import sys
from typing import Any, Dict, List

from hwctl.core.controller import HardwareController


def get_tool_catalog() -> Dict[str, Any]:
    """Self-documenting tool catalog for Antigravity agent discovery."""
    return {
        "tools": [
            {
                "name": "get_system_info",
                "description": "Queries Windows OS, CPU, RAM, motherboard and high-resource/hardware processes.",
                "parameters": {},
            },
            {
                "name": "get_gpu_info",
                "description": "Queries GPU model, vendor, VRAM, driver version, and VBIOS.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "get_gpu_sensors",
                "description": "Reads real-time GPU sensors (temperatures, clocks, fan RPM/%, power, voltage).",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "get_gpu_fan_status",
                "description": "Queries current fan percentage, RPM, min/max capabilities and control state.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "get_gpu_driver_info",
                "description": "Queries driver versions and driver subsystem readiness.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "set_gpu_fan_percent",
                "description": "Sets the GPU fan speed percentage [0.0 - 100.0]. Stores rollback snapshot.",
                "parameters": {
                    "percent": {"type": "number", "description": "Fan percentage (0 to 100)", "required": True},
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0},
                },
            },
            {
                "name": "enable_gpu_manual_fan_control",
                "description": "Locks the GPU fan controller to manual mode.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "disable_gpu_manual_fan_control",
                "description": "Restores the automatic driver/firmware fan curve.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "reset_gpu_fan_control",
                "description": "Failsafe reset of fan control to default automatic state.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "run_fan_test",
                "description": "Executes a multi-step fan test sequence (e.g. 25%, 50%, 75%, 100%) and returns sensor telemetry per step.",
                "parameters": {
                    "steps": {"type": "array", "items": {"type": "number"}, "description": "Percentages list", "default": [25, 50, 75, 100]},
                    "hold": {"type": "number", "description": "Seconds to hold per step", "default": 5.0},
                    "interval": {"type": "number", "description": "Sensor sampling interval in seconds", "default": 1.0},
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0},
                },
            },
            {
                "name": "check_environment",
                "description": "Checks Administrator elevation (UAC), AMD driver DLL presence, OpenCL, and potential conflicting tools (Afterburner, FanControl).",
                "parameters": {},
            },
            {
                "name": "start_gpu_stress",
                "description": "Starts continuous GPU compute load in the background (OpenCL / hardware accelerated) with an auto-timeout safeguard.",
                "parameters": {
                    "duration": {"type": "number", "description": "Max stress duration in seconds (default 30.0)", "default": 30.0}
                },
            },
            {
                "name": "stop_gpu_stress",
                "description": "Stops active background GPU compute stress immediately.",
                "parameters": {},
            },
            {
                "name": "run_thermal_stress_test",
                "description": "Applies GPU load for a specified duration, sampling sensor data continuously. Features an emergency thermal tripwire to abort if temperatures exceed limits.",
                "parameters": {
                    "duration": {"type": "number", "description": "Duration in seconds (default 20.0)", "default": 20.0},
                    "interval": {"type": "number", "description": "Sampling interval in seconds (default 1.0)", "default": 1.0},
                    "emergency_temp": {"type": "number", "description": "Tripwire abort temperature Celsius (default 90.0)", "default": 90.0},
                    "emergency_hotspot": {"type": "number", "description": "Tripwire abort hotspot Celsius (default 105.0)", "default": 105.0},
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0},
                },
            },
            {
                "name": "create_diagnostic_snapshot",
                "description": "Captures a single synchronized snapshot of system, GPU, sensors, and processes.",
                "parameters": {
                    "adapter": {"type": "integer", "description": "Adapter index (default 0)", "default": 0}
                },
            },
            {
                "name": "create_diagnostic_report",
                "description": "Captures a full diagnostic snapshot and saves it as a JSON file.",
                "parameters": {
                    "output": {"type": "string", "description": "Target file path for JSON report", "required": False}
                },
            },
        ]
    }


def output_json(data: Dict[str, Any]) -> None:
    """Emits clean, formatted JSON to stdout."""
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hwctl",
        description="Hardware Diagnostic and Control Layer for Antigravity AI Agent",
    )

    parser.add_argument(
        "--provider",
        choices=["amd", "nvidia", "intel", "mock"],
        default=None,
        help="Force specific hardware provider (default: auto-detect)",
    )
    parser.add_argument(
        "--mock-fault",
        choices=["none", "stuck_fan", "no_fan_control"],
        default="none",
        help="Simulate specific hardware fault in mock provider mode",
    )
    parser.add_argument(
        "--adapter",
        type=int,
        default=0,
        help="GPU Adapter index (default: 0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Always format output as JSON (default: True)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Hardware action to execute")

    # Command: describe-tools
    subparsers.add_parser("describe-tools", help="List available tools and schemas for AI Agent")

    # Command: get-system-info
    subparsers.add_parser("get-system-info", help="Get host OS, CPU, RAM, and motherboard")

    # Command: get-gpu-info
    subparsers.add_parser("get-gpu-info", help="Get GPU vendor, model, VRAM, and driver")

    # Command: get-gpu-sensors
    subparsers.add_parser("get-gpu-sensors", help="Get real-time GPU sensors (temp, RPM, power)")

    # Command: get-gpu-fan-status
    subparsers.add_parser("get-gpu-fan-status", help="Get fan speed percentage, RPM, and mode")

    # Command: get-gpu-driver-info
    subparsers.add_parser("get-gpu-driver-info", help="Get driver version and readiness")

    # Command: get-gpu-vbios-info
    subparsers.add_parser("get-gpu-vbios-info", help="Get VBIOS version strings")

    # Command: set-gpu-fan-percent
    p_set_fan = subparsers.add_parser("set-gpu-fan-percent", help="Set target fan percentage")
    p_set_fan.add_argument("--percent", type=float, required=True, help="Fan percent (0-100)")

    # Command: enable-gpu-manual-fan-control
    subparsers.add_parser("enable-gpu-manual-fan-control", help="Switch fan to manual mode")

    # Command: disable-gpu-manual-fan-control
    subparsers.add_parser("disable-gpu-manual-fan-control", help="Switch fan to auto mode")

    # Command: reset-gpu-fan-control
    subparsers.add_parser("reset-gpu-fan-control", help="Restore default auto fan curve")

    # Command: run-fan-test
    p_test = subparsers.add_parser("run-fan-test", help="Run multi-step fan response test")
    p_test.add_argument("--steps", type=str, default="25,50,75,100", help="Comma-separated percentages")
    p_test.add_argument("--hold", type=float, default=5.0, help="Hold duration per step in seconds")
    p_test.add_argument("--interval", type=float, default=1.0, help="Sample interval in seconds")

    # Command: check-environment
    subparsers.add_parser("check-environment", help="Check Windows admin privileges, drivers, and conflicting software")

    # Command: start-gpu-stress
    p_stress = subparsers.add_parser("start-gpu-stress", help="Start background GPU compute load")
    p_stress.add_argument("--duration", type=float, default=30.0, help="Max stress duration in seconds")

    # Command: stop-gpu-stress
    subparsers.add_parser("stop-gpu-stress", help="Stop background GPU compute load")

    # Command: run-thermal-stress-test
    p_therm = subparsers.add_parser("run-thermal-stress-test", help="Run controlled thermal stress test with auto-abort tripwire")
    p_therm.add_argument("--duration", type=float, default=20.0, help="Test duration in seconds")
    p_therm.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    p_therm.add_argument("--emergency-temp", type=float, default=90.0, help="Emergency core temperature tripwire in C")
    p_therm.add_argument("--emergency-hotspot", type=float, default=105.0, help="Emergency hotspot temperature tripwire in C")

    # Command: get-kernel-logs
    p_klog = subparsers.add_parser("get-kernel-logs", help="Get kernel dmesg logs for amdgpu driver")
    p_klog.add_argument("--lines", type=int, default=50, help="Max lines to retrieve")

    # Command: create-diagnostic-snapshot
    subparsers.add_parser("create-diagnostic-snapshot", help="Capture complete state snapshot")

    # Command: create-diagnostic-report
    p_report = subparsers.add_parser("create-diagnostic-report", help="Save diagnostic snapshot to file")
    p_report.add_argument("--output", type=str, default=None, help="Target JSON file path")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help(sys.stderr)
        return 1

    if args.command == "describe-tools":
        output_json({"success": True, "action": "describe-tools", "catalog": get_tool_catalog()})
        return 0

    controller = HardwareController(
        provider_name=args.provider,
        mock_fault_mode=args.mock_fault,
    )

    try:
        if args.command == "check-environment":
            res = controller.check_environment()
        elif args.command == "get-kernel-logs":
            res = controller.get_kernel_logs(max_lines=args.lines)
        elif args.command == "start-gpu-stress":
            res = controller.start_gpu_stress(duration_seconds=args.duration)
        elif args.command == "stop-gpu-stress":
            res = controller.stop_gpu_stress()
        elif args.command == "run-thermal-stress-test":
            res = controller.run_thermal_stress_test(
                duration_seconds=args.duration,
                sample_interval_seconds=args.interval,
                emergency_temp_c=args.emergency_temp,
                emergency_hotspot_c=args.emergency_hotspot,
                adapter_index=args.adapter,
            )
        elif args.command == "get-system-info":
            res = controller.get_system_info()
        elif args.command == "get-gpu-info":
            res = controller.get_gpu_info(args.adapter)
        elif args.command == "get-gpu-sensors":
            res = controller.get_gpu_sensors(args.adapter)
        elif args.command == "get-gpu-fan-status":
            res = controller.get_gpu_fan_status(args.adapter)
        elif args.command == "get-gpu-driver-info":
            res = controller.get_gpu_driver_info(args.adapter)
        elif args.command == "get-gpu-vbios-info":
            res = controller.get_gpu_vbios_info(args.adapter)
        elif args.command == "set-gpu-fan-percent":
            res = controller.set_gpu_fan_percent(args.percent, args.adapter)
        elif args.command == "enable-gpu-manual-fan-control":
            res = controller.enable_gpu_manual_fan_control(args.adapter)
        elif args.command == "disable-gpu-manual-fan-control":
            res = controller.disable_gpu_manual_fan_control(args.adapter)
        elif args.command == "reset-gpu-fan-control":
            res = controller.reset_gpu_fan_control(args.adapter)
        elif args.command == "run-fan-test":
            step_list = [float(x.strip()) for x in args.steps.split(",") if x.strip()]
            res = controller.run_fan_test(
                steps=step_list,
                hold_seconds=args.hold,
                sample_interval_seconds=args.interval,
                adapter_index=args.adapter,
            )
        elif args.command == "create-diagnostic-snapshot":
            res = controller.create_diagnostic_snapshot(args.adapter)
        elif args.command == "create-diagnostic-report":
            res = controller.create_diagnostic_report(args.output)
        else:
            res = {"success": False, "error": {"code": "UNKNOWN_COMMAND", "message": f"Unknown command {args.command}"}}

        output_json(res)
        return 0 if res.get("success", False) else 1

    finally:
        controller.shutdown()


if __name__ == "__main__":
    sys.exit(main())
