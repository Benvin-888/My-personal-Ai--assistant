"""
BENVIN Filesystem Tools

Phase 1 filesystem foundation.

Responsibilities:

    - Safely inspect allowed directories.
    - Resolve common human-friendly filesystem aliases.
    - Check whether paths exist.
    - Search for files and folders.
    - Retrieve basic file information.
    - Protect BENVIN from accessing arbitrary filesystem locations.

IMPORTANT:

    These tools DO NOT decide whether an action is allowed.

    Permission decisions belong to:
        tools/permissions.py

    Parameter validation belongs to:
        tools/validator.py

    Tool execution is controlled by:
        tools/executor.py

    Tool definitions belong to:
        tools/registry.py


SAFE ROOTS:

    BENVIN currently permits filesystem inspection only
    inside:

        Desktop
        Documents
        Downloads

    The roots themselves and everything beneath them
    are allowed.

    This is intentionally restrictive during Phase 1.

    Future versions can expand this through a dedicated
    filesystem policy layer rather than weakening this file.
"""

import os

from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

USER_HOME = Path.home()


# ============================================================
# BENVIN DIRECTORY
# ============================================================

BENVIN_DIRECTORY = (
    USER_HOME
    / "Desktop"
    / "Benvin"
)


# ============================================================
# SAFE ROOT DIRECTORIES
# ============================================================

SAFE_ROOTS = [
    USER_HOME / "Desktop",
    USER_HOME / "Documents",
    USER_HOME / "Downloads",
]


# ============================================================
# SEARCH LIMITS
# ============================================================

MAX_SEARCH_RESULTS = 50

MAX_DIRECTORY_ENTRIES = 1000


# ============================================================
# HUMAN PATH ALIASES
# ============================================================

"""
Human-friendly names that BENVIN can translate into
real filesystem locations.

These aliases do NOT expand filesystem permissions.

Every resolved path is still checked by is_safe_path().

Examples:

    "desktop"
        -> C:\\Users\\User\\Desktop

    "my desktop"
        -> C:\\Users\\User\\Desktop

    "desktop folder"
        -> C:\\Users\\User\\Desktop

    "documents"
        -> C:\\Users\\User\\Documents

    "downloads"
        -> C:\\Users\\User\\Downloads

    "benvin"
        -> C:\\Users\\User\\Desktop\\Benvin

    "my benvin folder"
        -> C:\\Users\\User\\Desktop\\Benvin

    "benvin folder"
        -> C:\\Users\\User\\Desktop\\Benvin
"""


PATH_ALIASES = {
    # --------------------------------------------------------
    # Desktop
    # --------------------------------------------------------

    "desktop":
        USER_HOME / "Desktop",

    "my desktop":
        USER_HOME / "Desktop",

    "desktop folder":
        USER_HOME / "Desktop",

    "my desktop folder":
        USER_HOME / "Desktop",

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    "documents":
        USER_HOME / "Documents",

    "document":
        USER_HOME / "Documents",

    "my documents":
        USER_HOME / "Documents",

    "documents folder":
        USER_HOME / "Documents",

    "my documents folder":
        USER_HOME / "Documents",

    # --------------------------------------------------------
    # Downloads
    # --------------------------------------------------------

    "downloads":
        USER_HOME / "Downloads",

    "download":
        USER_HOME / "Downloads",

    "downloads folder":
        USER_HOME / "Downloads",

    "my downloads":
        USER_HOME / "Downloads",

    "my downloads folder":
        USER_HOME / "Downloads",

    # --------------------------------------------------------
    # BENVIN
    # --------------------------------------------------------

    "benvin":
        BENVIN_DIRECTORY,

    "benvin folder":
        BENVIN_DIRECTORY,

    "my benvin":
        BENVIN_DIRECTORY,

    "my benvin folder":
        BENVIN_DIRECTORY,

    "the benvin folder":
        BENVIN_DIRECTORY,

    "my benvin directory":
        BENVIN_DIRECTORY,

    "benvin directory":
        BENVIN_DIRECTORY,
}


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _normalize_alias_text(value):
    """
    Normalize human-friendly path text.

    This is intentionally conservative.

    It is used only for alias matching and does not
    modify real filesystem paths.
    """

    if not isinstance(value, str):
        return ""

    value = value.strip().lower()

    # Collapse repeated whitespace.
    value = " ".join(
        value.split()
    )

    return value


def _resolve_alias(path):
    """
    Resolve a known human-friendly filesystem alias.

    Returns:

        Path | None

    None means that the supplied value is not a
    recognized alias.
    """

    if not isinstance(path, str):
        return None

    normalized = _normalize_alias_text(
        path
    )

    if not normalized:
        return None

    alias = PATH_ALIASES.get(
        normalized
    )

    if alias is None:
        return None

    return alias


