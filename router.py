"""
BENVIN Action Router

Phase 1 controlled action routing layer.

Architecture:

    User Request
         ↓
      brain.py
         ↓
    Structured Intent
         ↓
      router.py
         ↓
    executor.py
         ↓
    validator.py
         ↓
    permissions.py
         ↓
      Tool
         ↓
      Result


IMPORTANT:

The router does NOT directly execute filesystem,
application, or system tools.

The router's responsibilities are:

    1. Receive a structured intent.
    2. Determine whether it is a conversation or action.
    3. Validate the basic intent structure.
    4. Pass approved action information to the executor.
    5. Return the executor result.

The LLM never directly executes tools.

The router never bypasses the executor.
"""


from tools.executor import (
    execute_action,
    executor_exists
)

from tools.registry import (
    tool_exists
)


# ============================================================
# ROUTER RESULT HELPERS
# ============================================================

def router_error(
    message,
    action=None
):
    """
    Create a consistent router error.
    """

    result = {
        "success": False,
        "status": "routing_failed",
        "error": message
    }

    if action is not None:

        result["action"] = action

    return result


# ============================================================
# VALIDATE INTENT STRUCTURE
# ============================================================

def validate_intent_structure(
    intent
):
    """
    Validate the basic structure of an intent.

    This is intentionally lightweight.

    Detailed parameter validation belongs to:

        tools/validator.py
    """

    if not isinstance(
        intent,
        dict
    ):

        return {
            "valid": False,
            "error": (
                "Intent must be a dictionary."
            )
        }

    intent_type = intent.get(
        "type"
    )

    if intent_type not in {
        "conversation",
        "action"
    }:

        return {
            "valid": False,
            "error": (
                "Intent type must be "
                "'conversation' or 'action'."
            )
        }

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    if intent_type == "conversation":

        response = intent.get(
            "response"
        )

        if not isinstance(
            response,
            str
        ):

            return {
                "valid": False,
                "error": (
                    "Conversation intent requires "
                    "a string 'response'."
                )
            }

        return {
            "valid": True,
            "type": "conversation"
        }

    # --------------------------------------------------------
    # Action
    # --------------------------------------------------------

    action = intent.get(
        "action"
    )

    if not isinstance(
        action,
        str
    ):

        return {
            "valid": False,
            "error": (
                "Action intent requires a "
                "string 'action'."
            )
        }

    action = action.strip()

    if not action:

        return {
            "valid": False,
            "error": (
                "Action name cannot be empty."
            )
        }

    parameters = intent.get(
        "parameters",
        {}
    )

    if parameters is None:

        parameters = {}

    if not isinstance(
        parameters,
        dict
    ):

        return {
            "valid": False,
            "error": (
                "Action parameters must be "
                "a dictionary."
            )
        }

    return {
        "valid": True,
        "type": "action",
        "action": action,
        "parameters": parameters
    }


# ============================================================
# ROUTE INTENT
# ============================================================

def route_intent(
    intent,
    user_confirmed=False
):
    """
    Route a structured BENVIN intent.

    Conversation intents are returned without
    execution.

    Action intents are passed to executor.py.

    The router never directly calls a tool.
    """

    # ========================================================
    # STRUCTURE VALIDATION
    # ========================================================

    structure = validate_intent_structure(
        intent
    )

    if not structure.get(
        "valid",
        False
    ):

        return router_error(
            structure.get(
                "error",
                "Invalid intent."
            )
        )

    # ========================================================
    # CONVERSATION
    # ========================================================

    if structure["type"] == "conversation":

        return {
            "success": True,
            "type": "conversation",
            "status": "conversation",
            "response": intent.get(
                "response",
                ""
            )
        }

    # ========================================================
    # ACTION
    # ========================================================

    action = structure["action"]

    parameters = structure[
        "parameters"
    ]

    # --------------------------------------------------------
    # Registry check
    # --------------------------------------------------------

    if not tool_exists(
        action
    ):

        return router_error(
            (
                f"Action '{action}' is not "
                "registered or enabled."
            ),
            action
        )

    # --------------------------------------------------------
    # Executor check
    # --------------------------------------------------------

    if not executor_exists(
        action
    ):

        return router_error(
            (
                f"Action '{action}' has no "
                "registered executor."
            ),
            action
        )

    # ========================================================
    # EXECUTOR
    # ========================================================

    result = execute_action(
        action=action,
        parameters=parameters,
        user_confirmed=user_confirmed
    )

    # ========================================================
    # NORMALIZE RESULT
    # ========================================================

    if not isinstance(
        result,
        dict
    ):

        return {
            "success": False,
            "type": "action",
            "action": action,
            "status": "invalid_executor_result",
            "error": (
                "Executor returned an invalid result."
            )
        }

    # --------------------------------------------------------
    # Add intent metadata
    # --------------------------------------------------------

    result.setdefault(
        "type",
        "action"
    )

    return result


