"""
BENVIN Audit Logger

Responsibilities:

    1. Record BENVIN action attempts.
    2. Record validation results.
    3. Record permission decisions.
    4. Record execution results.
    5. Provide a persistent history of actions.
    6. Never execute tools.
    7. Never make authorization decisions.

IMPORTANT:

    The audit logger is observational only.

    It does NOT:
        - authorize actions
        - execute tools
        - modify permissions
        - decide whether an action is safe

It simply records what happened.
"""

import json
import os
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

AUDIT_DIRECTORY = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    ),
    "data"
)

AUDIT_FILE = os.path.join(
    AUDIT_DIRECTORY,
    "audit.json"
)


# ============================================================
# DIRECTORY MANAGEMENT
# ============================================================

def _ensure_audit_directory():
    """
    Ensure the audit data directory exists.
    """

    os.makedirs(
        AUDIT_DIRECTORY,
        exist_ok=True
    )


# ============================================================
# LOAD AUDIT LOG
# ============================================================

def load_audit_log():
    """
    Load the complete audit history.

    Returns:
        list
    """

    _ensure_audit_directory()

    if not os.path.exists(
        AUDIT_FILE
    ):
        return []

    try:

        with open(
            AUDIT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            list
        ):
            return []

        return data

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError
    ):

        return []


# ============================================================
# SAVE AUDIT LOG
# ============================================================

def save_audit_log(
    entries
):
    """
    Save the complete audit history.

    Returns:
        bool
    """

    _ensure_audit_directory()

    if not isinstance(
        entries,
        list
    ):
        return False

    temporary_file = (
        AUDIT_FILE + ".tmp"
    )

    try:

        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                entries,
                file,
                indent=2,
                ensure_ascii=False,
                default=str
            )

        os.replace(
            temporary_file,
            AUDIT_FILE
        )

        return True

    except OSError:

        try:

            if os.path.exists(
                temporary_file
            ):
                os.remove(
                    temporary_file
                )

        except OSError:
            pass

        return False


# ============================================================
# CREATE AUDIT ENTRY
# ============================================================

def create_audit_entry(
    event,
    action=None,
    parameters=None,
    status=None,
    result=None,
    error=None
):
    """
    Create a structured audit entry.

    Returns:
        dict
    """

    timestamp = (
        datetime.now().astimezone().isoformat()
    )

    entry = {
        "timestamp": timestamp,
        "event": event,
        "action": action,
        "parameters": (
            parameters
            if isinstance(parameters, dict)
            else {}
        ),
        "status": status,
        "result": result,
        "error": error
    }

    return entry


# ============================================================
# RECORD AUDIT EVENT
# ============================================================

def record_event(
    event,
    action=None,
    parameters=None,
    status=None,
    result=None,
    error=None
):
    """
    Record an event in the persistent audit log.

    Returns:
        dict
    """

    entry = create_audit_entry(
        event=event,
        action=action,
        parameters=parameters,
        status=status,
        result=result,
        error=error
    )

    entries = load_audit_log()

    entries.append(
        entry
    )

    saved = save_audit_log(
        entries
    )

    if not saved:

        entry["audit_saved"] = False

    else:

        entry["audit_saved"] = True

    return entry


# ============================================================
# RECORD ACTION ATTEMPT
# ============================================================

def record_action_attempt(
    action,
    parameters=None
):
    """
    Record that BENVIN attempted to process
    an action.
    """

    return record_event(
        event="action_attempt",
        action=action,
        parameters=parameters,
        status="attempted"
    )


# ============================================================
# RECORD VALIDATION
# ============================================================

def record_validation(
    action,
    parameters,
    validation
):
    """
    Record the result of action validation.
    """

    if not isinstance(
        validation,
        dict
    ):
        validation = {
            "valid": False,
            "error": "Invalid validation result."
        }

    valid = validation.get(
        "valid",
        False
    )

    status = (
        "validated"
        if valid
        else "validation_failed"
    )

    return record_event(
        event="validation",
        action=action,
        parameters=parameters,
        status=status,
        result=validation
    )


# ============================================================
# RECORD AUTHORIZATION
# ============================================================

def record_authorization(
    action,
    parameters,
    authorization
):
    """
    Record the permission decision.
    """

    if not isinstance(
        authorization,
        dict
    ):
        authorization = {
            "allowed": False,
            "reason": (
                "Invalid authorization result."
            )
        }

    allowed = authorization.get(
        "allowed",
        False
    )

    status = (
        "authorized"
        if allowed
        else authorization.get(
            "status",
            "denied"
        )
    )

    return record_event(
        event="authorization",
        action=action,
        parameters=parameters,
        status=status,
        result=authorization
    )


# ============================================================
# RECORD EXECUTION
# ============================================================

def record_execution(
    action,
    parameters,
    execution_result
):
    """
    Record the result of tool execution.
    """

    if not isinstance(
        execution_result,
        dict
    ):
        execution_result = {
            "success": False,
            "error": (
                "Invalid execution result."
            )
        }

    success = execution_result.get(
        "success",
        False
    )

    status = (
        "executed"
        if success
        else execution_result.get(
            "status",
            "execution_failed"
        )
    )

    return record_event(
        event="execution",
        action=action,
        parameters=parameters,
        status=status,
        result=execution_result,
        error=execution_result.get(
            "error"
        )
    )


# ============================================================
# GET RECENT EVENTS
# ============================================================

def get_recent_events(
    limit=20
):
    """
    Return the most recent audit events.

    Args:
        limit: Maximum number of events.

    Returns:
        list
    """

    if not isinstance(
        limit,
        int
    ):
        limit = 20

    if limit < 1:
        return []

    entries = load_audit_log()

    return entries[
        -limit:
    ]


# ============================================================
# GET ACTION HISTORY
# ============================================================

def get_action_history(
    action,
    limit=20
):
    """
    Return recent audit events for a specific action.
    """

    if not isinstance(
        action,
        str
    ):
        return []

    action = action.strip()

    if not action:
        return []

    entries = load_audit_log()

    matches = [
        entry
        for entry in entries
        if entry.get(
            "action"
        ) == action
    ]

    if not isinstance(
        limit,
        int
    ):
        limit = 20

    if limit < 1:
        return []

    return matches[
        -limit:
    ]


# ============================================================
# CLEAR AUDIT LOG
# ============================================================

def clear_audit_log():
    """
    Delete all audit history.

    Returns:
        bool
    """

    _ensure_audit_directory()

    try:

        if os.path.exists(
            AUDIT_FILE
        ):
            os.remove(
                AUDIT_FILE
            )

        return True

    except OSError:

        return False


# ============================================================
# AUDIT HEALTH CHECK
# ============================================================

def check_audit():
    """
    Check whether the audit system is operational.

    Returns:
        dict
    """

    _ensure_audit_directory()

    try:

        entries = load_audit_log()

        return {
            "success": True,
            "audit_file": AUDIT_FILE,
            "entries": len(entries)
        }

    except Exception as error:

        return {
            "success": False,
            "audit_file": AUDIT_FILE,
            "error": str(error)
        }