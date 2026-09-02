"""
BENVIN Brain

Responsibilities:
    1. Communicate with Ollama / Qwen3.
    2. Retrieve relevant BENVIN memories.
    3. Retrieve current short-term context.
    4. Build tool context from the central registry.
    5. Analyze natural-language requests.
    6. Produce structured conversation or action intents.
    7. Safely parse and normalize model output.
    8. Resolve simple contextual references.
    9. Convert completed tool results into natural language.

IMPORTANT:

    The brain NEVER executes tools.

    The brain may:
        - understand a request
        - select a registered action
        - build action parameters
        - use conversation context to resolve references

    The brain may NOT:
        - access the filesystem
        - launch applications
        - modify files
        - execute commands
        - claim an action happened

    The validator, permission engine, and executor remain
    the security boundary.


ARCHITECTURE:

    User
      ↓
    main.py
      ↓
    brain.py
      ↓
    structured intent
      ↓
    validator.py
      ↓
    permissions.py
      ↓
    executor.py
      ↓
    controlled tool
      ↓
    result
      ↓
    brain.py
      ↓
    natural-language response


IMPORTANT DESIGN RULE:

    Deterministic routing is used for requests where accuracy
    matters more than language creativity.

    Example:

        "what is my computer information?"

    MUST become:

        {
            "type": "action",
            "action": "system_info",
            "parameters": {}
        }

    It must never be left to a small local LLM to invent
    system information.


LONG-TERM MEMORY:

    memory.py
        Persistent user knowledge.


SHORT-TERM CONTEXT:

    context.py
        Current conversation and task state.
"""

import json
import re

import requests

from memory import search_memories

from context import (
    get_context_snapshot
)

from tools.registry import (
    list_tools,
    get_tool
)


# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL = "qwen3:1.7b"

# Qwen3:1.7B can be slow on an 8 GB RAM machine.
REQUEST_TIMEOUT = 300


# ============================================================
# OLLAMA COMMUNICATION
# ============================================================

def _ask_ollama(
    prompt,
    *,
    json_mode=False,
    think=False
):
    """
    Send a prompt to the local Ollama server.

    The brain only communicates with Ollama.

    It never executes computer actions.
    """

    if not isinstance(prompt, str):
        raise ValueError(
            "Prompt must be a string."
        )

    prompt = prompt.strip()

    if not prompt:
        raise ValueError(
            "Prompt cannot be empty."
        )

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": think
    }

    if json_mode:
        payload["format"] = "json"

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            "Ollama returned an invalid response."
        )

    result = data.get(
        "response",
        ""
    )

    if not isinstance(result, str):
        return ""

    return result.strip()


# ============================================================
# TOOL CONTEXT
# ============================================================

