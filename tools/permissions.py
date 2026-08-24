"""
BENVIN Permission Engine

Central authorization layer.

The LLM never decides whether an action is allowed.
The permission engine enforces the registered policy.
"""

from tools.registry import (
    get_tool,
    tool_exists,
    get_tool_risk,
    tool_requires_confirmation
)


# ============================================================
# RISK LEVELS
# ============================================================

RISK_LEVELS = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3
}


# ============================================================
# AUTHORIZE ACTION
# ============================================================

def authorize_action(
    action,
    user_confirmed=False
):
    """
    Determine whether an action may execute.
    """

    # --------------------------------------------------------
    # 1. Tool must exist and be enabled
    # --------------------------------------------------------

    if not tool_exists(action):

        return {
            "allowed": False,
            "status": "denied",
            "action": action,
            "reason": (
                f"Tool '{action}' is not registered "
                "or is disabled."
            )
        }

    # --------------------------------------------------------
    # 2. Get registered definition
    # --------------------------------------------------------

    tool = get_tool(action)

    if tool is None:

        return {
            "allowed": False,
            "status": "denied",
            "action": action,
            "reason": (
                f"Tool '{action}' does not exist."
            )
        }

    # --------------------------------------------------------
    # 3. Get risk
    # --------------------------------------------------------

    risk = get_tool_risk(action)

    if risk not in RISK_LEVELS:

        return {
            "allowed": False,
            "status": "denied",
            "action": action,
            "reason": (
                f"Invalid risk level '{risk}' "
                f"configured for '{action}'."
            )
        }

    # --------------------------------------------------------
    # 4. Check confirmation requirement
    # --------------------------------------------------------

    confirmation_required = (
        tool_requires_confirmation(action)
    )

    if confirmation_required:

        if not user_confirmed:

            return {
                "allowed": False,
                "status": "confirmation_required",
                "action": action,
                "risk": risk,
                "reason": (
                    f"Action '{action}' requires "
                    "explicit user confirmation."
                )
            }

    # --------------------------------------------------------
    # 5. Authorized
    # --------------------------------------------------------

    return {
        "allowed": True,
        "status": "authorized",
        "action": action,
        "risk": risk,
        "confirmation_required": (
            confirmation_required
        )
    }


# ============================================================
# REQUIRE CONFIRMATION
# ============================================================

def requires_confirmation(action):
    """
    Return whether an action requires confirmation.
    """

    return tool_requires_confirmation(
        action
    )


# ============================================================
# GET ACTION RISK
# ============================================================

def get_action_risk(action):
    """
    Return the risk level for an action.
    """

    risk = get_tool_risk(action)

    if risk is None:
        return "HIGH"

    return risk


# ============================================================
# PERMISSION SUMMARY
# ============================================================

def get_permission_summary():
    """
    Return permission information for all registered tools.
    """

    from tools.registry import list_tools

    summary = []

    for action in list_tools():

        summary.append({
            "action": action,
            "risk": get_tool_risk(action),
            "requires_confirmation": (
                tool_requires_confirmation(action)
            )
        })

    return summary