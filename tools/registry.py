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

IMPORTANT:

Other BENVIN layers should NOT independently decide which
tools exist.

They should use this registry.

Architecture:

    registry.py
         ↓
    ┌────┼───────────────┐
    ↓    ↓               ↓
validator permissions   brain
    ↓                    ↓
 executor            tool context
    ↓
 actual tools
"""


# ============================================================
# TOOL REGISTRY
# ============================================================

TOOL_REGISTRY = {

    # ========================================================
    # SYSTEM
    # ========================================================

    "system_info": {
        "description": (
            "Get information about the computer, "
            "operating system, hardware, Python version, "
            "computer name, and current user."
        ),

        "risk": "LOW",

        "requires_confirmation": False,

        "enabled": True,

        "parameters": {}
    },


    # ========================================================
    # FILESYSTEM
    # ========================================================

    "list_directory": {
        "description": (
            "List files and folders inside an allowed "
            "BENVIN filesystem directory."
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
            "Search for a file by name inside an allowed "
            "BENVIN filesystem directory."
        ),

        "risk": "LOW",

        "requires_confirmation": False,

        "enabled": True,

        "parameters": {

            "filename": {
                "type": "string",
                "required": True,
                "description": (
                    "File name to search for."
                )
            },

            "search_root": {
                "type": "string",
                "required": False,
                "description": (
                    "Directory where the search should begin."
                )
            }
        }
    },


    "path_exists": {
        "description": (
            "Check whether an allowed file or directory "
            "exists."
        ),

        "risk": "LOW",

        "requires_confirmation": False,

        "enabled": True,

        "parameters": {

            "path": {
                "type": "string",
                "required": True,
                "description": (
                    "File or directory path to check."
                )
            }
        }
    },


    "get_file_info": {
        "description": (
            "Get basic information about an allowed file "
            "or directory, including its name, type, path, "
            "and file size."
        ),

        "risk": "LOW",

        "requires_confirmation": False,

        "enabled": True,

        "parameters": {

            "path": {
                "type": "string",
                "required": True,
                "description": (
                    "File or directory path to inspect."
                )
            }
        }
    },


    # ========================================================
    # APPLICATIONS
    # ========================================================

    "open_application": {
        "description": (
            "Open an approved application on the "
            "Windows computer."
        ),

        "risk": "LOW",

        "requires_confirmation": False,

        "enabled": True,

        "parameters": {

            "application": {
                "type": "string",
                "required": True,
                "description": (
                    "Name or approved alias of the "
                    "application to open."
                )
            }
        }
    },


    "list_applications": {
        "description": (
            "List applications BENVIN is currently "
            "allowed to launch."
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

    if not isinstance(action, str):
        return None

    return TOOL_REGISTRY.get(
        action.strip()
    )


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

    return tool.get(
        "enabled",
        False
    )


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
    Return the description of a registered tool.
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
    Return the configured risk level of a tool.
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
# GET TOOL PARAMETERS
# ============================================================

def get_tool_parameters(action):
    """
    Return the parameter schema for the registered tool.
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
# LIST ALL TOOLS
# ============================================================

def list_all_tools():
    """
    Return the names of all registered tools,
    including disabled tools.
    """

    return list(
        TOOL_REGISTRY.keys()
    )


# ============================================================
# GET ENABLED TOOL COUNT
# ============================================================

def get_tool_count():
    """
    Return the number of enabled tools.
    """

    return len(
        list_tools()
    )


# ============================================================
# GET REGISTRY
# ============================================================

def get_registry():
    """
    Return a shallow copy of the complete tool registry.
    """

    return TOOL_REGISTRY.copy()