def _normalize_path(path):
    """
    Convert a user-provided path into a normalized
    Path object.

    Human-friendly aliases are resolved first.

    Returns:

        Path | None
    """

    # --------------------------------------------------------
    # Existing Path object
    # --------------------------------------------------------

    if isinstance(path, Path):

        raw_path = path

    # --------------------------------------------------------
    # String path
    # --------------------------------------------------------

    elif isinstance(path, str):

        path = path.strip()

        if not path:
            return None

        # ----------------------------------------------------
        # Try BENVIN human aliases first.
        # ----------------------------------------------------

        alias_path = _resolve_alias(
            path
        )

        if alias_path is not None:

            raw_path = alias_path

        else:

            raw_path = Path(
                path
            )

    else:

        return None

    # --------------------------------------------------------
    # Resolve filesystem path.
    # --------------------------------------------------------

    try:

        return raw_path.expanduser().resolve()

    except (
        OSError,
        RuntimeError
    ):

        return None


def resolve_path(path):
    """
    Resolve a user-provided filesystem path.

    Supports:

        - normal filesystem paths
        - Path objects
        - BENVIN aliases

    Examples:

        resolve_path("Desktop")

        resolve_path("my Benvin folder")

        resolve_path("C:\\Users\\User\\Desktop")

    Returns:

        Path

    Raises:

        ValueError:
            If the supplied path is invalid.
    """

    resolved = _normalize_path(
        path
    )

    if resolved is None:

        raise ValueError(
            "Invalid filesystem path."
        )

    return resolved


def _resolved_safe_roots():
    """
    Return normalized safe root directories.

    Invalid roots are ignored.

    Returns:

        list[Path]
    """

    roots = []

    for root in SAFE_ROOTS:

        try:

            resolved = (
                root
                .expanduser()
                .resolve()
            )

            roots.append(
                resolved
            )

        except (
            OSError,
            RuntimeError
        ):

            continue

    return roots


def is_safe_path(path):
    """
    Check whether a path is inside one of BENVIN's
    approved filesystem roots.

    Allowed roots:

        Desktop
        Documents
        Downloads

    The roots themselves are also allowed.

    Returns:

        bool
    """

    resolved = _normalize_path(
        path
    )

    if resolved is None:
        return False

    for root in _resolved_safe_roots():

        try:

            resolved.relative_to(
                root
            )

            return True

        except ValueError:

            continue

    return False


def _safe_path_error(path):
    """
    Build a consistent access-denied response.
    """

    return {
        "success": False,

        "error": (
            "Access denied. This path is outside "
            "BENVIN's safe filesystem areas."
        ),

        "path": str(path)
    }


def _path_type(path):
    """
    Determine whether a path is a file or folder.

    Returns:

        "file"
        "folder"
        None
    """

    try:

        if path.is_dir():
            return "folder"

        if path.is_file():
            return "file"

    except OSError:

        return None

    return None


# ============================================================
# PATH RESOLUTION INFORMATION
# ============================================================

def resolve_user_path(path):
    """
    Resolve a human-friendly path without performing
    a filesystem action.

    This function is useful for debugging and testing
    BENVIN's path understanding.

    Returns:

        {
            "success": True,
            "input": "...",
            "resolved_path": "...",
            "safe": True
        }
    """

    try:

        resolved = resolve_path(
            path
        )

    except ValueError as error:

        return {
            "success": False,
            "input": path,
            "error": str(error)
        }

    return {
        "success": True,
        "input": str(path),
        "resolved_path": str(resolved),
        "safe": is_safe_path(
            resolved
        )
    }


# ============================================================
# SAFE ROOT INFORMATION
# ============================================================

def get_safe_roots():
    """
    Return the filesystem roots currently available
    to BENVIN.

    This is informational and does not expose arbitrary
    filesystem locations.
    """

    roots = []

    for root in _resolved_safe_roots():

        roots.append(
            str(root)
        )

    return {
        "success": True,
        "roots": roots
    }


# ============================================================
# LIST DIRECTORY
# ============================================================