# ============================================================
# ROUTE ACTION
# ============================================================

def route_action(
    action,
    parameters=None,
    user_confirmed=False
):
    """
    Convenience function for routing an already
    structured action.

    Example:

        route_action(
            "list_directory",
            {
                "path": "Desktop"
            }
        )
    """

    if parameters is None:

        parameters = {}

    intent = {
        "type": "action",
        "action": action,
        "parameters": parameters
    }

    return route_intent(
        intent,
        user_confirmed=user_confirmed
    )


# ============================================================
# ROUTE CONVERSATION
# ============================================================

def route_conversation(
    response
):
    """
    Create a conversation result.

    This does not execute anything.
    """

    return route_intent(
        {
            "type": "conversation",
            "response": response
        }
    )


# ============================================================
# CHECK ROUTER ACTION
# ============================================================

def can_route_action(
    action
):
    """
    Check whether an action can reach an executor.

    This does NOT execute the action.
    """

    if not isinstance(
        action,
        str
    ):

        return False

    action = action.strip()

    if not action:

        return False

    if not tool_exists(
        action
    ):

        return False

    if not executor_exists(
        action
    ):

        return False

    return True


# ============================================================
# ROUTER STATUS
# ============================================================

def get_router_status():
    """
    Return diagnostic information about
    registered actions and their executors.

    This does not execute tools.
    """

    from tools.registry import (
        list_tools
    )

    registered_actions = list_tools()

    routable = []
    missing_executors = []

    for action in registered_actions:

        if executor_exists(
            action
        ):

            routable.append(
                action
            )

        else:

            missing_executors.append(
                action
            )

    return {
        "success": True,
        "registered_tools": len(
            registered_actions
        ),
        "routable_tools": len(
            routable
        ),
        "registered_actions": (
            registered_actions
        ),
        "routable_actions": routable,
        "missing_executors": (
            missing_executors
        )
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("BENVIN ROUTER TEST")
    print("=" * 60)

    # ========================================================
    # ROUTER STATUS
    # ========================================================

    print()
    print("Router status:")

    print(
        get_router_status()
    )

    # ========================================================
    # CONVERSATION TEST
    # ========================================================

    print()
    print("Testing conversation:")

    conversation = route_intent(
        {
            "type": "conversation",
            "response": (
                "BENVIN is ready."
            )
        }
    )

    print(
        conversation
    )

    # ========================================================
    # SYSTEM INFO TEST
    # ========================================================

    print()
    print("Testing system_info:")

    system_result = route_intent(
        {
            "type": "action",
            "action": "system_info",
            "parameters": {}
        }
    )

    print(
        system_result
    )

    # ========================================================
    # DIRECTORY TEST
    # ========================================================

    print()
    print("Testing BENVIN directory:")

    directory_result = route_intent(
        {
            "type": "action",
            "action": "list_directory",
            "parameters": {
                "path": "Benvin"
            }
        }
    )

    print(
        directory_result
    )

    # ========================================================
    # FILE SEARCH TEST
    # ========================================================

    print()
    print("Testing main.py search:")

    file_result = route_intent(
        {
            "type": "action",
            "action": "find_file",
            "parameters": {
                "filename": "main.py",
                "search_root": "Benvin"
            }
        }
    )

    print(
        file_result
    )

    # ========================================================
    # SECURITY TEST
    # ========================================================

    print()
    print("Testing filesystem security:")

    security_result = route_intent(
        {
            "type": "action",
            "action": "list_directory",
            "parameters": {
                "path": r"C:\Windows"
            }
        }
    )

    print(
        security_result
    )

    # ========================================================
    # INVALID ACTION TEST
    # ========================================================

    print()
    print("Testing invalid action:")

    invalid_result = route_intent(
        {
            "type": "action",
            "action": "delete_everything",
            "parameters": {}
        }
    )

    print(
        invalid_result
    )

    # ========================================================
    # UNKNOWN PARAMETER TEST
    # ========================================================

    print()
    print("Testing invalid parameters:")

    parameter_result = route_intent(
        {
            "type": "action",
            "action": "list_directory",
            "parameters": {
                "path": "Desktop",
                "dangerous_parameter": True
            }
        }
    )

    print(
        parameter_result
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print()
    print("=" * 60)
    print("ROUTER TEST COMPLETE")
    print("=" * 60)