"""
BENVIN Confirmation System

Responsibilities:

    1. Determine whether an action needs confirmation.
    2. Present a clear confirmation request to the user.
    3. Accept explicit user approval or rejection.
    4. Never execute tools.
    5. Never override the permission engine.

IMPORTANT:

    The confirmation system is NOT the permission engine.

    permissions.py
        Determines whether policy requires confirmation.

    confirmation.py
        Handles the user's explicit approval.

    executor.py
        Executes the action only after authorization.

SECURITY PRINCIPLE:

    User confirmation can approve an action that the
    permission policy allows to be confirmed.

    User confirmation must NEVER bypass validation,
    tool existence checks, disabled tools, or other
    security controls.
"""

from tools.permissions import (
    requires_confirmation,
    get_action_risk
)


# ============================================================
# CONFIRMATION RESPONSES
# ============================================================

YES_RESPONSES = {
    "y",
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "approve",
    "approved",
}

NO_RESPONSES = {
    "n",
    "no",
    "nope",
    "cancel",
    "deny",
    "denied",
    "reject",
    "rejected",
    "stop",
}


# ============================================================
# NORMALIZE RESPONSE
# ============================================================

def normalize_confirmation_response(
    response
):
    """
    Normalize a user's confirmation response.

    Returns:

        "yes"
        "no"
        None

    Unknown responses are intentionally not interpreted
    as approval.
    """

    if not isinstance(
        response,
        str
    ):
        return None

    normalized = response.strip().lower()

    if normalized in YES_RESPONSES:
        return "yes"

    if normalized in NO_RESPONSES:
        return "no"

    return None


# ============================================================
# CHECK WHETHER CONFIRMATION IS REQUIRED
# ============================================================

def action_requires_confirmation(
    action
):
    """
    Determine whether an action requires explicit
    user confirmation.

    This delegates policy decisions to the permission
    engine rather than duplicating registry logic.
    """

    try:

        return requires_confirmation(
            action
        )

    except Exception:

        # Fail closed.

        return True


# ============================================================
# BUILD CONFIRMATION MESSAGE
# ============================================================

def build_confirmation_message(
    action,
    parameters=None
):
    """
    Build the message shown to the user when confirmation
    is required.

    This function does not execute anything.
    """

    if parameters is None:
        parameters = {}

    risk = get_action_risk(
        action
    )

    message = (
        "\n"
        "BENVIN requires your confirmation.\n"
        "\n"
        f"Action: {action}\n"
        f"Risk level: {risk}\n"
    )

    if parameters:

        message += (
            f"Parameters: {parameters}\n"
        )

    message += (
        "\n"
        "Do you want BENVIN to continue? "
        "[y/n]: "
    )

    return message


# ============================================================
# REQUEST USER CONFIRMATION
# ============================================================

def request_confirmation(
    action,
    parameters=None,
    input_function=input,
    output_function=print
):
    """
    Ask the user to explicitly approve or reject an action.

    Returns:

        {
            "confirmed": True,
            "action": action,
            "response": "yes"
        }

    OR:

        {
            "confirmed": False,
            "action": action,
            "response": "no"
        }

    OR:

        {
            "confirmed": False,
            "action": action,
            "response": None,
            "reason": "..."
        }

    Security behavior:

        Unknown responses are NOT treated as approval.

    The input_function and output_function arguments make
    this function easy to test without requiring real
    console input.
    """

    if parameters is None:
        parameters = {}

    # --------------------------------------------------------
    # Check whether confirmation is actually required
    # --------------------------------------------------------

    if not action_requires_confirmation(
        action
    ):

        return {
            "confirmed": True,
            "action": action,
            "response": "not_required"
        }

    # --------------------------------------------------------
    # Display confirmation request
    # --------------------------------------------------------

    message = build_confirmation_message(
        action,
        parameters
    )

    try:

        response = input_function(
            message
        )

    except (
        KeyboardInterrupt,
        EOFError
    ):

        return {
            "confirmed": False,
            "action": action,
            "response": None,
            "reason": (
                "Confirmation was cancelled."
            )
        }

    except Exception as error:

        return {
            "confirmed": False,
            "action": action,
            "response": None,
            "reason": (
                f"Could not obtain confirmation: "
                f"{error}"
            )
        }

    # --------------------------------------------------------
    # Normalize response
    # --------------------------------------------------------

    normalized = normalize_confirmation_response(
        response
    )

    # --------------------------------------------------------
    # Explicit approval
    # --------------------------------------------------------

    if normalized == "yes":

        try:

            output_function(
                "BENVIN: Confirmation received."
            )

        except Exception:
            pass

        return {
            "confirmed": True,
            "action": action,
            "response": "yes"
        }

    # --------------------------------------------------------
    # Explicit rejection
    # --------------------------------------------------------

    if normalized == "no":

        try:

            output_function(
                "BENVIN: Action cancelled."
            )

        except Exception:
            pass

        return {
            "confirmed": False,
            "action": action,
            "response": "no",
            "reason": (
                "The user declined the action."
            )
        }

    # --------------------------------------------------------
    # Unknown response
    # --------------------------------------------------------

    try:

        output_function(
            (
                "BENVIN: I did not recognize "
                "that confirmation."
            )
        )

    except Exception:
        pass

    return {
        "confirmed": False,
        "action": action,
        "response": None,
        "reason": (
            "Confirmation response was not "
            "recognized. Action was not executed."
        )
    }


# ============================================================
# CONFIRM ACTION
# ============================================================

def confirm_action(
    action,
    parameters=None,
    input_function=input,
    output_function=print
):
    """
    Public confirmation API.

    This is the preferred function for the rest of BENVIN.

    It returns a structured result and never executes
    the requested action.
    """

    if parameters is None:
        parameters = {}

    return request_confirmation(
        action,
        parameters,
        input_function=input_function,
        output_function=output_function
    )


# ============================================================
# CONFIRMATION SUMMARY
# ============================================================

def get_confirmation_summary(
    action
):
    """
    Return information about the confirmation policy
    for an action.

    Returns:

        {
            "action": "...",
            "requires_confirmation": True/False,
            "risk": "LOW/MEDIUM/HIGH"
        }
    """

    return {
        "action": action,
        "requires_confirmation": (
            action_requires_confirmation(
                action
            )
        ),
        "risk": get_action_risk(
            action
        )
    }