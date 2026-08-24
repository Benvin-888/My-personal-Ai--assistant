"""
BENVIN Context / State Engine

This module manages BENVIN's short-term working context.

IMPORTANT DISTINCTION:

    memory.py
        Long-term persistent user knowledge.

    context.py
        Short-term session and task state.

Context is intended for information such as:

    - current conversation
    - current task
    - last user request
    - last BENVIN response
    - last action
    - last tool result
    - active application
    - task status

The context can later be expanded into a more advanced
task/state machine without changing the long-term memory
system.
"""

import json
import os
import uuid
from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

CONTEXT_FILE = "context.json"

MAX_MESSAGES = 20

MAX_TOOL_RESULTS = 10


# ============================================================
# INTERNAL HELPERS
# ============================================================

def generate_context_id():
    """
    Generate a unique context/session ID.
    """

    return f"ctx_{uuid.uuid4().hex[:12]}"


def current_timestamp():
    """
    Return the current UTC timestamp.
    """

    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ============================================================
# DEFAULT CONTEXT
# ============================================================

def create_default_context():
    """
    Create a completely new BENVIN session context.
    """

    timestamp = current_timestamp()

    return {
        "session_id": generate_context_id(),

        "created_at": timestamp,

        "updated_at": timestamp,

        "conversation": [],

        "current_task": {
            "active": False,
            "id": None,
            "description": None,
            "status": "idle",
            "started_at": None,
            "updated_at": None
        },

        "last_action": None,

        "last_tool_result": None,

        "active_application": None,

        "variables": {}
    }


# ============================================================
# LOAD CONTEXT
# ============================================================

