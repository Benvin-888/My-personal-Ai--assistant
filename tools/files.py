import os
from pathlib import Path


# ============================================================
# SAFE ROOT DIRECTORIES
# ============================================================

USER_HOME = Path.home()

SAFE_ROOTS = [
    USER_HOME / "Desktop",
    USER_HOME / "Documents",
    USER_HOME / "Downloads",
]


# ============================================================
# INTERNAL HELPERS
# ============================================================

def is_safe_path(path):
    """
    Check whether a path is inside one of the allowed
    BENVIN filesystem roots.
    """

    try:
        resolved = Path(path).expanduser().resolve()

        for root in SAFE_ROOTS:

            root = root.resolve()

            try:
                resolved.relative_to(root)
                return True

            except ValueError:
                continue

        return False

    except (OSError, RuntimeError):
        return False


def resolve_path(path):
    """
    Resolve a user-provided path.
    """

    return Path(path).expanduser().resolve()


# ============================================================
# LIST DIRECTORY
# ============================================================

def list_directory(path=None):
    """
    List files and folders in a safe directory.

    Defaults to Desktop.
    """

    if path is None:
        path = USER_HOME / "Desktop"

    path = resolve_path(path)

    if not is_safe_path(path):

        return {
            "success": False,
            "error": "Access denied. This directory is outside BENVIN's safe areas."
        }

    if not path.exists():

        return {
            "success": False,
            "error": f"Directory does not exist: {path}"
        }

    if not path.is_dir():

        return {
            "success": False,
            "error": f"Not a directory: {path}"
        }

    try:

        items = []

        for item in sorted(
            path.iterdir(),
            key=lambda x: (not x.is_dir(), x.name.lower())
        ):

            items.append({
                "name": item.name,
                "type": "folder" if item.is_dir() else "file"
            })

        return {
            "success": True,
            "path": str(path),
            "items": items
        }

    except OSError as error:

        return {
            "success": False,
            "error": str(error)
        }


# ============================================================
# CHECK PATH
# ============================================================

def path_exists(path):
    """
    Check whether a file or directory exists.
    """

    path = resolve_path(path)

    if not is_safe_path(path):

        return {
            "success": False,
            "error": "Access denied. This path is outside BENVIN's safe areas."
        }

    return {
        "success": True,
        "path": str(path),
        "exists": path.exists(),
        "type": (
            "folder"
            if path.is_dir()
            else "file"
            if path.is_file()
            else None
        )
    }


# ============================================================
# FIND FILE
# ============================================================

def find_file(filename, search_root=None):
    """
    Search for a file inside an allowed directory.

    The search is recursive.
    """

    if search_root is None:
        search_root = USER_HOME / "Desktop"

    search_root = resolve_path(search_root)

    if not is_safe_path(search_root):

        return {
            "success": False,
            "error": "Access denied. Search location is outside BENVIN's safe areas."
        }

    if not search_root.exists():

        return {
            "success": False,
            "error": f"Search directory does not exist: {search_root}"
        }

    matches = []

    try:

        for root, dirs, files in os.walk(search_root):

            # Prevent hidden/unwanted traversal
            dirs[:] = [
                directory
                for directory in dirs
                if not directory.startswith(".")
            ]

            for file in files:

                if file.lower() == filename.lower():

                    matches.append(
                        str(
                            Path(root) / file
                        )
                    )

                    # Prevent excessive results
                    if len(matches) >= 50:

                        return {
                            "success": True,
                            "filename": filename,
                            "matches": matches,
                            "limited": True
                        }

        return {
            "success": True,
            "filename": filename,
            "matches": matches,
            "limited": False
        }

    except OSError as error:

        return {
            "success": False,
            "error": str(error)
        }


# ============================================================
# FILE INFORMATION
# ============================================================

def get_file_info(path):
    """
    Return basic information about a file or directory.
    """

    path = resolve_path(path)

    if not is_safe_path(path):

        return {
            "success": False,
            "error": "Access denied. This path is outside BENVIN's safe areas."
        }

    if not path.exists():

        return {
            "success": False,
            "error": f"Path does not exist: {path}"
        }

    try:

        stat = path.stat()

        return {
            "success": True,
            "path": str(path),
            "name": path.name,
            "type": (
                "folder"
                if path.is_dir()
                else "file"
            ),
            "size_bytes": stat.st_size if path.is_file() else None
        }

    except OSError as error:

        return {
            "success": False,
            "error": str(error)
        }