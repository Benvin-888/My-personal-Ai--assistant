"""
BENVIN Application Manager

Provides controlled access to approved Windows applications.

IMPORTANT:
BENVIN does not execute arbitrary shell commands.
Applications must exist in the allowlist below.
"""

import os
import shutil
import subprocess
from pathlib import Path


# ============================================================
# APPROVED APPLICATIONS
# ============================================================

APPLICATIONS = {
    "notepad": {
        "name": "Notepad",
        "aliases": [
            "notepad",
            "text editor",
            "editor"
        ],
        "executables": [
            "notepad.exe"
        ]
    },

    "calculator": {
        "name": "Calculator",
        "aliases": [
            "calculator",
            "calc",
            "windows calculator"
        ],
        "executables": [
            "calc.exe"
        ]
    },

    "explorer": {
        "name": "File Explorer",
        "aliases": [
            "explorer",
            "file explorer",
            "windows explorer"
        ],
        "executables": [
            "explorer.exe"
        ]
    },

    "vscode": {
        "name": "Visual Studio Code",
        "aliases": [
            "vscode",
            "vs code",
            "visual studio code",
            "code"
        ],
        "executables": [
            "code.exe",
            "Code.exe"
        ]
    },

    "chrome": {
        "name": "Google Chrome",
        "aliases": [
            "chrome",
            "google chrome"
        ],
        "executables": [
            "chrome.exe"
        ]
    }
}


# ============================================================
# FIND EXECUTABLE
# ============================================================

def find_executable(executable_name):
    """
    Find an approved executable.

    Search order:
    1. Windows PATH
    2. Known installation locations
    """

    # --------------------------------------------------------
    # 1. Search PATH
    # --------------------------------------------------------

    path_result = shutil.which(executable_name)

    if path_result:
        return path_result

    # --------------------------------------------------------
    # 2. Environment variables
    # --------------------------------------------------------

    local_app_data = Path(
        os.environ.get(
            "LOCALAPPDATA",
            ""
        )
    )

    program_files = Path(
        os.environ.get(
            "PROGRAMFILES",
            "C:\\Program Files"
        )
    )

    program_files_x86 = Path(
        os.environ.get(
            "PROGRAMFILES(X86)",
            "C:\\Program Files (x86)"
        )
    )

    # --------------------------------------------------------
    # 3. Known locations
    # --------------------------------------------------------

    candidates = [
        local_app_data
        / "Programs"
        / "Microsoft VS Code"
        / executable_name,

        local_app_data
        / "Programs"
        / "Microsoft VS Code"
        / "bin"
        / executable_name,

        program_files
        / "Google"
        / "Chrome"
        / "Application"
        / executable_name,

        program_files_x86
        / "Google"
        / "Chrome"
        / "Application"
        / executable_name
    ]

    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue

    return None


# ============================================================
# RESOLVE APPLICATION
# ============================================================

def resolve_application(application):
    """
    Convert a user-provided application name into
    an approved application definition.
    """

    if not application:
        return None, None

    text = application.lower().strip()

    # Direct application ID
    if text in APPLICATIONS:
        return text, APPLICATIONS[text]

    # Alias lookup
    for key, definition in APPLICATIONS.items():

        for alias in definition["aliases"]:

            if text == alias.lower():
                return key, definition

    return None, None


# ============================================================
# OPEN APPLICATION
# ============================================================

def open_application(application):
    """
    Open an approved Windows application.

    Returns a structured result dictionary.
    """

    key, definition = resolve_application(
        application
    )

    if definition is None:
        return {
            "success": False,
            "error": (
                f"Application '{application}' "
                "is not approved by BENVIN."
            )
        }

    executable_path = None

    # --------------------------------------------------------
    # Find executable
    # --------------------------------------------------------

    for executable in definition["executables"]:

        executable_path = find_executable(
            executable
        )

        if executable_path:
            break

    # --------------------------------------------------------
    # Executable not found
    # --------------------------------------------------------

    if executable_path is None:
        return {
            "success": False,
            "application": definition["name"],
            "error": (
                f"Could not locate "
                f"{definition['name']} "
                "on this computer."
            )
        }

    # --------------------------------------------------------
    # Launch application
    # --------------------------------------------------------

    try:

        process = subprocess.Popen(
            [executable_path],
            shell=False
        )

        return {
            "success": True,
            "application": definition["name"],
            "application_id": key,
            "executable": executable_path,
            "process_id": process.pid
        }

    except OSError as error:

        return {
            "success": False,
            "application": definition["name"],
            "error": str(error)
        }


# ============================================================
# LIST APPLICATIONS
# ============================================================

def list_applications():
    """
    Return all applications BENVIN is currently
    allowed to launch.
    """

    applications = []

    for key, definition in APPLICATIONS.items():

        applications.append({
            "id": key,
            "name": definition["name"],
            "aliases": definition["aliases"]
        })

    return {
        "success": True,
        "applications": applications
    }


# ============================================================
# CHECK APPLICATION
# ============================================================

def application_available(application):
    """
    Check whether an approved application exists
    on the computer without launching it.
    """

    key, definition = resolve_application(
        application
    )

    if definition is None:
        return False

    for executable in definition["executables"]:

        if find_executable(executable):
            return True

    return False