def list_directory(path=None):
    """
    List files and folders inside a safe directory.

    Defaults to the user's Desktop.

    Supports human-friendly paths such as:

        Desktop
        my desktop
        Benvin
        my Benvin folder
        Documents
        Downloads

    Returns:

        {
            "success": True,
            "path": "...",
            "items": [...],
            "count": 10,
            "limited": False
        }
    """

    # --------------------------------------------------------
    # Default path
    # --------------------------------------------------------

    if path is None:

        path = USER_HOME / "Desktop"

    # --------------------------------------------------------
    # Resolve
    # --------------------------------------------------------

    try:

        path = resolve_path(
            path
        )

    except ValueError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Security
    # --------------------------------------------------------

    if not is_safe_path(path):

        return _safe_path_error(
            path
        )

    # --------------------------------------------------------
    # Existence
    # --------------------------------------------------------

    try:

        if not path.exists():

            return {
                "success": False,
                "path": str(path),
                "error": (
                    f"Directory does not exist: {path}"
                )
            }

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Directory check
    # --------------------------------------------------------

    try:

        if not path.is_dir():

            return {
                "success": False,
                "path": str(path),
                "error": (
                    f"Not a directory: {path}"
                )
            }

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Read directory
    # --------------------------------------------------------

    try:

        entries = list(
            path.iterdir()
        )

    except PermissionError:

        return {
            "success": False,
            "path": str(path),
            "error": (
                "Permission denied while reading "
                "this directory."
            )
        }

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Output limit
    # --------------------------------------------------------

    limited = False

    if len(entries) > MAX_DIRECTORY_ENTRIES:

        entries = entries[
            :MAX_DIRECTORY_ENTRIES
        ]

        limited = True

    # --------------------------------------------------------
    # Sort
    #
    # Folders first, then files.
    # --------------------------------------------------------

    entries.sort(
        key=lambda item: (
            not item.is_dir(),
            item.name.lower()
        )
    )

    # --------------------------------------------------------
    # Build result
    # --------------------------------------------------------

    items = []

    for item in entries:

        try:

            item_type = (
                "folder"
                if item.is_dir()
                else "file"
                if item.is_file()
                else "other"
            )

        except OSError:

            item_type = "unknown"

        items.append({
            "name": item.name,
            "type": item_type
        })

    return {
        "success": True,
        "path": str(path),
        "items": items,
        "count": len(items),
        "limited": limited
    }


# ============================================================
# CHECK PATH
# ============================================================

def path_exists(path):
    """
    Check whether a safe file or directory exists.

    Supports human-friendly aliases.

    Returns:

        {
            "success": True,
            "path": "...",
            "exists": True,
            "type": "file"
        }
    """

    # --------------------------------------------------------
    # Resolve
    # --------------------------------------------------------

    try:

        path = resolve_path(
            path
        )

    except ValueError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Security
    # --------------------------------------------------------

    if not is_safe_path(path):

        return _safe_path_error(
            path
        )

    # --------------------------------------------------------
    # Existence
    # --------------------------------------------------------

    try:

        exists = path.exists()

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Type
    # --------------------------------------------------------

    item_type = None

    if exists:

        item_type = _path_type(
            path
        )

    return {
        "success": True,
        "path": str(path),
        "exists": exists,
        "type": item_type
    }


# ============================================================
# FIND FILE
# ============================================================

