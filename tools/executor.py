"""
BENVIN Action Executor

Execution pipeline:

    Action
       ↓
    Validator
       ↓
    Audit
       ↓
    Permission Engine
       ↓
    Audit
       ↓
    Executor
       ↓
    Tool
       ↓
    Audit
       ↓
    Result

The LLM never directly executes Python functions.

The executor is responsible for connecting:

    validator
        +
    permission engine
        +
    registered tool functions
        +
    audit system
"""

from tools.validator import (
    validate_action
)

from tools.permissions import (
    authorize_action
)

from tools.audit import (
    record_action_attempt,
    record_validation,
    record_authorization,
    record_execution
)

from tools.system import (
    get_system_info
)

from tools.files import (
    list_directory,
    find_file,
    path_exists
)

from tools.applications import (
    open_application,
    list_applications
)


# ============================================================
# EXECUTION MAP
# ============================================================

TOOL_FUNCTIONS = {

    "system_info": get_system_info,

    "list_directory": list_directory,

    "find_file": find_file,

    "path_exists": path_exists,

    "open_application": open_application,

    "list_applications": list_applications

}


# ============================================================
# EXECUTOR CHECK
# ============================================================

def executor_exists(action):
    """
    Check whether an action has an executor.

    Returns:
        bool
    """

    return action in TOOL_FUNCTIONS


# ============================================================
# SAFE AUDIT HELPERS
# ============================================================

def _audit_action_attempt(
    action,
    parameters
):
    """
    Record an action attempt.

    Audit errors must never interrupt the execution
    pipeline.
    """

    try:

        return record_action_attempt(
            action,
            parameters
        )

    except Exception:

        return None


def _audit_validation(
    action,
    parameters,
    validation
):
    """
    Record a validation result.

    Audit errors are intentionally ignored.
    """

    try:

        return record_validation(
            action,
            parameters,
            validation
        )

    except Exception:

        return None


def _audit_authorization(
    action,
    parameters,
    authorization
):
    """
    Record an authorization decision.

    Audit errors are intentionally ignored.
    """

    try:

        return record_authorization(
            action,
            parameters,
            authorization
        )

    except Exception:

        return None


def _audit_execution(
    action,
    parameters,
    result
):
    """
    Record an execution result.

    Audit errors are intentionally ignored.
    """

    try:

        return record_execution(
            action,
            parameters,
            result
        )

    except Exception:

        return None


# ============================================================
# EXECUTE ACTION
# ============================================================

def execute_action(
    action,
    parameters=None,
    user_confirmed=False
):
    """
    Execute a structured BENVIN action.

    Pipeline:

        1. Record action attempt
        2. Validate action
        3. Record validation
        4. Check executor
        5. Check permission
        6. Record authorization
        7. Execute tool
        8. Record execution
        9. Return structured result

    IMPORTANT:

        This function does NOT trust the LLM.

        Every action passes through validation
        and authorization before execution.
    """

    if parameters is None:

        parameters = {}

    # ========================================================
    # STEP 0 — AUDIT ACTION ATTEMPT
    # ========================================================

    _audit_action_attempt(
        action,
        parameters
    )

    # ========================================================
    # STEP 1 — VALIDATION
    # ========================================================

    validation = validate_action(
        action,
        parameters
    )

    # --------------------------------------------------------
    # Record validation result
    # --------------------------------------------------------

    _audit_validation(
        action,
        parameters,
        validation
    )

    # --------------------------------------------------------
    # Validation failure
    # --------------------------------------------------------

    if not validation["valid"]:

        result = {
            "success": False,
            "action": action,
            "status": "validation_failed",
            "error": validation["error"]
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # STEP 2 — EXECUTOR CHECK
    # ========================================================

    if not executor_exists(
        action
    ):

        result = {
            "success": False,
            "action": action,
            "status": "no_executor",
            "error": (
                f"No executor exists for "
                f"'{action}'."
            )
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # STEP 3 — PERMISSION
    # ========================================================

    authorization = authorize_action(
        action,
        user_confirmed=user_confirmed
    )

    # --------------------------------------------------------
    # Record authorization decision
    # --------------------------------------------------------

    _audit_authorization(
        action,
        parameters,
        authorization
    )

    # --------------------------------------------------------
    # Authorization failure
    # --------------------------------------------------------

    if not authorization["allowed"]:

        result = {
            "success": False,
            "action": action,
            "status": authorization["status"],
            "error": authorization["reason"]
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # STEP 4 — GET TOOL FUNCTION
    # ========================================================

    tool_function = TOOL_FUNCTIONS.get(
        action
    )

    if tool_function is None:

        result = {
            "success": False,
            "action": action,
            "status": "no_executor",
            "error": (
                f"No executor exists for "
                f"'{action}'."
            )
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # STEP 5 — EXECUTE TOOL
    # ========================================================

    try:

        tool_result = tool_function(
            **parameters
        )

        result = {
            "success": True,
            "action": action,
            "status": "executed",
            "result": tool_result
        }

        # ----------------------------------------------------
        # Record successful execution
        # ----------------------------------------------------

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # PARAMETER ERROR
    # ========================================================

    except TypeError as error:

        result = {
            "success": False,
            "action": action,
            "status": (
                "execution_parameter_error"
            ),
            "error": str(error)
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result

    # ========================================================
    # GENERAL EXECUTION ERROR
    # ========================================================

    except Exception as error:

        result = {
            "success": False,
            "action": action,
            "status": "execution_error",
            "error": str(error)
        }

        _audit_execution(
            action,
            parameters,
            result
        )

        return result