def build_tool_context():
    """
    Build the tool description supplied to Qwen3.

    The registry remains the single source of truth.

    Only enabled tools are presented to the model.
    """

    tools = []

    for action in list_tools():

        definition = get_tool(action)

        if definition is None:
            continue

        if not definition.get(
            "enabled",
            False
        ):
            continue

        tools.append({
            "action": action,

            "description": definition.get(
                "description",
                ""
            ),

            "risk": definition.get(
                "risk",
                "HIGH"
            ),

            "requires_confirmation": definition.get(
                "requires_confirmation",
                True
            ),

            "parameters": definition.get(
                "parameters",
                {}
            )
        })

    return json.dumps(
        tools,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# MEMORY CONTEXT
# ============================================================

def build_memory_context(user_input):
    """
    Retrieve relevant long-term memories.
    """

    try:

        memories = search_memories(
            user_input
        )

    except Exception:

        return ""

    if not memories:
        return ""

    context = []

    for memory in memories[:5]:

        if not isinstance(
            memory,
            dict
        ):
            continue

        content = memory.get(
            "content"
        )

        if not content:
            continue

        category = memory.get(
            "category"
        )

        if category:

            context.append(
                f"- [{category}] {content}"
            )

        else:

            context.append(
                f"- {content}"
            )

    return "\n".join(context)


# ============================================================
# SHORT-TERM CONTEXT
# ============================================================

def _get_context_snapshot():
    """
    Safely retrieve the current short-term context.
    """

    try:

        snapshot = get_context_snapshot()

    except Exception:

        return None

    if not isinstance(
        snapshot,
        dict
    ):

        return None

    return snapshot


def build_context_context():
    """
    Build short-term session context.

    Only recent conversation is supplied to the model.
    """

    snapshot = _get_context_snapshot()

    if snapshot is None:

        return (
            "No short-term context available."
        )

    conversation = snapshot.get(
        "conversation",
        []
    )

    if not isinstance(
        conversation,
        list
    ):

        conversation = []

    recent_conversation = conversation[-8:]

    context = {
        "session_id": snapshot.get(
            "session_id"
        ),

        "conversation": recent_conversation,

        "current_task": snapshot.get(
            "current_task"
        ),

        "last_action": snapshot.get(
            "last_action"
        ),

        "last_tool_result": snapshot.get(
            "last_tool_result"
        ),

        "active_application": snapshot.get(
            "active_application"
        ),

        "variables": snapshot.get(
            "variables",
            {}
        )
    }

    return json.dumps(
        context,
        indent=2,
        ensure_ascii=False,
        default=str
    )


# ============================================================
# CONTEXT REFERENCE HELPERS
# ============================================================

def _get_last_successful_action_context():
    """
    Retrieve useful information from the most recent
    short-term context.

    This function does NOT execute anything.

    It only reads context.py's stored state.
    """

    snapshot = _get_context_snapshot()

    if snapshot is None:
        return None

    last_action = snapshot.get(
        "last_action"
    )

    last_result = snapshot.get(
        "last_tool_result"
    )

    variables = snapshot.get(
        "variables",
        {}
    )

    if not isinstance(
        variables,
        dict
    ):
        variables = {}

    return {
        "last_action": last_action,
        "last_tool_result": last_result,
        "variables": variables
    }


def _resolve_contextual_path():
    """
    Try to recover a previous filesystem path from
    short-term context.

    This does NOT access the filesystem.
    """

    context = _get_last_successful_action_context()

    if context is None:
        return None

    last_action = context.get(
        "last_action"
    )

    last_result = context.get(
        "last_tool_result"
    )

    variables = context.get(
        "variables",
        {}
    )

    possible_values = [
        variables.get("current_path"),
        variables.get("last_path"),
        variables.get("search_root"),
        variables.get("current_directory"),
    ]

    for value in possible_values:

        if isinstance(
            value,
            str
        ) and value.strip():

            return value.strip()

    if isinstance(
        last_action,
        dict
    ):

        parameters = last_action.get(
            "parameters",
            {}
        )

        if isinstance(
            parameters,
            dict
        ):

            for key in (
                "path",
                "search_root"
            ):

                value = parameters.get(
                    key
                )

                if isinstance(
                    value,
                    str
                ) and value.strip():

                    return value.strip()

    if isinstance(
        last_result,
        dict
    ):

        for key in (
            "path",
            "directory",
            "search_root"
        ):

            value = last_result.get(
                key
            )

            if isinstance(
                value,
                str
            ) and value.strip():

                return value.strip()

    return None


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def _normalize_text(text):
    """
    Normalize user text for lightweight routing.
    """

    if not isinstance(
        text,
        str
    ):
        return ""

    text = text.strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ============================================================
# SYSTEM INFORMATION REQUEST DETECTION
# ============================================================

def _is_system_info_request(text):
    """
    Detect requests that require actual computer information.

    These requests MUST NOT be delegated to Qwen3 because
    Qwen3 does not have direct access to the computer.
    """

    if not isinstance(
        text,
        str
    ):
        return False

    normalized = _normalize_text(text)

    if not normalized:
        return False

    patterns = [
        r"\bwhat is my computer information\b",
        r"\bwhat is my computer info\b",
        r"\bwhat's my computer information\b",
        r"\bwhat's my computer info\b",

        r"\bwhat is my pc information\b",
        r"\bwhat is my pc info\b",
        r"\bwhat's my pc information\b",
        r"\bwhat's my pc info\b",

        r"\bwhat is my laptop information\b",
        r"\bwhat is my laptop info\b",
        r"\bwhat's my laptop information\b",
        r"\bwhat's my laptop info\b",

        r"\bshow my computer information\b",
        r"\bshow my computer info\b",
        r"\bshow my pc information\b",
        r"\bshow my pc info\b",

        r"\bshow my laptop information\b",
        r"\bshow my laptop info\b",

        r"\bget my computer information\b",
        r"\bget my computer info\b",
        r"\bget my pc information\b",
        r"\bget my pc info\b",

        r"\bget my laptop information\b",
        r"\bget my laptop info\b",

        r"\bcomputer specifications\b",
        r"\bcomputer specs\b",
        r"\bpc specifications\b",
        r"\bpc specs\b",
        r"\blaptop specifications\b",
        r"\blaptop specs\b",

        r"\bsystem information\b",
        r"\bsystem info\b",
    ]

    return any(
        re.search(
            pattern,
            normalized,
            re.IGNORECASE
        )
        for pattern in patterns
    )


# ============================================================
# SYSTEM HEALTH REQUEST DETECTION
# ============================================================

def _is_system_health_request(text):
    """
    Detect requests asking BENVIN to assess the actual
    computer's current health.

    These requests MUST be routed to the real
    system_health tool.

    Qwen3 must not guess the computer's health.
    """

    if not isinstance(
        text,
        str
    ):
        return False

    normalized = _normalize_text(text)

    if not normalized:
        return False

    patterns = [
        r"\bsystem health\b",
        r"\bcomputer health\b",
        r"\bpc health\b",
        r"\blaptop health\b",

        r"\bcheck my system health\b",
        r"\bcheck my computer health\b",
        r"\bcheck my pc health\b",
        r"\bcheck my laptop health\b",

        r"\bcheck system health\b",
        r"\bcheck computer health\b",
        r"\bcheck pc health\b",
        r"\bcheck laptop health\b",

        r"\bhow healthy is my computer\b",
        r"\bhow healthy is my pc\b",
        r"\bhow healthy is my laptop\b",

        r"\bis my computer healthy\b",
        r"\bis my pc healthy\b",
        r"\bis my laptop healthy\b",

        r"\bcheck my computer\b",
        r"\bcheck my pc\b",
        r"\bcheck my laptop\b",
    ]

    return any(
        re.search(
            pattern,
            normalized,
            re.IGNORECASE
        )
        for pattern in patterns
    )


# ============================================================
# FILENAME EXTRACTION
# ============================================================

def _extract_filename(text):
    """
    Extract a likely filename from a filesystem request.
    """

    if not isinstance(
        text,
        str
    ):
        return None

    pattern = re.compile(
        r"""
        (?:
            file\s+
        )?
        ["'`]?
        (
            [A-Za-z0-9_\-\.\\]+
            \.[A-Za-z0-9_\-]+
        )
        ["'`]?
        """,
        re.IGNORECASE | re.VERBOSE
    )

    match = pattern.search(
        text
    )

    if not match:
        return None

    filename = match.group(
        1
    ).strip()

    if not filename:
        return None

    return filename


# ============================================================
# REQUEST DETECTION
# ============================================================

def _is_find_file_request(text):
    """
    Detect obvious file-search requests.
    """

    patterns = [
        r"\bfind\b",
        r"\bsearch\s+for\b",
        r"\blook\s+for\b",
        r"\blocate\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


def _is_directory_listing_request(text):
    """
    Detect obvious directory-listing requests.
    """

    patterns = [
        r"\blist\b.*\bfiles?\b",
        r"\bshow\b.*\bfiles?\b",
        r"\bshow\b.*\bfolders?\b",
        r"\bwhat\b.*\bfiles?\b",
        r"\bwhat\b.*\bin\b.*\bfolder\b",
        r"\bcontents?\s+of\b",
        r"\bfiles?\s+in\b",
        r"\bwhat's\s+in\b",
        r"\bwhats\s+in\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


def _is_path_exists_request(text):
    """
    Detect obvious existence checks.
    """

    patterns = [
        r"\bdoes\b.*\bexist\b",
        r"\bis\b.*\bthere\b",
        r"\bcheck\b.*\bexist",
        r"\bcheck\b.*\bpath\b",
        r"\bcheck\b.*\bfile\b",
        r"\bcheck\b.*\bfolder\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


def _is_file_info_request(text):
    """
    Detect requests for information about a file/path.
    """

    patterns = [
        r"\bfile\s+info\b",
        r"\binformation\s+about\b",
        r"\bdetails\s+about\b",
        r"\bdetails\s+of\b",
        r"\bproperties\s+of\b",
        r"\bsize\s+of\b",
        r"\bfile\s+size\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


# ============================================================
# APPLICATION REQUEST DETECTION
# ============================================================

def _is_open_application_request(text):
    """
    Detect obvious requests to launch an application.
    """

    patterns = [
        r"\bopen\b",
        r"\blaunch\b",
        r"\bstart\b",
        r"\brun\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


def _is_list_applications_request(text):
    """
    Detect requests asking which applications BENVIN
    is allowed to open.
    """

    patterns = [
        r"\bwhat applications\b",
        r"\bwhich applications\b",
        r"\bwhat apps\b",
        r"\bwhich apps\b",
        r"\bwhat programs\b",
        r"\bwhich programs\b",
        r"\bwhat can you open\b",
        r"\bwhat can benvin open\b",
        r"\bwhat applications can you open\b",
        r"\bwhich applications can you open\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


def _extract_application_name(text):
    """
    Extract a likely application name from a launch request.
    """

    if not isinstance(
        text,
        str
    ):
        return None

    patterns = [
        r"\bopen\s+(?:the\s+)?(.+?)\s*$",
        r"\blaunch\s+(?:the\s+)?(.+?)\s*$",
        r"\bstart\s+(?:the\s+)?(.+?)\s*$",
        r"\brun\s+(?:the\s+)?(.+?)\s*$",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        application = match.group(
            1
        ).strip()

        if not application:
            continue

        application = re.sub(
            r"[.!?]+$",
            "",
            application
        ).strip()

        if not application:
            continue

        application = re.sub(
            r"\s+(?:please|for me)$",
            "",
            application,
            flags=re.IGNORECASE
        ).strip()

        if not application:
            continue

        return application

    return None


# ============================================================
# LOCATION EXTRACTION
# ============================================================

def _extract_location_hint(text):
    """
    Extract a simple human-readable location hint.

    This does NOT access the filesystem.
    """

    if not isinstance(
        text,
        str
    ):
        return None

    patterns = [

        r"\bin\s+(?:my\s+)?([A-Za-z0-9_\-\\ ]+?)\s+folder\b",

        r"\bin\s+(?:the\s+)?([A-Za-z0-9_\-\\ ]+?)\s+folder\b",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        location = match.group(
            1
        ).strip()

        if not location:
            continue

        location = re.sub(
            r"\s+(?:files?|folders?)$",
            "",
            location,
            flags=re.IGNORECASE
        ).strip()

        if location:
            return location

    return None


# ============================================================
# CONTEXT REFERENCE DETECTION
# ============================================================

def _contains_context_reference(text):
    """
    Detect common contextual references.
    """

    if not isinstance(
        text,
        str
    ):
        return False

    patterns = [
        r"\bthere\b",
        r"\bhere\b",
        r"\bit\b",
        r"\bthat\b",
        r"\bthe same\b",
        r"\bagain\b",
        r"\bthe file\b",
        r"\bthe folder\b",
        r"\bthe path\b",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in patterns
    )


# ============================================================
# DETERMINISTIC ACTION ROUTER
# ============================================================

def _build_deterministic_action_intent(
    user_input
):
    """
    Detect obvious computer actions before sending the
    request to the small local LLM.

    This is NOT a tool executor.

    It only creates an intent.

    The validator, permission system, and executor still
    control whether the action actually happens.
    """

    text = _normalize_text(
        user_input
    )

    if not text:
        return None

    # ========================================================
    # SYSTEM INFORMATION
    # ========================================================

    if _is_system_info_request(text):

        intent = {
            "type": "action",
            "action": "system_info",
            "parameters": {}
        }

        if _validate_registered_action(intent):
            return intent

        return None

    # ========================================================
    # SYSTEM HEALTH
    # ========================================================

    if _is_system_health_request(text):

        intent = {
            "type": "action",
            "action": "system_health",
            "parameters": {}
        }

        if _validate_registered_action(intent):
            return intent

        return None

    # ========================================================
    # LIST APPLICATIONS
    # ========================================================

    if _is_list_applications_request(text):

        intent = {
            "type": "action",
            "action": "list_applications",
            "parameters": {}
        }

        if _validate_registered_action(intent):
            return intent

        return None

    # ========================================================
    # OPEN APPLICATION
    # ========================================================

    if _is_open_application_request(text):

        application = _extract_application_name(
            text
        )

        if application:

            intent = {
                "type": "action",
                "action": "open_application",
                "parameters": {
                    "application": application
                }
            }

            if _validate_registered_action(intent):
                return intent

    # ========================================================
    # FIND FILE
    # ========================================================

    if (
        _is_find_file_request(text)
        and _extract_filename(text)
    ):

        filename = _extract_filename(
            text
        )

        location = _extract_location_hint(
            text
        )

        parameters = {
            "filename": filename
        }

        if location:

            parameters["search_root"] = location

        elif _contains_context_reference(text):

            previous_path = (
                _resolve_contextual_path()
            )

            if previous_path:

                parameters["search_root"] = previous_path

        intent = {
            "type": "action",
            "action": "find_file",
            "parameters": parameters
        }

        if _validate_registered_action(intent):
            return intent

    # ========================================================
    # LIST DIRECTORY
    # ========================================================

    if _is_directory_listing_request(text):

        location = _extract_location_hint(
            text
        )

        if location:

            path = location

        elif "desktop" in text:

            path = "Desktop"

        elif _contains_context_reference(text):

            previous_path = (
                _resolve_contextual_path()
            )

            if previous_path:

                path = previous_path

            else:

                path = "."

        else:

            path = "."

        intent = {
            "type": "action",
            "action": "list_directory",
            "parameters": {
                "path": path
            }
        }

        if _validate_registered_action(intent):
            return intent

    # ========================================================
    # PATH EXISTS
    # ========================================================

    if _is_path_exists_request(text):

        filename = _extract_filename(
            text
        )

        location = _extract_location_hint(
            text
        )

        if filename and location:

            path = f"{location}\\{filename}"

        elif filename:

            path = filename

        elif location:

            path = location

        elif _contains_context_reference(text):

            previous_path = (
                _resolve_contextual_path()
            )

            if previous_path:

                path = previous_path

            else:

                return None

        else:

            return None

        intent = {
            "type": "action",
            "action": "path_exists",
            "parameters": {
                "path": path
            }
        }

        if _validate_registered_action(intent):
            return intent

    # ========================================================
    # FILE INFORMATION
    # ========================================================

    if _is_file_info_request(text):

        filename = _extract_filename(
            text
        )

        location = _extract_location_hint(
            text
        )

        if filename and location:

            path = f"{location}\\{filename}"

        elif filename:

            path = filename

        elif location:

            path = location

        elif _contains_context_reference(text):

            previous_path = (
                _resolve_contextual_path()
            )

            if previous_path:

                path = previous_path

            else:

                return None

        else:

            return None

        intent = {
            "type": "action",
            "action": "get_file_info",
            "parameters": {
                "path": path
            }
        }

        if _validate_registered_action(intent):
            return intent

    return None


# ============================================================
# INTENT PROMPT
# ============================================================

def build_intent_prompt(user_input):
    """
    Build the structured-intent prompt for Qwen3.
    """

    tools = build_tool_context()

    memory_context = build_memory_context(
        user_input
    )

    short_term_context = (
        build_context_context()
    )

    if not memory_context:

        memory_context = (
            "No relevant long-term memories found."
        )

    return f"""
You are BENVIN's intent analysis engine.

BENVIN is a local personal AI assistant running
on the user's Windows computer.

Your ONLY job is to understand the user's request
and return ONE structured JSON intent.

You do NOT execute computer actions.

You do NOT have direct access to the computer.

============================================================
VALID INTENT TYPES
============================================================

There are exactly TWO normal intent types.

1. conversation

2. action

============================================================
CONVERSATION
============================================================

Use "conversation" when the user wants:

- an explanation
- an answer to a question
- general conversation
- programming help
- knowledge
- advice
- information that does not require a registered tool

Format:

{{
    "type": "conversation",
    "response": "Your concise answer."
}}

============================================================
ACTION
============================================================

Use "action" when the user asks BENVIN to perform
a computer operation using one of the registered tools.

Format:

{{
    "type": "action",
    "action": "registered_action_name",
    "parameters": {{
        "parameter_name": "value"
    }}
}}

============================================================
AVAILABLE TOOLS
============================================================

Only these tools may be selected:

{tools}

============================================================
IMPORTANT
============================================================

The AVAILABLE TOOLS section is the authoritative list.

Never invent an action.

Never invent a parameter.

Never invent a filesystem result.

Never invent computer information.

Never claim an action already happened.

The executor will perform the actual action later.

============================================================
SYSTEM INFORMATION
============================================================

If the user asks for actual information about their
computer, PC, laptop, operating system, processor,
memory, Python version, computer name, username,
disk, or system:

    use:

    {{
        "type": "action",
        "action": "system_info",
        "parameters": {{}}
    }}

Do NOT answer with guessed system information.

============================================================
SYSTEM HEALTH
============================================================

If the user asks to check, assess, inspect, or report
the actual health of their computer, PC, laptop, memory,
RAM, disk, or overall system condition:

    use:

    {{
        "type": "action",
        "action": "system_health",
        "parameters": {{}}
    }}

Do NOT guess the computer's health.

Do NOT invent RAM usage.

Do NOT invent disk usage.

Do NOT invent health warnings.

The system_health tool provides the actual information.

============================================================
COMMON ACTION MAPPINGS
============================================================

"find a file"
    -> find_file

"search for a file"
    -> find_file

"locate a file"
    -> find_file

"find main.py"
    -> find_file

"list files"
    -> list_directory

"list desktop files"
    -> list_directory

"show desktop files"
    -> list_directory

"show files in a folder"
    -> list_directory

"does main.py exist"
    -> path_exists

"check whether main.py exists"
    -> path_exists

"get information about main.py"
    -> get_file_info

"open Notepad"
    -> open_application

"launch Calculator"
    -> open_application

"what applications can you open"
    -> list_applications

"what apps can you open"
    -> list_applications

"what is my computer information"
    -> system_info

"show my computer specifications"
    -> system_info

"check my computer health"
    -> system_health

"check my system health"
    -> system_health

"what is Python"
    -> conversation

============================================================
CONTEXT
============================================================

Short-term context may contain previous conversation,
previous actions, and actual execution results.

Use it to understand references such as:

- it
- that
- the file
- the application
- there
- here
- again
- continue

However:

Previous assistant text is NOT evidence that an action
actually happened.

Only an actual execution result supplied by the execution
system is evidence that an action happened.

Do not invent missing context.

============================================================
LONG-TERM MEMORY
============================================================

{memory_context}

============================================================
CURRENT SHORT-TERM CONTEXT
============================================================

{short_term_context}

============================================================
STRICT OUTPUT RULES
============================================================

1. Return ONLY ONE valid JSON object.

2. Do NOT use Markdown.

3. Do NOT use code fences.

4. The root object must contain "type".

5. "type" must be exactly "conversation" or "action".

6. Conversation intents must contain:
       "response": string

7. Action intents must contain:
       "action": string
       "parameters": object

8. Only use registered actions.

9. Only use parameters defined by the selected tool.

10. Do not add unnecessary fields.

11. Never execute tools.

12. Never claim a computer action happened.

13. Never invent a filesystem result.

14. Never invent system information.

15. Never invent system health information.

16. If the user asks a normal knowledge question,
    use "conversation".

17. If the user clearly asks for a registered computer
    operation, use "action".

18. If the request is ambiguous and does not clearly
    require a computer action, use "conversation".

19. For filesystem actions, provide the user's symbolic
    path/name when possible. Do not invent absolute paths.

20. The executor is responsible for determining whether
    the requested action actually succeeds.

============================================================
USER REQUEST
============================================================

{user_input}
""".strip()


# ============================================================
# JSON EXTRACTION
# ============================================================

def _extract_json(text):
    """
    Safely extract one JSON object from model output.
    """

    if not isinstance(
        text,
        str
    ):
        return None

    text = text.strip()

    if not text:
        return None

    try:

        parsed = json.loads(text)

        if isinstance(
            parsed,
            dict
        ):
            return parsed

    except json.JSONDecodeError:

        pass

    cleaned = re.sub(
        r"```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    )

    cleaned = cleaned.replace(
        "```",
        ""
    ).strip()

    try:

        parsed = json.loads(cleaned)

        if isinstance(
            parsed,
            dict
        ):
            return parsed

    except json.JSONDecodeError:

        pass

    start_positions = [
        match.start()
        for match in re.finditer(
            r"\{",
            cleaned
        )
    ]

    for start in start_positions:

        depth = 0
        in_string = False
        escaped = False

        for index in range(
            start,
            len(cleaned)
        ):

            character = cleaned[index]

            if escaped:

                escaped = False
                continue

            if character == "\\" and in_string:

                escaped = True
                continue

            if character == '"':

                in_string = not in_string
                continue

            if in_string:
                continue

            if character == "{":

                depth += 1

            elif character == "}":

                depth -= 1

                if depth == 0:

                    candidate = cleaned[
                        start:index + 1
                    ]

                    try:

                        parsed = json.loads(
                            candidate
                        )

                        if isinstance(
                            parsed,
                            dict
                        ):

                            return parsed

                    except json.JSONDecodeError:

                        break

    return None


# ============================================================
# INTENT NORMALIZATION
# ============================================================

def _normalize_intent(intent):
    """
    Normalize a parsed intent into BENVIN's canonical
    structure.
    """

    if not isinstance(
        intent,
        dict
    ):
        return None

    intent_type = intent.get(
        "type"
    )

    if not isinstance(
        intent_type,
        str
    ):
        return None

    intent_type = (
        intent_type.strip().lower()
    )

    if intent_type == "conversation":

        response = intent.get(
            "response"
        )

        if not isinstance(
            response,
            str
        ):
            return None

        response = response.strip()

        if not response:
            return None

        return {
            "type": "conversation",
            "response": response
        }

    if intent_type == "action":

        action = intent.get(
            "action"
        )

        parameters = intent.get(
            "parameters"
        )

        if not isinstance(
            action,
            str
        ):
            return None

        action = action.strip()

        if not action:
            return None

        if not isinstance(
            parameters,
            dict
        ):
            return None

        return {
            "type": "action",
            "action": action,
            "parameters": parameters
        }

    return None


# ============================================================
# INTENT SHAPE VALIDATION
# ============================================================

def validate_intent_shape(intent):
    """
    Validate the basic structure of an intent.

    Deep action validation remains the responsibility of
    tools.validator.py.
    """

    if not isinstance(
        intent,
        dict
    ):
        return False

    intent_type = intent.get(
        "type"
    )

    if intent_type == "conversation":

        response = intent.get(
            "response"
        )

        return (
            isinstance(
                response,
                str
            )
            and bool(
                response.strip()
            )
        )

    if intent_type == "action":

        action = intent.get(
            "action"
        )

        parameters = intent.get(
            "parameters"
        )

        if not isinstance(
            action,
            str
        ):
            return False

        if not action.strip():
            return False

        if not isinstance(
            parameters,
            dict
        ):
            return False

        return True

    return False


# ============================================================
# VALIDATE ACTION AGAINST REGISTRY
# ============================================================

def _validate_registered_action(intent):
    """
    Ensure an action produced by the brain is actually
    registered and enabled.

    tools.validator.py remains the authoritative validator
    before execution.
    """

    if not isinstance(
        intent,
        dict
    ):
        return False

    if intent.get(
        "type"
    ) != "action":

        return True

    action = intent.get(
        "action"
    )

    tool = get_tool(
        action
    )

    if tool is None:
        return False

    if not tool.get(
        "enabled",
        False
    ):
        return False

    parameters = intent.get(
        "parameters"
    )

    if not isinstance(
        parameters,
        dict
    ):
        return False

    allowed_parameters = tool.get(
        "parameters",
        {}
    )

    if not isinstance(
        allowed_parameters,
        dict
    ):
        return False

    for parameter in parameters:

        if parameter not in allowed_parameters:

            return False

    for name, definition in allowed_parameters.items():

        if not isinstance(
            definition,
            dict
        ):
            continue

        if definition.get(
            "required",
            False
        ):

            if name not in parameters:

                return False

            value = parameters.get(
                name
            )

            if value is None:

                return False

            if isinstance(
                value,
                str
            ) and not value.strip():

                return False

    return True


# ============================================================
# ANALYZE INTENT
# ============================================================

def analyze_intent(user_input):
    """
    Analyze a user request.

    Processing order:

        1. Validate input.
        2. Try deterministic routing.
        3. Build the LLM intent prompt.
        4. Ask Qwen3.
        5. Parse JSON.
        6. Normalize intent.
        7. Validate intent shape.
        8. Validate action against registry.
        9. Return canonical intent.

    Deterministic routing is deliberately first.
    """

    if not isinstance(
        user_input,
        str
    ):

        return {
            "type": "error",
            "error": (
                "User input must be a string."
            )
        }

    user_input = user_input.strip()

    if not user_input:

        return {
            "type": "error",
            "error": (
                "User input cannot be empty."
            )
        }

    # ========================================================
    # DETERMINISTIC ROUTING
    # ========================================================

    deterministic_intent = (
        _build_deterministic_action_intent(
            user_input
        )
    )

    if deterministic_intent is not None:

        if not validate_intent_shape(
            deterministic_intent
        ):

            return {
                "type": "error",
                "error": (
                    "The deterministic router "
                    "produced an invalid intent."
                )
            }

        if not _validate_registered_action(
            deterministic_intent
        ):

            return {
                "type": "error",
                "error": (
                    "The requested action is not "
                    "valid or registered."
                )
            }

        return deterministic_intent

    # ========================================================
    # BUILD LLM PROMPT
    # ========================================================

    try:

        prompt = build_intent_prompt(
            user_input
        )

    except Exception as error:

        return {
            "type": "error",
            "error": (
                f"Could not build AI prompt: {error}"
            )
        }

    # ========================================================
    # ASK QWEN3
    # ========================================================

    try:

        raw_response = _ask_ollama(
            prompt,
            json_mode=True,
            think=False
        )

    except requests.Timeout:

        return {
            "type": "error",
            "error": (
                "Ollama took too long to process "
                "the request."
            )
        }

    except requests.ConnectionError:

        return {
            "type": "error",
            "error": (
                "Could not connect to Ollama. "
                "Make sure Ollama is running."
            )
        }

    except requests.RequestException as error:

        return {
            "type": "error",
            "error": (
                f"Ollama request failed: {error}"
            )
        }

    except Exception as error:

        return {
            "type": "error",
            "error": str(error)
        }

    # ========================================================
    # PARSE JSON
    # ========================================================

    intent = _extract_json(
        raw_response
    )

    if intent is None:

        return {
            "type": "error",
            "error": (
                "The AI returned invalid structured "
                "intent data."
            )
        }

    # ========================================================
    # NORMALIZE
    # ========================================================

    intent = _normalize_intent(
        intent
    )

    if intent is None:

        return {
            "type": "error",
            "error": (
                "The AI returned an unsupported "
                "intent structure."
            )
        }

    # ========================================================
    # VALIDATE SHAPE
    # ========================================================

    if not validate_intent_shape(
        intent
    ):

        return {
            "type": "error",
            "error": (
                "The AI returned an invalid intent."
            )
        }

    # ========================================================
    # VALIDATE REGISTRY
    # ========================================================

    if not _validate_registered_action(
        intent
    ):

        return {
            "type": "error",
            "error": (
                "The AI proposed an invalid or "
                "unsupported action."
            )
        }

    return intent


# ============================================================
# SYSTEM INFORMATION RESPONSE
# ============================================================

def _format_system_info_response(result):
    """
    Format system information deterministically.

    This is intentionally NOT delegated to Qwen3.

    The data comes directly from the trusted system tool.
    """

    if not isinstance(
        result,
        dict
    ):
        return None

    if not result.get(
        "success"
    ):
        return None

    data = result.get(
        "result"
    )

    if not isinstance(
        data,
        dict
    ):
        return None

    lines = [
        "Here is your computer information:"
    ]

    operating_system = data.get(
        "operating_system"
    )

    if isinstance(
        operating_system,
        dict
    ):

        name = operating_system.get("name")
        version = operating_system.get("version")
        release = operating_system.get("release")
        architecture = operating_system.get("architecture")

        if name:
            lines.append(
                f"- Operating System: {name}"
            )

        if version:
            lines.append(
                f"- OS Version: {version}"
            )

        if release:
            lines.append(
                f"- OS Release: {release}"
            )

        if architecture:
            lines.append(
                f"- Architecture: {architecture}"
            )

    processor = data.get(
        "processor"
    )

    if isinstance(
        processor,
        dict
    ):

        processor_name = processor.get(
            "processor"
        )

        machine = processor.get(
            "machine"
        )

        if processor_name:
            lines.append(
                f"- Processor: {processor_name}"
            )

        if machine:
            lines.append(
                f"- Machine: {machine}"
            )

    memory = data.get(
        "memory"
    )

    if isinstance(
        memory,
        dict
    ):

        total_gb = memory.get(
            "total_gb"
        )

        available_gb = memory.get(
            "available_gb"
        )

        used_gb = memory.get(
            "used_gb"
        )

        usage_percent = memory.get(
            "usage_percent"
        )

        if total_gb is not None:
            lines.append(
                f"- RAM Total: {total_gb} GB"
            )

        if used_gb is not None:
            lines.append(
                f"- RAM Used: {used_gb} GB"
            )

        if available_gb is not None:
            lines.append(
                f"- RAM Available: {available_gb} GB"
            )

        if usage_percent is not None:
            lines.append(
                f"- RAM Usage: {usage_percent}%"
            )

    disk = data.get(
        "disk"
    )

    if isinstance(
        disk,
        dict
    ):

        drive = disk.get(
            "drive"
        )

        total_gb = disk.get(
            "total_gb"
        )

        used_gb = disk.get(
            "used_gb"
        )

        free_gb = disk.get(
            "free_gb"
        )

        usage_percent = disk.get(
            "usage_percent"
        )

        if drive:
            lines.append(
                f"- Disk Drive: {drive}"
            )

        if total_gb is not None:
            lines.append(
                f"- Disk Total: {total_gb} GB"
            )

        if used_gb is not None:
            lines.append(
                f"- Disk Used: {used_gb} GB"
            )

        if free_gb is not None:
            lines.append(
                f"- Disk Free: {free_gb} GB"
            )

        if usage_percent is not None:
            lines.append(
                f"- Disk Usage: {usage_percent}%"
            )

    python_info = data.get(
        "python"
    )

    if isinstance(
        python_info,
        dict
    ):

        version = python_info.get(
            "version"
        )

        implementation = python_info.get(
            "implementation"
        )

        if version:
            lines.append(
                f"- Python: {version}"
            )

        if implementation:
            lines.append(
                f"- Python Implementation: {implementation}"
            )

    computer_name = data.get(
        "computer_name"
    )

    username = data.get(
        "username"
    )

    uptime = data.get(
        "uptime"
    )

    benvin_directory = data.get(
        "benvin_directory"
    )

    if computer_name:
        lines.append(
            f"- Computer Name: {computer_name}"
        )

    if username:
        lines.append(
            f"- User: {username}"
        )

    if uptime:
        lines.append(
            f"- Uptime: {uptime}"
        )

    if benvin_directory:
        lines.append(
            f"- BENVIN Directory: {benvin_directory}"
        )

    if len(lines) == 1:

        return (
            "The system information tool returned "
            "no readable information."
        )

    return "\n".join(lines)


# ============================================================
# SYSTEM HEALTH RESPONSE
# ============================================================

def _format_system_health_response(result):
    """
    Format the actual system_health tool result
    deterministically.

    This function does not calculate health itself.

    It only reports the values supplied by the
    trusted system_health tool.
    """

    if not isinstance(
        result,
        dict
    ):
        return None

    if not result.get(
        "success"
    ):
        return None

    data = result.get(
        "result"
    )

    if not isinstance(
        data,
        dict
    ):
        return None

    lines = [
        "Here is the current computer health assessment:"
    ]

    overall_status = data.get(
        "overall_status"
    )

    assessment_completeness = data.get(
        "assessment_completeness"
    )

    priority = data.get(
        "priority"
    )

    if overall_status:
        lines.append(
            f"- Overall Status: {overall_status}"
        )

    if assessment_completeness:
        lines.append(
            f"- Assessment: {assessment_completeness}"
        )

    if priority:
        lines.append(
            f"- Priority: {priority}"
        )

    memory = data.get(
        "memory"
    )

    if isinstance(
        memory,
        dict
    ):

        status = memory.get(
            "status"
        )

        usage_percent = memory.get(
            "usage_percent"
        )

        available_gb = memory.get(
            "available_gb"
        )

        used_gb = memory.get(
            "used_gb"
        )

        message = memory.get(
            "message"
        )

        memory_line = "- Memory"

        if status:
            memory_line += f": {status}"

        if usage_percent is not None:
            memory_line += f" ({usage_percent}% used)"

        lines.append(
            memory_line
        )

        if used_gb is not None:
            lines.append(
                f"  - Used: {used_gb} GB"
            )

        if available_gb is not None:
            lines.append(
                f"  - Available: {available_gb} GB"
            )

        if message:
            lines.append(
                f"  - {message}"
            )

    disk = data.get(
        "disk"
    )

    if isinstance(
        disk,
        dict
    ):

        status = disk.get(
            "status"
        )

        drive = disk.get(
            "drive"
        )

        usage_percent = disk.get(
            "usage_percent"
        )

        free_gb = disk.get(
            "free_gb"
        )

        message = disk.get(
            "message"
        )

        disk_line = "- Disk"

        if drive:
            disk_line += f" ({drive})"

        if status:
            disk_line += f": {status}"

        if usage_percent is not None:
            disk_line += f" ({usage_percent}% used)"

        lines.append(
            disk_line
        )

        if free_gb is not None:
            lines.append(
                f"  - Free: {free_gb} GB"
            )

        if message:
            lines.append(
                f"  - {message}"
            )

    recommendations = data.get(
        "recommendations"
    )

    if isinstance(
        recommendations,
        list
    ) and recommendations:

        lines.append("")
        lines.append("Recommendations:")

        for recommendation in recommendations:

            if isinstance(
                recommendation,
                str
            ) and recommendation.strip():

                lines.append(
                    f"- {recommendation.strip()}"
                )

    if len(lines) == 1:

        return (
            "The system health tool returned "
            "no readable health information."
        )

    return "\n".join(lines)


# ============================================================
# NORMAL CONVERSATION API
# ============================================================

def ask_benvin(message):
    """
    Public conversational API.

    This function analyzes the request but does not
    execute computer actions.
    """

    intent = analyze_intent(
        message
    )

    if intent.get(
        "type"
    ) == "conversation":

        return intent.get(
            "response",
            ""
        )

    if intent.get(
        "type"
    ) == "error":

        return (
            "I couldn't process that request "
            "through my local AI engine."
        )

    if intent.get(
        "type"
    ) == "action":

        return (
            "ACTION_INTENT:"
            + json.dumps(
                intent,
                ensure_ascii=False
            )
        )

    return (
        "I couldn't understand that request."
    )


# ============================================================
# ACTION RESULT RESPONSE
# ============================================================

def respond_to_action_result(
    action,
    parameters,
    result
):
    """
    Convert an actual tool execution result into
    natural language.

    This function does NOT execute another action.

    Some results are formatted deterministically because
    accuracy is more important than LLM wording.
    """

    # ========================================================
    # SYSTEM INFORMATION
    # ========================================================

    if action == "system_info":

        formatted = (
            _format_system_info_response(
                result
            )
        )

        if formatted:
            return formatted

    # ========================================================
    # SYSTEM HEALTH
    # ========================================================

    if action == "system_health":

        formatted = (
            _format_system_health_response(
                result
            )
        )

        if formatted:
            return formatted

    try:

        serialized_result = json.dumps(
            result,
            ensure_ascii=False,
            default=str
        )

    except Exception:

        serialized_result = str(
            result
        )

    try:

        serialized_parameters = json.dumps(
            parameters,
            ensure_ascii=False,
            default=str
        )

    except Exception:

        serialized_parameters = str(
            parameters
        )

    prompt = f"""
You are BENVIN, a local personal AI assistant.

A computer action has ALREADY been processed by
BENVIN's secure execution system.

Your job is ONLY to explain the actual result
to the user.

Do NOT perform another action.

Do NOT invent information.

Do NOT claim an action succeeded unless the
execution result confirms success.

Do NOT claim an action failed unless the
execution result indicates failure.

Keep the response short, natural, and useful.

============================================================
ACTION
============================================================

{action}

============================================================
PARAMETERS
============================================================

{serialized_parameters}

============================================================
EXECUTION RESULT
============================================================

{serialized_result}

============================================================
RESPONSE RULES
============================================================

If success is true:

    Tell the user what was completed.

If success is false:

    Explain that the action failed.

    Give the reason when available.

For filesystem results:

    Report the actual files, folders, path, or
    information supplied by the execution result.

Do not invent files.

Do not invent paths.

Do not mention internal Python functions.

Do not mention registries.

Do not mention validators.

Do not mention permissions.

Do not mention JSON.

Respond with ONLY the natural-language response.
""".strip()

    try:

        response = _ask_ollama(
            prompt,
            json_mode=False,
            think=False
        )

        if response:

            return response

    except Exception:

        pass

    readable_action = (
        str(action).replace(
            "_",
            " "
        )
    )

    if isinstance(
        result,
        dict
    ) and result.get(
        "success"
    ):

        return (
            f"I successfully completed "
            f"{readable_action}."
        )

    error = None

    if isinstance(
        result,
        dict
    ):

        error = result.get(
            "error"
        )

    if error:

        return (
            f"I couldn't complete "
            f"{readable_action}: {error}"
        )

    return (
        f"I couldn't complete "
        f"{readable_action}."
    )


# ============================================================
# HEALTH CHECK
# ============================================================

def check_brain():
    """
    Check whether Ollama is reachable and whether
    the configured model is available.
    """

    try:

        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict
        ):
            raise ValueError(
                "Ollama returned invalid model data."
            )

        models = []

        for model in data.get(
            "models",
            []
        ):

            if not isinstance(
                model,
                dict
            ):
                continue

            name = model.get(
                "name"
            )

            if name:
                models.append(
                    name
                )

        return {
            "success": True,
            "ollama": True,
            "model": MODEL,
            "model_available": MODEL in models,
            "available_models": models
        }

    except requests.Timeout:

        return {
            "success": False,
            "ollama": False,
            "model": MODEL,
            "error": "Ollama health check timed out."
        }

    except requests.ConnectionError:

        return {
            "success": False,
            "ollama": False,
            "model": MODEL,
            "error": "Could not connect to Ollama."
        }

    except Exception as error:

        return {
            "success": False,
            "ollama": False,
            "model": MODEL,
            "error": str(error)
        }


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("BENVIN BRAIN TEST")
    print("=" * 60)

    print()

    health = check_brain()

    print("Ollama health:")

    print(
        json.dumps(
            health,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print("Registered enabled tools:")

    print(
        build_tool_context()
    )

    print()

    print("System information routing test:")

    test_intent = analyze_intent(
        "what is my computer information?"
    )

    print(
        json.dumps(
            test_intent,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print("System health routing test:")

    health_intent = analyze_intent(
        "check my computer health"
    )

    print(
        json.dumps(
            health_intent,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print("Brain module loaded successfully.")