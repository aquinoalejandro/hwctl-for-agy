"""Low-level ctypes bindings for AMD Display Library (ADL).

Maps functions and structures from atiadlxx.dll (64-bit) / atiadlxy.dll (32-bit).
Covers Polaris (RX 470/480/570/580) Overdrive 5, Overdrive 6, and OverdriveN interfaces.
"""

import ctypes
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    c_int,
    c_void_p,
    cast,
    create_string_buffer,
    sizeof,
)
import os
import platform
import sys
from typing import Optional

# ADL Constants
ADL_OK = 0
ADL_ERR = -1
ADL_ERR_NOT_INIT = -2
ADL_ERR_INVALID_PARAM = -3
ADL_ERR_INVALID_PARAM_SIZE = -4
ADL_ERR_INVALID_ADL_IDX = -5
ADL_ERR_NOT_SUPPORTED = -8

# Fan control modes & flags
ADL_DL_FANCTRL_SPEED_TYPE_PERCENT = 1
ADL_DL_FANCTRL_SPEED_TYPE_RPM = 2
ADL_DL_FANCTRL_FLAG_USER_DEFINED_SPEED = 1

# OverdriveN temperature types
ADL_ODN_TEMPERATURE_CORE = 1
ADL_ODN_TEMPERATURE_HOTSPOT = 2

# Memory allocation callback type expected by ADL
ADL_MAIN_MALLOC_CALLBACK = ctypes.CFUNCTYPE(c_void_p, c_int)


class AdapterInfo(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iAdapterIndex", c_int),
        ("strUDID", c_char * 256),
        ("iBusNumber", c_int),
        ("iDeviceNumber", c_int),
        ("iFunctionNumber", c_int),
        ("iVendorID", c_int),
        ("strAdapterName", c_char * 256),
        ("strDisplayName", c_char * 256),
        ("iPresent", c_int),
        ("iExist", c_int),
        ("strDriverPath", c_char * 256),
        ("strDriverPathExt", c_char * 256),
        ("strPNPString", c_char * 256),
        ("iOSDisplayIndex", c_int),
    ]


class ADLTemperature(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iTemperature", c_int),  # in millidegrees Celsius
    ]


class ADLPMActivity(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iEngineClock", c_int),  # in 10 kHz
        ("iMemoryClock", c_int),  # in 10 kHz
        ("iVddc", c_int),         # in mV
        ("iActivityPercent", c_int),
        ("iCurrentPerformanceLevel", c_int),
        ("iCurrentBusSpeed", c_int),
        ("iCurrentBusLanes", c_int),
        ("iMaximumBusLanes", c_int),
        ("iReserved", c_int),
    ]


class ADLFanSpeedValue(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iSpeedType", c_int),  # 1 = %, 2 = RPM
        ("iFanSpeed", c_int),
        ("iFlags", c_int),
    ]


class ADLFanSpeedInfo(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iFlags", c_int),
        ("iMinPercent", c_int),
        ("iMaxPercent", c_int),
        ("iMinRPM", c_int),
        ("iMaxRPM", c_int),
    ]


class ADLBiosInfo(Structure):
    _fields_ = [
        ("strPartNumber", c_char * 256),
        ("strVersion", c_char * 256),
        ("strDate", c_char * 256),
    ]


class ADLODNFanControl(Structure):
    _fields_ = [
        ("iMode", c_int),             # 1 = auto, 2 = manual
        ("iFanSpeed", c_int),
        ("iTargetFanSpeed", c_int),
        ("iCurrentFanSpeed", c_int),
        ("iCurrentFanMode", c_int),
        ("iMinFanLimit", c_int),
        ("iTargetTemperature", c_int),
    ]


def _adl_malloc(size: int) -> c_void_p:
    """Default memory allocator callback using msvcrt malloc."""
    msvcrt = ctypes.cdll.msvcrt
    msvcrt.malloc.restype = c_void_p
    msvcrt.malloc.argtypes = [ctypes.c_size_t]
    return msvcrt.malloc(size)


ADL_MALLOC_CB = ADL_MAIN_MALLOC_CALLBACK(_adl_malloc)


