"""
BENVIN System Information Tool

Provides read-only information about the computer.

IMPORTANT:

    This module only READS system information.

    It does not:
        - execute shell commands
        - modify files
        - launch applications
        - change system settings

The executor controls access to this tool.

RESPONSIBILITY:

    This module collects RAW system measurements.

    Health interpretation belongs to:

        tools/health.py

    This separation ensures that system information and
    health assessment have a single, consistent source
    of truth.

FEATURES:

    - Operating system information
    - CPU / processor information
    - RAM information
    - Disk information
    - Computer name
    - Current username
    - Python version
    - System uptime
    - BENVIN directory

SECURITY:

    This tool is strictly read-only.
"""


# ============================================================
# IMPORTS
# ============================================================

import ctypes
import getpass
import os
import platform
import shutil
import sys
import time


# ============================================================
# CONSTANTS
# ============================================================

BYTES_PER_GB = 1024 ** 3


# ============================================================
# MEMORY
# ============================================================

def _get_memory_information():
    """
    Retrieve physical memory information.

    Uses the Windows GlobalMemoryStatusEx API when
    running on Windows.

    Returns:
        dict
    """

    empty_result = {
        "total_gb": None,
        "available_gb": None,
        "used_gb": None,
        "usage_percent": None
    }

    if os.name != "nt":
        return empty_result

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            (
                "dwLength",
                ctypes.c_ulong
            ),
            (
                "dwMemoryLoad",
                ctypes.c_ulong
            ),
            (
                "ullTotalPhys",
                ctypes.c_ulonglong
            ),
            (
                "ullAvailPhys",
                ctypes.c_ulonglong
            ),
            (
                "ullTotalPageFile",
                ctypes.c_ulonglong
            ),
            (
                "ullAvailPageFile",
                ctypes.c_ulonglong
            ),
            (
                "ullTotalVirtual",
                ctypes.c_ulonglong
            ),
            (
                "ullAvailVirtual",
                ctypes.c_ulonglong
            ),
            (
                "ullAvailExtendedVirtual",
                ctypes.c_ulonglong
            )
        ]

    status = MEMORYSTATUSEX()

    status.dwLength = ctypes.sizeof(
        MEMORYSTATUSEX
    )

    try:
        result = (
            ctypes.windll.kernel32
            .GlobalMemoryStatusEx(
                ctypes.byref(status)
            )
        )

    except Exception:
        return empty_result

    if not result:
        return empty_result

    total = status.ullTotalPhys
    available = status.ullAvailPhys

    if total <= 0:
        return empty_result

    used = total - available

    return {
        "total_gb": round(
            total / BYTES_PER_GB,
            2
        ),

        "available_gb": round(
            available / BYTES_PER_GB,
            2
        ),

        "used_gb": round(
            used / BYTES_PER_GB,
            2
        ),

        "usage_percent": int(
            status.dwMemoryLoad
        )
    }


# ============================================================
# DISK
# ============================================================

def _get_disk_information():
    """
    Retrieve information about the system drive.

    Returns:
        dict
    """

    empty_result = {
        "drive": None,
        "total_gb": None,
        "used_gb": None,
        "free_gb": None,
        "usage_percent": None
    }

    try:

        drive = os.environ.get(
            "SystemDrive",
            "C:"
        )

        root = (
            drive + "\\"
            if os.name == "nt"
            else "/"
        )

        total, used, free = (
            shutil.disk_usage(root)
        )

        usage_percent = (
            round(
                (used / total) * 100,
                1
            )
            if total
            else None
        )

        return {
            "drive": drive,

            "total_gb": round(
                total / BYTES_PER_GB,
                2
            ),

            "used_gb": round(
                used / BYTES_PER_GB,
                2
            ),

            "free_gb": round(
                free / BYTES_PER_GB,
                2
            ),

            "usage_percent": usage_percent
        }

    except Exception:
        return empty_result


# ============================================================
# UPTIME
# ============================================================