def load_context():
    """
    Load the current context from disk.

    If no context exists, create a fresh context.
    """

    if not os.path.exists(
        CONTEXT_FILE
    ):
        return create_default_context()

    try:

        with open(
            CONTEXT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            context = json.load(
                file
            )

    except (
        json.JSONDecodeError,
        OSError
    ):

        return create_default_context()

    if not isinstance(
        context,
        dict
    ):

        return create_default_context()

    # --------------------------------------------------------
    # Ensure required structures exist
    # --------------------------------------------------------

    default = create_default_context()

    for key, value in default.items():

        if key not in context:
            context[key] = value

    return context


# ============================================================
# SAVE CONTEXT
# ============================================================

def save_context(context):
    """
    Persist the current context.
    """

    if not isinstance(
        context,
        dict
    ):
        raise TypeError(
            "Context must be a dictionary."
        )

    context["updated_at"] = (
        current_timestamp()
    )

    with open(
        CONTEXT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            context,
            file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# SESSION
# ============================================================

def get_session_id():
    """
    Return the current BENVIN session ID.
    """

    context = load_context()

    return context.get(
        "session_id"
    )


# ============================================================
# CONVERSATION
# ============================================================

def add_message(
    role,
    content
):
    """
    Add a message to the short-term conversation context.

    Valid roles:

        user
        assistant
        system
        tool
    """

    if not isinstance(
        role,
        str
    ):
        raise TypeError(
            "Message role must be a string."
        )

    if not isinstance(
        content,
        str
    ):
        raise TypeError(
            "Message content must be a string."
        )

    role = role.strip().lower()

    allowed_roles = {
        "user",
        "assistant",
        "system",
        "tool"
    }

    if role not in allowed_roles:
        raise ValueError(
            f"Invalid message role: {role}"
        )

    context = load_context()

    context["conversation"].append({
        "role": role,
        "content": content,
        "timestamp": current_timestamp()
    })

    # Keep context bounded.
    if len(
        context["conversation"]
    ) > MAX_MESSAGES:

        context["conversation"] = (
            context["conversation"][
                -MAX_MESSAGES:
            ]
        )

    save_context(
        context
    )

    return context["conversation"][-1]


def get_conversation(
    limit=None
):
    """
    Return recent conversation messages.
    """

    context = load_context()

    conversation = context.get(
        "conversation",
        []
    )

    if limit is None:
        return conversation

    if limit <= 0:
        return []

    return conversation[-limit:]


def clear_conversation():
    """
    Clear only the short-term conversation.

    Long-term memory is NOT affected.
    """

    context = load_context()

    context["conversation"] = []

    save_context(
        context
    )


# ============================================================
# CURRENT TASK
# ============================================================

def start_task(
    description
):
    """
    Start a new task.
    """

    if not isinstance(
        description,
        str
    ):
        raise TypeError(
            "Task description must be a string."
        )

    description = description.strip()

    if not description:
        raise ValueError(
            "Task description cannot be empty."
        )

    context = load_context()

    task_id = (
        f"task_{uuid.uuid4().hex[:12]}"
    )

    timestamp = current_timestamp()

    context["current_task"] = {
        "active": True,
        "id": task_id,
        "description": description,
        "status": "running",
        "started_at": timestamp,
        "updated_at": timestamp
    }

    save_context(
        context
    )

    return context["current_task"]


def get_current_task():
    """
    Return the current task.
    """

    context = load_context()

    return context.get(
        "current_task"
    )


def update_task(
    status=None,
    description=None
):
    """
    Update the active task.
    """

    context = load_context()

    task = context.get(
        "current_task"
    )

    if not isinstance(
        task,
        dict
    ):
        return None

    if status is not None:

        task["status"] = status

    if description is not None:

        task["description"] = (
            description
        )

    task["updated_at"] = (
        current_timestamp()
    )

    save_context(
        context
    )

    return task


def complete_task():
    """
    Mark the current task as completed.
    """

    context = load_context()

    task = context.get(
        "current_task"
    )

    if not isinstance(
        task,
        dict
    ):
        return None

    task["active"] = False

    task["status"] = "completed"

    task["updated_at"] = (
        current_timestamp()
    )

    save_context(
        context
    )

    return task


def cancel_task():
    """
    Cancel the current task.
    """

    context = load_context()

    task = context.get(
        "current_task"
    )

    if not isinstance(
        task,
        dict
    ):
        return None

    task["active"] = False

    task["status"] = "cancelled"

    task["updated_at"] = (
        current_timestamp()
    )

    save_context(
        context
    )

    return task


# ============================================================
# LAST ACTION
# ============================================================

def set_last_action(
    action,
    parameters=None
):
    """
    Store the most recent executed action.
    """

    context = load_context()

    context["last_action"] = {
        "action": action,
        "parameters": (
            parameters
            if isinstance(
                parameters,
                dict
            )
            else {}
        ),
        "timestamp": current_timestamp()
    }

    save_context(
        context
    )

    return context["last_action"]


def get_last_action():
    """
    Return the last executed action.
    """

    context = load_context()

    return context.get(
        "last_action"
    )


# ============================================================
# TOOL RESULTS
# ============================================================

def set_last_tool_result(
    result
):
    """
    Store the most recent tool result.
    """

    context = load_context()

    context["last_tool_result"] = {
        "result": result,
        "timestamp": current_timestamp()
    }

    save_context(
        context
    )

    return context["last_tool_result"]


def get_last_tool_result():
    """
    Return the most recent tool result.
    """

    context = load_context()

    return context.get(
        "last_tool_result"
    )


# ============================================================
# ACTIVE APPLICATION
# ============================================================

def set_active_application(
    application
):
    """
    Record the application BENVIN currently considers
    active.
    """

    context = load_context()

    context["active_application"] = (
        application
    )

    save_context(
        context
    )

    return application


def get_active_application():
    """
    Return the current active application.
    """

    context = load_context()

    return context.get(
        "active_application"
    )


# ============================================================
# VARIABLES
# ============================================================

def set_variable(
    name,
    value
):
    """
    Store a temporary session variable.
    """

    if not isinstance(
        name,
        str
    ):
        raise TypeError(
            "Variable name must be a string."
        )

    name = name.strip()

    if not name:
        raise ValueError(
            "Variable name cannot be empty."
        )

    context = load_context()

    context["variables"][name] = value

    save_context(
        context
    )

    return value


def get_variable(
    name,
    default=None
):
    """
    Retrieve a temporary session variable.
    """

    context = load_context()

    return context.get(
        "variables",
        {}
    ).get(
        name,
        default
    )


def delete_variable(
    name
):
    """
    Delete a temporary session variable.
    """

    context = load_context()

    variables = context.get(
        "variables",
        {}
    )

    if name not in variables:
        return False

    del variables[name]

    save_context(
        context
    )

    return True


# ============================================================
# CONTEXT SNAPSHOT
# ============================================================

def get_context_snapshot():
    """
    Return a clean snapshot of the current context.

    This will eventually be supplied to the brain when
    generating intents.
    """

    context = load_context()

    return {
        "session_id": context.get(
            "session_id"
        ),

        "conversation": context.get(
            "conversation",
            []
        )[-MAX_MESSAGES:],

        "current_task": context.get(
            "current_task"
        ),

        "last_action": context.get(
            "last_action"
        ),

        "last_tool_result": context.get(
            "last_tool_result"
        ),

        "active_application": context.get(
            "active_application"
        ),

        "variables": context.get(
            "variables",
            {}
        )
    }


# ============================================================
# RESET SESSION
# ============================================================

def reset_context():
    """
    Completely reset the current short-term context.

    This does NOT modify memory.json.
    """

    context = create_default_context()

    save_context(
        context
    )

    return context