class AdlLibrary:
    """Wrapper that dynamically loads and binds to atiadlxx.dll / atiadlxy.dll."""

    def __init__(self):
        self._dll: Optional[ctypes.CDLL] = None
        self._initialized = False

    def load(self) -> bool:
        """Attempts to load atiadlxx.dll (64-bit) or atiadlxy.dll (32-bit)."""
        dll_names = ["atiadlxx.dll", "atiadlxy.dll"] if platform.architecture()[0] == "64bit" else ["atiadlxy.dll"]

        for name in dll_names:
            try:
                self._dll = ctypes.cdll.LoadLibrary(name)
                return True
            except OSError:
                continue
        return False

    def is_loaded(self) -> bool:
        return self._dll is not None

    def initialize(self) -> int:
        """Calls ADL_Main_Control_Create."""
        if not self._dll:
            return ADL_ERR_NOT_INIT

        func = getattr(self._dll, "ADL_Main_Control_Create", None)
        if not func:
            return ADL_ERR

        func.restype = c_int
        func.argtypes = [ADL_MAIN_MALLOC_CALLBACK, c_int]
        res = func(ADL_MALLOC_CB, 1)
        if res == ADL_OK:
            self._initialized = True
        return res

    def destroy(self) -> int:
        """Calls ADL_Main_Control_Destroy."""
        if self._dll and self._initialized:
            func = getattr(self._dll, "ADL_Main_Control_Destroy", None)
            if func:
                func.restype = c_int
                func.argtypes = []
                res = func()
                self._initialized = False
                return res
        return ADL_OK

    def get_number_of_adapters(self) -> tuple[int, int]:
        """Returns (status, num_adapters)."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, 0
        func = getattr(self._dll, "ADL_Adapter_NumberOfAdapters_Get", None)
        if not func:
            return ADL_ERR, 0

        func.restype = c_int
        num = c_int(0)
        func.argtypes = [POINTER(c_int)]
        res = func(byref(num))
        return res, num.value

    def get_adapter_info(self, num_adapters: int) -> tuple[int, list[AdapterInfo]]:
        """Returns (status, list[AdapterInfo])."""
        if not self._dll or num_adapters <= 0:
            return ADL_ERR_NOT_INIT, []

        func = getattr(self._dll, "ADL_Adapter_AdapterInfo_Get", None)
        if not func:
            return ADL_ERR, []

        array_type = AdapterInfo * num_adapters
        adapters = array_type()
        for i in range(num_adapters):
            adapters[i].iSize = sizeof(AdapterInfo)

        func.restype = c_int
        func.argtypes = [POINTER(AdapterInfo), c_int]
        res = func(cast(adapters, POINTER(AdapterInfo)), sizeof(AdapterInfo) * num_adapters)
        return res, list(adapters)

    def get_temperature(self, adapter_index: int) -> tuple[int, float]:
        """Gets core temperature in Celsius via Overdrive 5."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, 0.0

        func = getattr(self._dll, "ADL_Overdrive5_Temperature_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, 0.0

        temp = ADLTemperature()
        temp.iSize = sizeof(ADLTemperature)
        func.restype = c_int
        func.argtypes = [c_int, c_int, POINTER(ADLTemperature)]
        res = func(adapter_index, 0, byref(temp))
        return res, temp.iTemperature / 1000.0

    def get_activity(self, adapter_index: int) -> tuple[int, Optional[ADLPMActivity]]:
        """Gets current clocks, activity % and voltage via Overdrive 5."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, None

        func = getattr(self._dll, "ADL_Overdrive5_CurrentActivity_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, None

        act = ADLPMActivity()
        act.iSize = sizeof(ADLPMActivity)
        func.restype = c_int
        func.argtypes = [c_int, POINTER(ADLPMActivity)]
        res = func(adapter_index, byref(act))
        return res, act

    def get_fan_speed_info(self, adapter_index: int) -> tuple[int, Optional[ADLFanSpeedInfo]]:
        """Gets min/max RPM and percent limits."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, None

        func = getattr(self._dll, "ADL_Overdrive5_FanSpeedInfo_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, None

        info = ADLFanSpeedInfo()
        info.iSize = sizeof(ADLFanSpeedInfo)
        func.restype = c_int
        func.argtypes = [c_int, c_int, POINTER(ADLFanSpeedInfo)]
        res = func(adapter_index, 0, byref(info))
        return res, info

    def get_fan_speed(self, adapter_index: int, speed_type: int) -> tuple[int, int]:
        """Gets fan speed (speed_type: 1 = %, 2 = RPM)."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, 0

        func = getattr(self._dll, "ADL_Overdrive5_FanSpeed_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, 0

        val = ADLFanSpeedValue()
        val.iSize = sizeof(ADLFanSpeedValue)
        val.iSpeedType = speed_type
        func.restype = c_int
        func.argtypes = [c_int, c_int, POINTER(ADLFanSpeedValue)]
        res = func(adapter_index, 0, byref(val))
        return res, val.iFanSpeed

    def set_fan_speed_percent(self, adapter_index: int, percent: int) -> int:
        """Sets fan speed percentage (0-100) via Overdrive 5."""
        if not self._dll:
            return ADL_ERR_NOT_INIT

        func = getattr(self._dll, "ADL_Overdrive5_FanSpeed_Set", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED

        val = ADLFanSpeedValue()
        val.iSize = sizeof(ADLFanSpeedValue)
        val.iSpeedType = ADL_DL_FANCTRL_SPEED_TYPE_PERCENT
        val.iFanSpeed = int(percent)
        val.iFlags = ADL_DL_FANCTRL_FLAG_USER_DEFINED_SPEED

        func.restype = c_int
        func.argtypes = [c_int, c_int, POINTER(ADLFanSpeedValue)]
        return func(adapter_index, 0, byref(val))

    def reset_fan_speed(self, adapter_index: int) -> int:
        """Resets fan speed back to automatic driver control."""
        if not self._dll:
            return ADL_ERR_NOT_INIT

        func = getattr(self._dll, "ADL_Overdrive5_FanSpeedToDefault_Set", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED

        func.restype = c_int
        func.argtypes = [c_int, c_int]
        return func(adapter_index, 0)

    def get_power(self, adapter_index: int) -> tuple[int, float]:
        """Gets current power in Watts via Overdrive 6 if supported."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, 0.0

        func = getattr(self._dll, "ADL_Overdrive6_CurrentPower_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, 0.0

        power = c_int(0)
        func.restype = c_int
        func.argtypes = [c_int, c_int, POINTER(c_int)]
        res = func(adapter_index, 0, byref(power))
        # Value is typically reported in units or Watts (or 100 * Watts)
        return res, float(power.value) / 100.0 if power.value > 1000 else float(power.value)

    def get_bios_info(self, adapter_index: int) -> tuple[int, Optional[ADLBiosInfo]]:
        """Gets VBIOS part number, version and date."""
        if not self._dll:
            return ADL_ERR_NOT_INIT, None

        func = getattr(self._dll, "ADL_Adapter_VideoBiosInfo_Get", None)
        if not func:
            return ADL_ERR_NOT_SUPPORTED, None

        bios = ADLBiosInfo()
        func.restype = c_int
        func.argtypes = [c_int, POINTER(ADLBiosInfo)]
        res = func(adapter_index, byref(bios))
        return res, bios