def _get_uptime():
    """
    Retrieve system uptime.

    Uses Windows GetTickCount64 when available.

    Returns:
        str | None
    """

    if os.name == "nt":

        try:

            milliseconds = (
                ctypes.windll.kernel32
                .GetTickCount64()
            )

            seconds = int(
                milliseconds / 1000
            )

        except Exception:

            seconds = None

    else:

        try:

            seconds = int(
                time.time()
                - os.stat(
                    "/proc"
                ).st_ctime
            )

        except Exception:

            seconds = None

    if seconds is None:
        return None

    days = seconds // 86400

    seconds %= 86400

    hours = seconds // 3600

    seconds %= 3600

    minutes = seconds // 60

    seconds %= 60

    parts = []

    if days:

        parts.append(
            f"{days}d"
        )

    if hours:

        parts.append(
            f"{hours}h"
        )

    if minutes:

        parts.append(
            f"{minutes}m"
        )

    if not parts:

        parts.append(
            f"{seconds}s"
        )

    return " ".join(
        parts
    )


# ============================================================
# OPERATING SYSTEM
# ============================================================

def _get_operating_system_information():
    """
    Retrieve operating system information.

    Returns:
        dict
    """

    return {
        "name": (
            platform.system()
            or "Unknown"
        ),

        "version": (
            platform.version()
            or "Unknown"
        ),

        "release": (
            platform.release()
            or "Unknown"
        ),

        "architecture": (
            platform.architecture()[0]
            or "Unknown"
        )
    }


# ============================================================
# PROCESSOR
# ============================================================

def _get_processor_information():
    """
    Retrieve processor information.

    Returns:
        dict
    """

    processor = (
        platform.processor()
        or "Unknown"
    )

    machine = (
        platform.machine()
        or "Unknown"
    )

    return {
        "processor": processor,
        "machine": machine
    }


# ============================================================
# COMPUTER NAME
# ============================================================

def _get_computer_name():
    """
    Retrieve the computer name safely.

    Returns:
        str
    """

    try:

        name = platform.node()

        if name:
            return name

    except Exception:
        pass

    try:

        name = os.environ.get(
            "COMPUTERNAME"
        )

        if name:
            return name

    except Exception:
        pass

    return "Unknown"


# ============================================================
# USERNAME
# ============================================================

def _get_username():
    """
    Retrieve the current username safely.

    getpass.getuser() is preferred over os.getlogin()
    because it is more reliable when Python is launched
    from terminals, services, remote sessions, or IDEs.

    Returns:
        str
    """

    try:

        username = getpass.getuser()

        if username:
            return username

    except Exception:
        pass

    try:

        username = os.environ.get(
            "USERNAME"
        )

        if username:
            return username

    except Exception:
        pass

    return "Unknown"


# ============================================================
# BENVIN DIRECTORY
# ============================================================

def _get_benvin_directory():
    """
    Return the directory containing the running BENVIN
    application.

    Returns:
        str | None
    """

    try:

        return os.path.abspath(
            os.getcwd()
        )

    except Exception:

        return None


# ============================================================
# PYTHON
# ============================================================

def _get_python_information():
    """
    Retrieve Python runtime information.

    Returns:
        dict
    """

    return {
        "version": sys.version.split()[0],

        "implementation": (
            platform.python_implementation()
            or "Unknown"
        )
    }


# ============================================================
# SYSTEM INFORMATION
# ============================================================

def get_system_info():
    """
    Retrieve read-only system information.

    This is the main public API used by BENVIN.

    IMPORTANT:

        This function reports raw system measurements.

        It does NOT perform health assessment.

        Health interpretation belongs to tools/health.py.

    Returns:
        dict
    """

    operating_system = (
        _get_operating_system_information()
    )

    processor = (
        _get_processor_information()
    )

    memory = (
        _get_memory_information()
    )

    disk = (
        _get_disk_information()
    )

    python = (
        _get_python_information()
    )

    return {
        "operating_system": operating_system,

        "processor": processor,

        "memory": memory,

        "disk": disk,

        "python": python,

        "computer_name": (
            _get_computer_name()
        ),

        "username": (
            _get_username()
        ),

        "uptime": (
            _get_uptime()
            or "Unknown"
        ),

        "benvin_directory": (
            _get_benvin_directory()
            or "Unknown"
        )
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    import json

    print("=" * 60)
    print("BENVIN SYSTEM INFORMATION TEST")
    print("=" * 60)

    print()

    information = get_system_info()

    print(
        json.dumps(
            information,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print("=" * 60)
    print("SYSTEM INFORMATION TEST COMPLETE")
    print("=" * 60)