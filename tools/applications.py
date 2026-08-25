"""
BENVIN Application Tools

Safe application discovery and launching.

Available operations:

    list_applications()
    open_application(application)

IMPORTANT:

    The LLM never directly launches applications.

    The execution pipeline is:

        Brain
            ↓
        Validator
            ↓
        Permission Engine
            ↓
        Executor
            ↓
        Application Tool

SECURITY MODEL:

    BENVIN does NOT execute arbitrary executable paths.

    Applications must be explicitly defined in
    APPROVED_APPLICATIONS.

    User input is treated as an application name or alias,
    never as a shell command.

    subprocess is used without shell=True.
"""


import os
import shutil
import subprocess
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

WINDOWS = os.name == "nt"


# ============================================================
# APPROVED APPLICATIONS
# ============================================================

APPROVED_APPLICATIONS = {
    "notepad": {
        "name": "Notepad",
        "aliases": [
            "notepad",
            "text editor",
        ],
        "commands": [
            ["notepad.exe"],
        ],
    },

    "calculator": {
        "name": "Calculator",
        "aliases": [
            "calculator",
            "calc",
        ],
        "commands": [
            ["calc.exe"],
        ],
    },

    "paint": {
        "name": "Paint",
        "aliases": [
            "paint",
            "mspaint",
        ],
        "commands": [
            ["mspaint.exe"],
        ],
    },

    "file explorer": {
        "name": "File Explorer",
        "aliases": [
            "file explorer",
            "explorer",
            "windows explorer",
        ],
        "commands": [
            ["explorer.exe"],
        ],
    },

    "command prompt": {
        "name": "Command Prompt",
        "aliases": [
            "command prompt",
            "cmd",
        ],
        "commands": [
            ["cmd.exe"],
        ],
    },

    "powershell": {
        "name": "PowerShell",
        "aliases": [
            "powershell",
            "power shell",
        ],
        "commands": [
            ["powershell.exe"],
        ],
    },

    "chrome": {
        "name": "Google Chrome",
        "aliases": [
            "chrome",
            "google chrome",
        ],
        "commands": [
            [
                os.path.expandvars(
                    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
                )
            ],
            [
                os.path.expandvars(
                    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
                )
            ],
            [
                os.path.expandvars(
                    r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
                )
            ],
            ["chrome.exe"],
        ],
    },

    "edge": {
        "name": "Microsoft Edge",
        "aliases": [
            "edge",
            "microsoft edge",
        ],
        "commands": [
            [
                os.path.expandvars(
                    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
                )
            ],
            [
                os.path.expandvars(
                    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
                )
            ],
            ["msedge.exe"],
        ],
    },

    "vscode": {
        "name": "Visual Studio Code",
        "aliases": [
            "vscode",
            "vs code",
            "visual studio code",
            "code",
        ],
        "commands": [
            [
                os.path.expandvars(
                    r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"
                )
            ],
            [
                os.path.expandvars(
                    r"%ProgramFiles%\Microsoft VS Code\Code.exe"
                )
            ],
            ["code.exe"],
        ],
    },
}


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _normalize_name(value):
    """
    Normalize an application name for safe comparison.

    Returns:
        str
    """

    if not isinstance(
        value,
        str
    ):
        return ""

    return " ".join(
        value.strip().lower().split()
    )


def _find_application_key(application):
    """
    Find the canonical application key from an
    application name or alias.

    Returns:
        str | None
    """

    normalized = _normalize_name(
        application
    )

    if not normalized:
        return None

    for key, definition in APPROVED_APPLICATIONS.items():

        if normalized == _normalize_name(key):

            return key

        aliases = definition.get(
            "aliases",
            []
        )

        for alias in aliases:

            if normalized == _normalize_name(alias):

                return key

    return None


