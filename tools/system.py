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
"""

import ctypes
import getpass
import os
import platform
import shutil
import sys
import time


# ============================================================
# MEMORY
# ============================================================

def _get_memory_information():
    """
    Retrieve physical memory information.

    Uses Windows API when available.

    Returns:
        dict
    """

    if os.name != "nt":

        return {
            "total_gb": None,
            "available_gb": None,
            "used_gb": None
        }

    class MEMORYSTATUSEX(
        ctypes.Structure
    ):
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

        result = ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        )

    except Exception:

        return {
            "total_gb": None,
            "available_gb": None,
            "used_gb": None
        }

    if not result:

        return {
            "total_gb": None,
            "available_gb": None,
            "used_gb": None
        }

    total = status.ullTotalPhys
    available = status.ullAvailPhys
    used = total - available

    return {
        "total_gb": round(
            total / (1024 ** 3),
            2
        ),
        "available_gb": round(
            available / (1024 ** 3),
            2
        ),
        "used_gb": round(
            used / (1024 ** 3),
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

    try:

        drive = os.environ.get(
            "SystemDrive",
            "C:"
        )

        total, used, free = (
            shutil.disk_usage(
                drive + "\\"
                if os.name == "nt"
                else "/"
            )
        )

        return {
            "drive": drive,
            "total_gb": round(
                total / (1024 ** 3),
                2
            ),
            "used_gb": round(
                used / (1024 ** 3),
                2
            ),
            "free_gb": round(
                free / (1024 ** 3),
                2
            ),
            "usage_percent": round(
                (used / total) * 100,
                1
            ) if total else None
        }

    except Exception:

        return {
            "drive": None,
            "total_gb": None,
            "used_gb": None,
            "free_gb": None,
            "usage_percent": None
        }


# ============================================================
# UPTIME
# ============================================================

def _get_uptime():
    """
    Retrieve system uptime.

    Uses Windows GetTickCount64 when available.
    """

    if os.name == "nt":

        try:

            milliseconds = (
                ctypes.windll.kernel32.GetTickCount64()
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
# BENVIN DIRECTORY
# ============================================================

def _get_benvin_directory():
    """
    Return the directory containing the running BENVIN
    application.
    """

    try:

        return os.path.abspath(
            os.getcwd()
        )

    except Exception:

        return None


# ============================================================
# USERNAME
# ============================================================

def _get_username():
    """
    Retrieve the current username safely.

    getpass.getuser() is preferred over os.getlogin()
    because it is more reliable when Python is launched
    from terminals, services, remote sessions, or IDEs.
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

    return None


# ============================================================
# SYSTEM INFORMATION
# ============================================================

def get_system_info():
    """
    Retrieve read-only system information.

    Returns:
        dict
    """

    return {
        "operating_system": platform.system(),

        "os_version": platform.version(),

        "architecture": platform.architecture()[0],

        "machine": platform.machine(),

        "processor": (
            platform.processor()
            or "Unknown"
        ),

        "memory": _get_memory_information(),

        "disk": _get_disk_information(),

        "computer_name": (
            platform.node()
            or "Unknown"
        ),

        "username": (
            _get_username()
            or "Unknown"
        ),

        "python_version": (
            sys.version.split()[0]
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

    print("=" * 60)
    print("BENVIN SYSTEM INFORMATION TEST")
    print("=" * 60)

    print()

    information = get_system_info()

    for key, value in information.items():

        print(
            f"{key}: {value}"
        )