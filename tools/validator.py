"""
BENVIN Action Validator

Validates structured actions before they reach
the permission and execution layers.

The validator does NOT execute tools.
"""

from tools.registry import (
    get_tool,
    tool_exists,
    get_tool_parameters
)


# ============================================================
# VALIDATION RESULT
# ============================================================

def validation_error(
    action,
    message
):
    return {
        "valid": False,
        "action": action,
        "error": message
    }


# ============================================================
# VALIDATE PARAMETERS
# ============================================================

def validate_parameters(
    action,
    parameters
):
    """
    Validate parameters against the registered
    tool parameter schema.
    """

    if parameters is None:
        parameters = {}

    if not isinstance(parameters, dict):

        return validation_error(
            action,
            "Parameters must be an object/dictionary."
        )

    schema = get_tool_parameters(
        action
    )

    if schema is None:

        return validation_error(
            action,
            f"No parameter schema exists for '{action}'."
        )

    # --------------------------------------------------------
    # Check required parameters
    # --------------------------------------------------------

    for name, definition in schema.items():

        required = definition.get(
            "required",
            False
        )

        if required and name not in parameters:

            return validation_error(
                action,
                f"Missing required parameter: '{name}'."
            )

    # --------------------------------------------------------
    # Check unknown parameters
    # --------------------------------------------------------

    allowed_parameters = set(
        schema.keys()
    )

    supplied_parameters = set(
        parameters.keys()
    )

    unknown_parameters = (
        supplied_parameters
        - allowed_parameters
    )

    if unknown_parameters:

        unknown = ", ".join(
            sorted(unknown_parameters)
        )

        return validation_error(
            action,
            f"Unknown parameter(s): {unknown}"
        )

    # --------------------------------------------------------
    # Check basic types
    # --------------------------------------------------------

    for name, value in parameters.items():

        definition = schema.get(
            name
        )

        if definition is None:
            continue

        expected_type = definition.get(
            "type"
        )

        if expected_type == "string":

            if not isinstance(value, str):

                return validation_error(
                    action,
                    (
                        f"Parameter '{name}' "
                        "must be a string."
                    )
                )

        elif expected_type == "boolean":

            if not isinstance(value, bool):

                return validation_error(
                    action,
                    (
                        f"Parameter '{name}' "
                        "must be a boolean."
                    )
                )

        elif expected_type == "integer":

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):

                return validation_error(
                    action,
                    (
                        f"Parameter '{name}' "
                        "must be an integer."
                    )
                )

        elif expected_type == "number":

            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
            ):

                return validation_error(
                    action,
                    (
                        f"Parameter '{name}' "
                        "must be a number."
                    )
                )

    # --------------------------------------------------------
    # Valid
    # --------------------------------------------------------

    return {
        "valid": True,
        "action": action,
        "parameters": parameters
    }


# ============================================================
# VALIDATE ACTION
# ============================================================

def validate_action(
    action,
    parameters=None
):
    """
    Validate a complete structured action.
    """

    # --------------------------------------------------------
    # Action name
    # --------------------------------------------------------

    if not isinstance(action, str):

        return validation_error(
            action,
            "Action must be a string."
        )

    action = action.strip()

    if not action:

        return validation_error(
            action,
            "Action cannot be empty."
        )

    # --------------------------------------------------------
    # Tool existence
    # --------------------------------------------------------

    if not tool_exists(action):

        return validation_error(
            action,
            (
                f"Action '{action}' is not "
                "registered or enabled."
            )
        )

    # --------------------------------------------------------
    # Tool definition
    # --------------------------------------------------------

    tool = get_tool(
        action
    )

    if tool is None:

        return validation_error(
            action,
            (
                f"No registry definition "
                f"exists for '{action}'."
            )
        )

    # --------------------------------------------------------
    # Parameters
    # --------------------------------------------------------

    return validate_parameters(
        action,
        parameters
    )