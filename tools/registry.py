"""
BENVIN Tool Registry

The registry is the single source of truth for BENVIN's tools.

Every tool registered here contains:
    - action name
    - description
    - risk level
    - confirmation requirement
    - parameter definitions
    - enabled state

Other BENVIN layers should use this registry rather than
maintaining separate tool definitions.
"""


# ============================================================
# TOOL REGISTRY
# ============================================================

TOOL_REGISTRY = {

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    "system_info": {
        "description": (
            "Get information about the computer, "
            "operating system, hardware, Python version, "
            "and current user."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {}
    },

    # --------------------------------------------------------
    # FILESYSTEM
    # --------------------------------------------------------

    "list_directory": {
        "description": (
            "List files and folders inside a directory."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {
            "path": {
                "type": "string",
                "required": True,
                "description": (
                    "Directory path to inspect."
                )
            }
        }
    },

    "find_file": {
        "description": (
            "Search for files and folders."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {
            "name": {
                "type": "string",
                "required": True,
                "description": (
                    "File or folder name to search for."
                )
            }
        }
    },

    "path_exists": {
        "description": (
            "Check whether a file or folder exists."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {
            "path": {
                "type": "string",
                "required": True,
                "description": (
                    "Path to check."
                )
            }
        }
    },

    # --------------------------------------------------------
    # APPLICATIONS
    # --------------------------------------------------------

    "open_application": {
        "description": (
            "Open an approved application on the computer."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {
            "application": {
                "type": "string",
                "required": True,
                "description": (
                    "Name or alias of the application "
                    "to open."
                )
            }
        }
    },

    "list_applications": {
        "description": (
            "List applications BENVIN is allowed "
            "to launch."
        ),
        "risk": "LOW",
        "requires_confirmation": False,
        "enabled": True,

        "parameters": {}
    }
}


# ============================================================
# GET TOOL
# ============================================================

def get_tool(action):
    """
    Return the complete definition of a registered tool.

    Returns:
        dict | None
    """

    return TOOL_REGISTRY.get(action)


# ============================================================
# CHECK TOOL EXISTENCE
# ============================================================

def tool_exists(action):
    """
    Return True if a tool exists and is enabled.
    """

    tool = get_tool(action)

    if tool is None:
        return False

    return tool.get("enabled", False)


# ============================================================
# CHECK TOOL ENABLED
# ============================================================

def is_tool_enabled(action):
    """
    Check whether a registered tool is enabled.
    """

    tool = get_tool(action)

    if tool is None:
        return False

    return tool.get(
        "enabled",
        False
    )


# ============================================================
# GET TOOL DESCRIPTION
# ============================================================

def get_tool_description(action):
    """
    Return the description of a tool.
    """

    tool = get_tool(action)

    if tool is None:
        return None

    return tool.get(
        "description"
    )


# ============================================================
# GET TOOL RISK
# ============================================================

def get_tool_risk(action):
    """
    Return the configured risk level.
    """

    tool = get_tool(action)

    if tool is None:
        return None

    return tool.get(
        "risk",
        "HIGH"
    )


# ============================================================
# CHECK CONFIRMATION
# ============================================================

def tool_requires_confirmation(action):
    """
    Determine whether a tool requires explicit
    user confirmation.
    """

    tool = get_tool(action)

    if tool is None:
        return True

    return tool.get(
        "requires_confirmation",
        True
    )


# ============================================================
# GET PARAMETERS
# ============================================================

def get_tool_parameters(action):
    """
    Return the parameter schema for a tool.
    """

    tool = get_tool(action)

    if tool is None:
        return None

    return tool.get(
        "parameters",
        {}
    )


# ============================================================
# LIST TOOLS
# ============================================================

def list_tools():
    """
    Return the names of all enabled tools.
    """

    return [
        action
        for action, definition
        in TOOL_REGISTRY.items()
        if definition.get(
            "enabled",
            False
        )
    ]


# ============================================================
# GET REGISTRY
# ============================================================

def get_registry():
    """
    Return the complete tool registry.
    """

    return TOOL_REGISTRY.copy()