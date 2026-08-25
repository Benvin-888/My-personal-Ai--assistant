"""
BENVIN Action Executor

Execution pipeline:

    Action
       ↓
    Validator
       ↓
    Permission Engine
       ↓
    Executor
       ↓
    Tool

The LLM never directly executes Python functions.

The executor is the controlled bridge between
BENVIN's approved structured actions and the actual
Python tool implementations.

IMPORTANT:

    The executor does NOT decide what the AI should do.

    It only executes an action after:

        1. Validation
        2. Executor availability check
        3. Permission authorization
"""


from tools.validator import (
    validate_action
)

from tools.permissions import (
    authorize_action
)

from tools.system import (
    get_system_info
)

from tools.files import (
    list_directory,
    find_file,
    path_exists,
    get_file_info
)

from tools.applications import (
    open_application,
    list_applications
)


# ============================================================
# EXECUTION MAP
# ============================================================

TOOL_FUNCTIONS = {

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    "system_info": get_system_info,

    # --------------------------------------------------------
    # FILESYSTEM
    # --------------------------------------------------------

    "list_directory": list_directory,

    "find_file": find_file,

    "path_exists": path_exists,

    "get_file_info": get_file_info,

    # --------------------------------------------------------
    # APPLICATIONS
    # --------------------------------------------------------

    "open_application": open_application,

    "list_applications": list_applications
}


# ============================================================
# EXECUTOR CHECK
# ============================================================

def executor_exists(action):
    """
    Check whether an action has a corresponding
    Python executor function.

    Returns:
        bool
    """

    return action in TOOL_FUNCTIONS


# ============================================================
# GET EXECUTOR
# ============================================================

def get_executor(action):
    """
    Return the Python function associated with
    a registered action.

    Returns:
        callable | None
    """

    return TOOL_FUNCTIONS.get(
        action
    )


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

        1. Validate action
        2. Validate parameters
        3. Check executor
        4. Check permission
        5. Execute tool
        6. Return structured result

    The returned structure is intentionally consistent
    so main.py, context.py, audit logging, and brain.py
    can safely consume it.
    """

    # ========================================================
    # NORMALIZE PARAMETERS
    # ========================================================

    if parameters is None:

        parameters = {}

    # ========================================================
    # STEP 1 — VALIDATION
    # ========================================================

    validation = validate_action(
        action,
        parameters
    )

    if not validation.get(
        "valid",
        False
    ):

        return {
            "success": False,
            "action": action,
            "status": "validation_failed",
            "error": validation.get(
                "error",
                "Action validation failed."
            )
        }

    # ========================================================
    # STEP 2 — EXECUTOR CHECK
    # ========================================================

    if not executor_exists(
        action
    ):

        return {
            "success": False,
            "action": action,
            "status": "no_executor",
            "error": (
                f"No executor exists for "
                f"'{action}'."
            )
        }

    # ========================================================
    # STEP 3 — PERMISSION
    # ========================================================

    authorization = authorize_action(
        action,
        user_confirmed=user_confirmed
    )

    if not authorization.get(
        "allowed",
        False
    ):

        return {
            "success": False,
            "action": action,
            "status": authorization.get(
                "status",
                "denied"
            ),
            "error": authorization.get(
                "reason",
                "Action was not authorized."
            )
        }

    # ========================================================
    # STEP 4 — GET TOOL FUNCTION
    # ========================================================

    tool_function = get_executor(
        action
    )

    if tool_function is None:

        return {
            "success": False,
            "action": action,
            "status": "no_executor",
            "error": (
                f"No executable function exists "
                f"for '{action}'."
            )
        }

    # ========================================================
    # STEP 5 — EXECUTE TOOL
    # ========================================================

    try:

        result = tool_function(
            **parameters
        )

    except TypeError as error:

        return {
            "success": False,
            "action": action,
            "status": (
                "execution_parameter_error"
            ),
            "error": str(error)
        }

    except Exception as error:

        return {
            "success": False,
            "action": action,
            "status": "execution_error",
            "error": str(error)
        }

    # ========================================================
    # STEP 6 — HANDLE TOOL RESULT
    # ========================================================

    # BENVIN tools normally return dictionaries.
    #
    # We deliberately handle unexpected return types so
    # the executor itself never crashes because a future
    # tool returned something unusual.

    if isinstance(
        result,
        dict
    ):

        # ----------------------------------------------------
        # If the tool explicitly reports success=False,
        # preserve that failure instead of claiming execution
        # succeeded.
        # ----------------------------------------------------

        if result.get(
            "success"
        ) is False:

            return {
                "success": False,
                "action": action,
                "status": (
                    "tool_execution_failed"
                ),
                "error": result.get(
                    "error",
                    "The tool reported an execution failure."
                ),
                "result": result
            }

    # ========================================================
    # SUCCESS
    # ========================================================

    return {
        "success": True,
        "action": action,
        "status": "executed",
        "result": result
    }


# ============================================================
# LIST EXECUTABLE ACTIONS
# ============================================================

def list_executable_actions():
    """
    Return the actions that currently have Python
    executor functions.

    This is useful for diagnostics and testing.
    """

    return list(
        TOOL_FUNCTIONS.keys()
    )


# ============================================================
# EXECUTOR STATUS
# ============================================================

def get_executor_status():
    """
    Return a structured diagnostic report showing
    which actions have executor functions.

    This does not execute anything.
    """

    status = []

    for action, function in TOOL_FUNCTIONS.items():

        status.append({
            "action": action,
            "executor": function.__name__,
            "available": callable(
                function
            )
        })

    return {
        "success": True,
        "count": len(status),
        "executors": status
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("BENVIN EXECUTOR TEST")
    print("=" * 60)

    print()
    print("Executable actions:")

    for action in list_executable_actions():

        print(
            f"  - {action}"
        )

    print()
    print("Executor status:")

    print(
        get_executor_status()
    )

    print()
    print("Executor test complete.")