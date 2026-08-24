from tools.system import get_system_info

from tools.files import (
    list_directory,
    path_exists,
    find_file,
    get_file_info
)

from tools.applications import (
    open_application,
    list_applications
)

from tools.registry import tool_exists


# ============================================================
# ROUTER
# ============================================================

def route_command(user_input):
    """
    Route user requests to controlled BENVIN tools.

    The router never executes arbitrary shell commands.
    """

    command = user_input.lower().strip()

    # ========================================================
    # SYSTEM INFORMATION
    # ========================================================

    system_keywords = [
        "system info",
        "system information",
        "computer info",
        "computer information",
        "computer specifications",
        "computer specs",
        "laptop specifications",
        "laptop specs",
        "pc specifications",
        "pc specs",
        "my computer",
        "my laptop"
    ]

    if any(
        keyword in command
        for keyword in system_keywords
    ):

        if not tool_exists(
            "system_info"
        ):
            return None

        return {
            "tool": "system_info",
            "success": True,
            "data": get_system_info()
        }

    # ========================================================
    # DESKTOP
    # ========================================================

    desktop_keywords = [
        "list files on my desktop",
        "list my desktop",
        "show my desktop files",
        "what is on my desktop",
        "what's on my desktop",
        "show desktop files"
    ]

    if any(
        keyword in command
        for keyword in desktop_keywords
    ):

        if not tool_exists(
            "list_directory"
        ):
            return None

        result = list_directory()

        return {
            "tool": "list_directory",
            "success": result.get(
                "success",
                False
            ),
            "data": result
        }

    # ========================================================
    # DIRECTORY LISTING
    # ========================================================

    if (
        "list files in" in command
        or "show files in" in command
        or "what is in" in command
        or "what's in" in command
    ):

        directory = extract_directory(
            user_input
        )

        if directory:

            if not tool_exists(
                "list_directory"
            ):
                return None

            result = list_directory(
                directory
            )

            return {
                "tool": "list_directory",
                "success": result.get(
                    "success",
                    False
                ),
                "data": result
            }

    # ========================================================
    # FIND FILE
    # ========================================================

    if (
        command.startswith("find ")
        and "file" in command
    ):

        filename = extract_filename(
            user_input
        )

        if filename:

            if not tool_exists(
                "find_file"
            ):
                return None

            result = find_file(
                filename
            )

            return {
                "tool": "find_file",
                "success": result.get(
                    "success",
                    False
                ),
                "data": result
            }

    # ========================================================
    # CHECK PATH
    # ========================================================

    if (
        command.startswith("does ")
        and "exist" in command
    ):

        path = extract_path(
            user_input
        )

        if path:

            if not tool_exists(
                "path_exists"
            ):
                return None

            result = path_exists(
                path
            )

            return {
                "tool": "path_exists",
                "success": result.get(
                    "success",
                    False
                ),
                "data": result
            }

    # ========================================================
    # LIST APPROVED APPLICATIONS
    # ========================================================

    application_list_keywords = [
        "what applications can you open",
        "what apps can you open",
        "which applications can you open",
        "which apps can you open",
        "list applications",
        "list apps"
    ]

    if any(
        keyword in command
        for keyword in application_list_keywords
    ):

        if not tool_exists(
            "list_applications"
        ):
            return None

        result = list_applications()

        return {
            "tool": "list_applications",
            "success": result.get(
                "success",
                False
            ),
            "data": result
        }

    # ========================================================
    # OPEN APPLICATION
    # ========================================================

    application = extract_application(
        user_input
    )

    if application:

        if not tool_exists(
            "open_application"
        ):
            return None

        result = open_application(
            application
        )

        return {
            "tool": "open_application",
            "success": result.get(
                "success",
                False
            ),
            "data": result
        }

    # ========================================================
    # NO TOOL
    # ========================================================

    return None


# ============================================================
# DIRECTORY EXTRACTION
# ============================================================

def extract_directory(user_input):
    """
    Extract a directory from common requests.
    """

    text = user_input.strip()
    lowered = text.lower()

    patterns = [
        "list files in ",
        "show files in ",
        "what is in ",
        "what's in "
    ]

    for pattern in patterns:

        if lowered.startswith(
            pattern
        ):

            return text[
                len(pattern):
            ].strip()

    return None


# ============================================================
# FILE EXTRACTION
# ============================================================

def extract_filename(user_input):
    """
    Extract a filename from a find request.
    """

    text = user_input.strip()
    lowered = text.lower()

    prefixes = [
        "find the file ",
        "find file ",
        "find "
    ]

    for prefix in prefixes:

        if lowered.startswith(
            prefix
        ):

            value = text[
                len(prefix):
            ].strip()

            value = value.rstrip(
                "?."
            )

            if value.lower().endswith(
                " file"
            ):

                value = value[:-5].strip()

            return value

    return None


# ============================================================
# PATH EXTRACTION
# ============================================================

def extract_path(user_input):
    """
    Extract a path from:

        Does memory.json exist?
        Does Benvin exist?
    """

    text = user_input.strip()
    lowered = text.lower()

    if lowered.startswith(
        "does "
    ):

        value = text[
            5:
        ].strip()

        if value.lower().endswith(
            " exist?"
        ):

            value = value[:-7]

        elif value.lower().endswith(
            " exist"
        ):

            value = value[:-6]

        return value.strip()

    return None


# ============================================================
# APPLICATION EXTRACTION
# ============================================================

def extract_application(
    user_input
):
    """
    Extract an approved application name
    from natural language.
    """

    text = user_input.strip()
    lowered = text.lower()

    patterns = [
        "open ",
        "launch ",
        "start ",
        "run "
    ]

    for pattern in patterns:

        if lowered.startswith(
            pattern
        ):

            application = text[
                len(pattern):
            ].strip()

            application = application.rstrip(
                "?.!"
            )

            if application:

                return application

    return None