def _resolve_command(command):
    """
    Resolve an approved command.

    Commands may contain:

        - absolute executable paths
        - executable names available on PATH

    Returns:
        list[str] | None
    """

    if not isinstance(
        command,
        list
    ):
        return None

    if not command:
        return None

    executable = command[0]

    if not isinstance(
        executable,
        str
    ):
        return None

    executable = os.path.expandvars(
        executable
    )

    # --------------------------------------------------------
    # Absolute executable path
    # --------------------------------------------------------

    executable_path = Path(
        executable
    )

    if executable_path.is_absolute():

        if executable_path.exists() and executable_path.is_file():

            return [
                str(executable_path),
                *command[1:]
            ]

        return None

    # --------------------------------------------------------
    # Executable available on PATH
    # --------------------------------------------------------

    resolved = shutil.which(
        executable
    )

    if resolved:

        return [
            resolved,
            *command[1:]
        ]

    return None


def _get_available_command(definition):
    """
    Find the first working command for an approved
    application definition.

    Returns:
        list[str] | None
    """

    commands = definition.get(
        "commands",
        []
    )

    for command in commands:

        resolved = _resolve_command(
            command
        )

        if resolved:

            return resolved

    return None


# ============================================================
# LIST APPLICATIONS
# ============================================================

def list_applications():
    """
    Return the applications BENVIN is allowed to launch.

    The result also indicates whether an executable
    was found on the current computer.

    Returns:
        dict
    """

    applications = []

    for key, definition in APPROVED_APPLICATIONS.items():

        command = _get_available_command(
            definition
        )

        applications.append({
            "id": key,
            "name": definition.get(
                "name",
                key
            ),
            "aliases": definition.get(
                "aliases",
                []
            ),
            "available": command is not None
        })

    return {
        "success": True,
        "count": len(applications),
        "applications": applications
    }


# ============================================================
# OPEN APPLICATION
# ============================================================

def open_application(application):
    """
    Open an approved application.

    Parameters:
        application (str):
            Application name or approved alias.

    Returns:
        dict

    Security:

        - Only allowlisted applications can launch.
        - No shell commands are accepted.
        - shell=True is never used.
        - Arbitrary executable paths are rejected.
    """

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not isinstance(
        application,
        str
    ):

        return {
            "success": False,
            "error": (
                "Application name must be a string."
            )
        }

    application = application.strip()

    if not application:

        return {
            "success": False,
            "error": (
                "Application name cannot be empty."
            )
        }

    # --------------------------------------------------------
    # Find approved application
    # --------------------------------------------------------

    application_key = _find_application_key(
        application
    )

    if application_key is None:

        return {
            "success": False,
            "error": (
                f"Application '{application}' "
                "is not approved by BENVIN."
            )
        }

    definition = APPROVED_APPLICATIONS[
        application_key
    ]

    # --------------------------------------------------------
    # Find executable
    # --------------------------------------------------------

    command = _get_available_command(
        definition
    )

    if command is None:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": (
                f"The approved application "
                f"'{definition.get('name', application_key)}' "
                "could not be found on this computer."
            )
        }

    # --------------------------------------------------------
    # Windows check
    # --------------------------------------------------------

    if not WINDOWS:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": (
                "BENVIN Phase 1 application control "
                "currently supports Windows only."
            )
        }

    # --------------------------------------------------------
    # Launch
    # --------------------------------------------------------

    try:

        process = subprocess.Popen(
            command,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )

        return {
            "success": True,
            "application": definition.get(
                "name",
                application_key
            ),
            "application_id": application_key,
            "pid": process.pid,
            "status": "launched"
        }

    except FileNotFoundError:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": (
                "The application executable "
                "could not be found."
            )
        }

    except PermissionError:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": (
                "Windows denied permission to "
                "launch the application."
            )
        }

    except OSError as error:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": str(error)
        }

    except Exception as error:

        return {
            "success": False,
            "application": definition.get(
                "name",
                application_key
            ),
            "error": str(error)
        }