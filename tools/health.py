"""
BENVIN Computer Health Tool

Provides a read-only health assessment of the computer.

IMPORTANT:

    This module only READS system information.

    It does not:
        - execute shell commands
        - modify files
        - launch applications
        - change system settings
        - automatically repair anything

The executor controls access to this tool.

ARCHITECTURE:

    system.py
        ↓
    actual system measurements
        ↓
    health.py
        ↓
    deterministic health assessment
        ↓
    structured result
        ↓
    executor.py
        ↓
    brain.py
        ↓
    user response
"""

from tools.system import get_system_info


# ============================================================
# HEALTH THRESHOLDS
# ============================================================

# RAM usage:
#
#   < 80%       = HEALTHY
#   80% - 89.99% = WARNING
#   >= 90%      = CRITICAL
#
RAM_WARNING_PERCENT = 80.0
RAM_CRITICAL_PERCENT = 90.0


# System-drive storage usage:
#
#   < 85%       = HEALTHY
#   85% - 89.99% = WARNING
#   >= 90%      = CRITICAL
#
DISK_WARNING_PERCENT = 85.0
DISK_CRITICAL_PERCENT = 90.0


# ============================================================
# STATUS CONSTANTS
# ============================================================

STATUS_HEALTHY = "HEALTHY"
STATUS_WARNING = "WARNING"
STATUS_CRITICAL = "CRITICAL"
STATUS_UNKNOWN = "UNKNOWN"


# ============================================================
# STATUS HELPERS
# ============================================================

def _normalize_usage_percent(value):
    """
    Convert a usage percentage into a safe numeric value.

    Valid values must be between 0 and 100 inclusive.

    Returns:
        float | None
    """

    try:
        usage_percent = float(value)

    except (TypeError, ValueError):
        return None

    # Avoid accepting NaN or infinite values.
    if usage_percent != usage_percent:
        return None

    if usage_percent == float("inf"):
        return None

    if usage_percent == float("-inf"):
        return None

    if usage_percent < 0.0:
        return None

    if usage_percent > 100.0:
        return None

    return round(usage_percent, 2)


def _get_status(
    usage_percent,
    warning_threshold,
    critical_threshold
):
    """
    Determine the health status of a resource.

    Returns:

        HEALTHY
        WARNING
        CRITICAL
        UNKNOWN
    """

    usage_percent = _normalize_usage_percent(
        usage_percent
    )

    if usage_percent is None:
        return STATUS_UNKNOWN

    if usage_percent >= critical_threshold:
        return STATUS_CRITICAL

    if usage_percent >= warning_threshold:
        return STATUS_WARNING

    return STATUS_HEALTHY


# ============================================================
# RAM HEALTH
# ============================================================

def _assess_memory(memory):
    """
    Assess physical memory usage.

    Returns:
        dict
    """

    if not isinstance(memory, dict):

        return {
            "status": STATUS_UNKNOWN,
            "usage_percent": None,
            "total_gb": None,
            "available_gb": None,
            "used_gb": None,
            "message": (
                "RAM usage information is unavailable."
            )
        }

    usage_percent = _normalize_usage_percent(
        memory.get("usage_percent")
    )

    status = _get_status(
        usage_percent,
        RAM_WARNING_PERCENT,
        RAM_CRITICAL_PERCENT
    )

    if status == STATUS_CRITICAL:

        message = (
            "RAM usage is critically high."
        )

    elif status == STATUS_WARNING:

        message = (
            "RAM usage is high."
        )

    elif status == STATUS_HEALTHY:

        message = (
            "RAM usage is within a healthy range."
        )

    else:

        message = (
            "RAM usage could not be determined."
        )

    return {
        "status": status,
        "usage_percent": usage_percent,
        "total_gb": memory.get("total_gb"),
        "available_gb": memory.get("available_gb"),
        "used_gb": memory.get("used_gb"),
        "message": message
    }


# ============================================================
# DISK HEALTH
# ============================================================

def _assess_disk(disk):
    """
    Assess system-drive storage usage.

    Returns:
        dict
    """

    if not isinstance(disk, dict):

        return {
            "status": STATUS_UNKNOWN,
            "drive": None,
            "usage_percent": None,
            "total_gb": None,
            "used_gb": None,
            "free_gb": None,
            "message": (
                "Disk usage information is unavailable."
            )
        }

    usage_percent = _normalize_usage_percent(
        disk.get("usage_percent")
    )

    status = _get_status(
        usage_percent,
        DISK_WARNING_PERCENT,
        DISK_CRITICAL_PERCENT
    )

    if status == STATUS_CRITICAL:

        message = (
            "Disk usage is critically high."
        )

    elif status == STATUS_WARNING:

        message = (
            "Disk usage is high."
        )

    elif status == STATUS_HEALTHY:

        message = (
            "Disk usage is within a healthy range."
        )

    else:

        message = (
            "Disk usage could not be determined."
        )

    return {
        "status": status,
        "drive": disk.get("drive"),
        "usage_percent": usage_percent,
        "total_gb": disk.get("total_gb"),
        "used_gb": disk.get("used_gb"),
        "free_gb": disk.get("free_gb"),
        "message": message
    }


# ============================================================
# OVERALL HEALTH
# ============================================================