def find_file(
    filename,
    search_root=None
):
    """
    Search recursively for a file or folder.

    By default, BENVIN searches the user's Desktop.

    Supports human-friendly search roots:

        Desktop
        Benvin
        my Benvin folder
        Documents
        Downloads

    Matching is case-insensitive.

    Both files and folders may be matched.

    Results are limited to MAX_SEARCH_RESULTS.
    """

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not isinstance(
        filename,
        str
    ):

        return {
            "success": False,
            "error": (
                "Filename must be a string."
            )
        }

    filename = filename.strip()

    if not filename:

        return {
            "success": False,
            "error": (
                "Filename cannot be empty."
            )
        }

    # --------------------------------------------------------
    # Default search root
    # --------------------------------------------------------

    if search_root is None:

        search_root = USER_HOME / "Desktop"

    # --------------------------------------------------------
    # Resolve search root
    # --------------------------------------------------------

    try:

        search_root = resolve_path(
            search_root
        )

    except ValueError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Security
    # --------------------------------------------------------

    if not is_safe_path(
        search_root
    ):

        return {
            "success": False,
            "error": (
                "Access denied. Search location "
                "is outside BENVIN's safe areas."
            ),
            "search_root": str(
                search_root
            )
        }

    # --------------------------------------------------------
    # Existence
    # --------------------------------------------------------

    try:

        if not search_root.exists():

            return {
                "success": False,
                "error": (
                    f"Search directory does not exist: "
                    f"{search_root}"
                )
            }

    except OSError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Directory check
    # --------------------------------------------------------

    try:

        if not search_root.is_dir():

            return {
                "success": False,
                "error": (
                    f"Search root is not a directory: "
                    f"{search_root}"
                )
            }

    except OSError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    matches = []

    filename_lower = filename.lower()

    try:

        for root, dirs, files in os.walk(
            search_root,
            topdown=True
        ):

            # ------------------------------------------------
            # Security:
            #
            # Prevent traversal outside safe roots.
            # ------------------------------------------------

            safe_dirs = []

            for directory in dirs:

                directory_path = (
                    Path(root)
                    / directory
                )

                if is_safe_path(
                    directory_path
                ):

                    safe_dirs.append(
                        directory
                    )

            dirs[:] = safe_dirs

            # ------------------------------------------------
            # Search directories
            # ------------------------------------------------

            for directory in dirs:

                if (
                    directory.lower()
                    == filename_lower
                ):

                    matches.append(
                        str(
                            Path(root)
                            / directory
                        )
                    )

                    if (
                        len(matches)
                        >= MAX_SEARCH_RESULTS
                    ):

                        return {
                            "success": True,
                            "filename": filename,
                            "search_root": str(
                                search_root
                            ),
                            "matches": matches,
                            "count": len(matches),
                            "limited": True
                        }

            # ------------------------------------------------
            # Search files
            # ------------------------------------------------

            for file in files:

                if (
                    file.lower()
                    == filename_lower
                ):

                    matches.append(
                        str(
                            Path(root)
                            / file
                        )
                    )

                    if (
                        len(matches)
                        >= MAX_SEARCH_RESULTS
                    ):

                        return {
                            "success": True,
                            "filename": filename,
                            "search_root": str(
                                search_root
                            ),
                            "matches": matches,
                            "count": len(matches),
                            "limited": True
                        }

    except PermissionError as error:

        return {
            "success": False,
            "filename": filename,
            "search_root": str(
                search_root
            ),
            "error": (
                f"Permission denied during search: "
                f"{error}"
            )
        }

    except OSError as error:

        return {
            "success": False,
            "filename": filename,
            "search_root": str(
                search_root
            ),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Completed search
    # --------------------------------------------------------

    return {
        "success": True,
        "filename": filename,
        "search_root": str(
            search_root
        ),
        "matches": matches,
        "count": len(matches),
        "limited": False
    }


# ============================================================
# FILE INFORMATION
# ============================================================

def get_file_info(path):
    """
    Return basic information about a safe file or folder.

    Supports human-friendly aliases.

    Directory size is not calculated recursively because
    that can be expensive and is unnecessary for Phase 1.
    """

    # --------------------------------------------------------
    # Resolve
    # --------------------------------------------------------

    try:

        path = resolve_path(
            path
        )

    except ValueError as error:

        return {
            "success": False,
            "error": str(error)
        }

    # --------------------------------------------------------
    # Security
    # --------------------------------------------------------

    if not is_safe_path(path):

        return _safe_path_error(
            path
        )

    # --------------------------------------------------------
    # Existence
    # --------------------------------------------------------

    try:

        if not path.exists():

            return {
                "success": False,
                "path": str(path),
                "error": (
                    f"Path does not exist: {path}"
                )
            }

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Type
    # --------------------------------------------------------

    item_type = _path_type(
        path
    )

    if item_type is None:

        return {
            "success": False,
            "path": str(path),
            "error": (
                "Unable to determine the type "
                "of this path."
            )
        }

    # --------------------------------------------------------
    # Stat
    # --------------------------------------------------------

    try:

        stat = path.stat()

    except PermissionError:

        return {
            "success": False,
            "path": str(path),
            "error": (
                "Permission denied while reading "
                "file information."
            )
        }

    except OSError as error:

        return {
            "success": False,
            "path": str(path),
            "error": str(error)
        }

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {
        "success": True,
        "path": str(path),
        "name": path.name,
        "type": item_type,
        "size_bytes": (
            stat.st_size
            if item_type == "file"
            else None
        )
    }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("BENVIN FILESYSTEM TOOL TEST")
    print("=" * 60)

    print()
    print("Safe roots:")
    print(
        get_safe_roots()
    )

    print()
    print("Path alias tests:")

    aliases_to_test = [
        "Desktop",
        "my desktop",
        "Benvin",
        "my Benvin folder",
        "Documents",
        "Downloads",
        r"C:\Windows"
    ]

    for alias in aliases_to_test:

        print()
        print(
            f"Input: {alias}"
        )

        print(
            resolve_user_path(
                alias
            )
        )

    print()
    print("Desktop contents:")

    desktop_result = list_directory(
        "Desktop"
    )

    print(
        desktop_result
    )

    print()
    print("BENVIN contents:")

    benvin_result = list_directory(
        "my Benvin folder"
    )

    print(
        benvin_result
    )

    print()
    print("BENVIN main.py search:")

    main_result = find_file(
        "main.py",
        "my Benvin folder"
    )

    print(
        main_result
    )

    print()
    print("Windows security test:")

    windows_result = list_directory(
        r"C:\Windows"
    )

    print(
        windows_result
    )

    print()
    print("=" * 60)
    print("FILESYSTEM TOOL TEST COMPLETE")
    print("=" * 60)