def _calculate_overall_status(
    memory_status,
    disk_status
):
    """
    Calculate the overall computer health.

    Priority:

        CRITICAL > WARNING > HEALTHY

    UNKNOWN does not override a known problem.

    Examples:

        HEALTHY + HEALTHY
            -> HEALTHY

        WARNING + HEALTHY
            -> WARNING

        CRITICAL + HEALTHY
            -> CRITICAL

        WARNING + CRITICAL
            -> CRITICAL

        UNKNOWN + HEALTHY
            -> HEALTHY

        UNKNOWN + WARNING
            -> WARNING

        UNKNOWN + CRITICAL
            -> CRITICAL

        UNKNOWN + UNKNOWN
            -> UNKNOWN
    """

    statuses = [
        memory_status,
        disk_status
    ]

    if STATUS_CRITICAL in statuses:
        return STATUS_CRITICAL

    if STATUS_WARNING in statuses:
        return STATUS_WARNING

    if STATUS_HEALTHY in statuses:
        return STATUS_HEALTHY

    return STATUS_UNKNOWN


# ============================================================
# ASSESSMENT COMPLETENESS
# ============================================================

def _calculate_completeness(
    memory_status,
    disk_status
):
    """
    Determine whether all monitored resources were assessed.

    Returns:

        COMPLETE
        PARTIAL
        UNAVAILABLE
    """

    statuses = [
        memory_status,
        disk_status
    ]

    known_count = sum(
        status != STATUS_UNKNOWN
        for status in statuses
    )

    if known_count == len(statuses):
        return "COMPLETE"

    if known_count > 0:
        return "PARTIAL"

    return "UNAVAILABLE"


# ============================================================
# RECOMMENDATIONS
# ============================================================

def _build_recommendations(
    memory_assessment,
    disk_assessment
):
    """
    Build informational recommendations from actual
    health results.

    This function never performs any action.
    """

    recommendations = []

    memory_status = memory_assessment.get(
        "status"
    )

    disk_status = disk_assessment.get(
        "status"
    )

    # --------------------------------------------------------
    # DISK
    # --------------------------------------------------------

    if disk_status == STATUS_CRITICAL:

        recommendations.append(
            "Free up disk space as soon as practical."
        )

    elif disk_status == STATUS_WARNING:

        recommendations.append(
            "Consider freeing up disk space soon."
        )

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    if memory_status == STATUS_CRITICAL:

        recommendations.append(
            "Close unnecessary applications and investigate "
            "memory-heavy processes."
        )

    elif memory_status == STATUS_WARNING:

        recommendations.append(
            "Consider closing unnecessary applications if "
            "the computer feels slow."
        )

    # --------------------------------------------------------
    # INCOMPLETE DATA
    # --------------------------------------------------------

    completeness = _calculate_completeness(
        memory_status,
        disk_status
    )

    if completeness == "PARTIAL":

        recommendations.append(
            "Some monitored system information was unavailable."
        )

    elif completeness == "UNAVAILABLE":

        recommendations.append(
            "No monitored system resources could be assessed."
        )

    # --------------------------------------------------------
    # HEALTHY
    # --------------------------------------------------------

    if not recommendations:

        recommendations.append(
            "No immediate action is recommended based on "
            "the monitored resources."
        )

    return recommendations


# ============================================================
# PRIORITY
# ============================================================

def _calculate_priority(
    overall_status
):
    """
    Convert overall health status into a simple priority.

    Returns:

        HIGH
        MEDIUM
        LOW
        UNKNOWN
    """

    if overall_status == STATUS_CRITICAL:
        return "HIGH"

    if overall_status == STATUS_WARNING:
        return "MEDIUM"

    if overall_status == STATUS_HEALTHY:
        return "LOW"

    return STATUS_UNKNOWN


# ============================================================
# COMPUTER HEALTH
# ============================================================

def get_system_health():
    """
    Retrieve current system information and produce a
    read-only computer health assessment.

    All measurements come from system.py.

    No system modifications are performed.

    Returns:
        dict
    """

    try:

        system_info = get_system_info()

    except Exception:

        return {
            "success": False,
            "error": (
                "Could not retrieve system information."
            )
        }

    if not isinstance(
        system_info,
        dict
    ):

        return {
            "success": False,
            "error": (
                "System information returned an invalid result."
            )
        }

    memory = system_info.get(
        "memory"
    )

    disk = system_info.get(
        "disk"
    )

    memory_assessment = _assess_memory(
        memory
    )

    disk_assessment = _assess_disk(
        disk
    )

    memory_status = memory_assessment.get(
        "status"
    )

    disk_status = disk_assessment.get(
        "status"
    )

    overall_status = _calculate_overall_status(
        memory_status,
        disk_status
    )

    completeness = _calculate_completeness(
        memory_status,
        disk_status
    )

    priority = _calculate_priority(
        overall_status
    )

    recommendations = _build_recommendations(
        memory_assessment,
        disk_assessment
    )

    return {
        "success": True,

        "overall_status": overall_status,

        "assessment_completeness": completeness,

        "priority": priority,

        "memory": memory_assessment,

        "disk": disk_assessment,

        "recommendations": recommendations
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    import json

    print("=" * 60)
    print("BENVIN COMPUTER HEALTH TEST")
    print("=" * 60)

    print()

    health = get_system_health()

    print(
        json.dumps(
            health,
            indent=2,
            ensure_ascii=False
        )
    )