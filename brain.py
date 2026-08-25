"""
BENVIN Brain

Responsibilities:
    1. Communicate with Ollama / Qwen3.
    2. Retrieve relevant BENVIN memories.
    3. Retrieve current short-term context.
    4. Build tool context from the central registry.
    5. Analyze natural-language requests.
    6. Produce structured conversation or action intents.
    7. Safely parse model output.
    8. Convert completed tool results into natural language.

IMPORTANT:

    The brain NEVER executes tools.

    The brain may:
        - understand a request
        - select a registered action
        - build action parameters

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

    Args:
        prompt:
            Prompt sent to Qwen3.

        json_mode:
            Ask Ollama for JSON-formatted output.

        think:
            Enable or disable Qwen3 thinking.

    Returns:
        str:
            Model response.
    """

    if not isinstance(
        prompt,
        str
    ):
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

    if not isinstance(
        data,
        dict
    ):
        raise ValueError(
            "Ollama returned an invalid response."
        )

    result = data.get(
        "response",
        ""
    )

    if not isinstance(
        result,
        str
    ):
        return ""

    return result.strip()


# ============================================================
# TOOL CONTEXT
# ============================================================

def build_tool_context():
    """
    Build the tool description supplied to Qwen3.

    The registry remains the single source of truth.
    """

    tools = []

    for action in list_tools():

        definition = get_tool(
            action
        )

        if definition is None:
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

    return "\n".join(
        context
    )


# ============================================================
# SHORT-TERM CONTEXT
# ============================================================

def build_context_context():
    """
    Build short-term session context.

    Only recent conversation is supplied to the model.
    """

    try:

        snapshot = get_context_snapshot()

    except Exception:

        return (
            "No short-term context available."
        )

    if not isinstance(
        snapshot,
        dict
    ):

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
# DETERMINISTIC ACTION ROUTER
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


def _extract_filename(text):
    """
    Extract a likely filename from a filesystem request.

    Examples:

        Find main.py
        Search for test.txt
        Find config.json

    Returns:
        filename or None
    """

    if not isinstance(
        text,
        str
    ):
        return None

    # --------------------------------------------------------
    # Common filename patterns
    # --------------------------------------------------------

    pattern = re.compile(
        r"""
        (?:
            file\s+
        )?
        ["'`]?   
        (
            [A-Za-z0-9_\-\.]+
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


def _extract_location_hint(text):
    """
    Extract a simple human-readable location hint.

    This does NOT access the filesystem.

    It only identifies words supplied by the user so that
    the controlled filesystem layer can resolve them.

    Examples:

        "in my Benvin folder"
            -> Benvin

        "on my Desktop"
            -> Desktop
    """

    if not isinstance(
        text,
        str
    ):
        return None

    patterns = [

        r"\bin\s+(?:my\s+)?([A-Za-z0-9_\- ]+?)\s+folder\b",

        r"\bin\s+(?:the\s+)?([A-Za-z0-9_\- ]+?)\s+folder\b",

        r"\bon\s+(?:my\s+)?([A-Za-z0-9_\- ]+?)\b",

        r"\bin\s+(?:my\s+)?([A-Za-z0-9_\- ]+?)\b",
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

        # Remove common trailing words.
        location = re.sub(
            r"\s+(?:files?|folders?)$",
            "",
            location,
            flags=re.IGNORECASE
        ).strip()

        if location:
            return location

    return None


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

    Returns:

        dict
            Structured action intent.

        None
            No deterministic route detected.
    """

    text = _normalize_text(
        user_input
    )

    if not text:
        return None

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
            parameters[
                "search_root"
            ] = location

        return {
            "type": "action",
            "action": "find_file",
            "parameters": parameters,
            "routing": "deterministic"
        }

    # ========================================================
    # LIST DIRECTORY
    # ========================================================

    if _is_directory_listing_request(
        text
    ):

        location = _extract_location_hint(
            text
        )

        # ----------------------------------------------------
        # Common Windows location aliases.
        #
        # These remain symbolic. The filesystem tool is
        # responsible for resolving/allowing the actual path.
        # ----------------------------------------------------

        if location:

            path = location

        elif "desktop" in text:

            path = "Desktop"

        else:

            path = "."

        return {
            "type": "action",
            "action": "list_directory",
            "parameters": {
                "path": path
            },
            "routing": "deterministic"
        }

    # ========================================================
    # PATH EXISTS
    # ========================================================

    if _is_path_exists_request(
        text
    ):

        filename = _extract_filename(
            text
        )

        location = _extract_location_hint(
            text
        )

        if filename and location:

            path = (
                f"{location}\\{filename}"
            )

        elif filename:

            path = filename

        elif location:

            path = location

        else:

            return None

        return {
            "type": "action",
            "action": "path_exists",
            "parameters": {
                "path": path
            },
            "routing": "deterministic"
        }

    # ========================================================
    # FILE INFORMATION
    # ========================================================

    if _is_file_info_request(
        text
    ):

        filename = _extract_filename(
            text
        )

        location = _extract_location_hint(
            text
        )

        if filename and location:

            path = (
                f"{location}\\{filename}"
            )

        elif filename:

            path = filename

        elif location:

            path = location

        else:

            return None

        return {
            "type": "action",
            "action": "get_file_info",
            "parameters": {
                "path": path
            },
            "routing": "deterministic"
        }

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
RESPONSE TYPE 1 — CONVERSATION
============================================================

Use this when the user wants:

- an explanation
- an answer to a question
- general conversation
- programming help
- knowledge
- advice
- information that does not require a registered tool

Example:

User:
What is Python?

Return:

{{
    "type": "conversation",
    "response": "Python is a high-level programming language..."
}}

============================================================
RESPONSE TYPE 2 — ACTION
============================================================

Use this when the user explicitly asks BENVIN
to perform a registered computer action.

Example:

User:
Find main.py in my Benvin folder.

Return:

{{
    "type": "action",
    "action": "find_file",
    "parameters": {{
        "filename": "main.py",
        "search_root": "Benvin"
    }}
}}

Example:

User:
List desktop files.

Return:

{{
    "type": "action",
    "action": "list_directory",
    "parameters": {{
        "path": "Desktop"
    }}
}}

============================================================
AVAILABLE TOOLS
============================================================

{tools}

============================================================
IMPORTANT ACTION MAPPINGS
============================================================

Use these mappings when the user's request matches them.

"find a file"
        -> find_file

"search for a file"
        -> find_file

"locate a file"
        -> find_file

"find main.py"
        -> find_file

"find test.txt"
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

"what is Python"
        -> conversation

============================================================
CRITICAL EXECUTION RULE
============================================================

The assistant's previous conversational responses are
NOT evidence that a computer action happened.

For example, if previous context contains:

"The file was not found."

that does NOT mean a real filesystem search happened.

Only an actual execution result supplied by BENVIN's
execution system is evidence that an action happened.

If the current user asks to find the file again,
you MUST create a new action intent.

============================================================
RELEVANT LONG-TERM USER MEMORY
============================================================

{memory_context}

============================================================
CURRENT SHORT-TERM CONTEXT
============================================================

{short_term_context}

============================================================
CONTEXT RULES
============================================================

Use short-term context for references such as:

- "it"
- "that"
- "the file"
- "the application"
- "again"
- "continue"
- "close it"
- "open it"
- "what happened"

Do NOT treat previous assistant statements as tool results.

Do NOT invent filesystem results.

Do NOT claim that a file exists.

Do NOT claim that a file does not exist.

Do NOT claim that an application was opened.

Do NOT claim that an action was performed.

Only the execution system can establish those facts.

============================================================
STRICT RULES
============================================================

1. Return ONLY ONE valid JSON object.

2. Do NOT use Markdown.

3. Do NOT use code fences.

4. Never invent a tool.

5. Only use actions listed in AVAILABLE TOOLS.

6. Never invent parameters.

7. Only use parameters defined by the selected tool.

8. Normal questions use "conversation".

9. Computer requests use "action".

10. Never execute tools.

11. Never invent tool results.

12. Never claim an action already happened.

13. Use relevant long-term memory when appropriate.

14. Use short-term context when appropriate.

15. Keep conversational answers concise.

16. If the user clearly requests a computer action,
    prefer the registered action.

17. If a request is ambiguous and does not clearly
    require an action, use conversation.

18. For filesystem requests, do NOT answer with a
    claimed filesystem result.

19. The filesystem tool must determine whether files
    actually exist.

20. The executor must determine whether an action
    actually happens.

21. For actions, "parameters" must be a JSON object.

22. For conversations, "response" must be a string.

23. Do not include unnecessary fields.

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

    # --------------------------------------------------------
    # Direct JSON
    # --------------------------------------------------------

    try:

        parsed = json.loads(
            text
        )

        if isinstance(
            parsed,
            dict
        ):
            return parsed

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # Remove Markdown fences
    # --------------------------------------------------------

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

        parsed = json.loads(
            cleaned
        )

        if isinstance(
            parsed,
            dict
        ):
            return parsed

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # Extract JSON object
    # --------------------------------------------------------

    start = cleaned.find(
        "{"
    )

    end = cleaned.rfind(
        "}"
    )

    if (
        start != -1
        and end != -1
        and end > start
    ):

        candidate = cleaned[
            start:end + 1
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
            pass

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

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Action
    # --------------------------------------------------------

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
    registered.

    This is an additional brain-side safety check.

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

    # --------------------------------------------------------
    # Reject unknown parameters.
    # --------------------------------------------------------

    for parameter in parameters:

        if parameter not in allowed_parameters:

            return False

    # --------------------------------------------------------
    # Check required parameters.
    # --------------------------------------------------------

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

    Deterministic routing handles obvious computer actions.

    Qwen3 handles general natural-language intent analysis.

    Returns:

        conversation intent

        action intent

        error intent
    """

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

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
    # STEP 1 — DETERMINISTIC ROUTING
    # ========================================================

    deterministic_intent = (
        _build_deterministic_action_intent(
            user_input
        )
    )

    if deterministic_intent is not None:

        # ----------------------------------------------------
        # Remove internal routing metadata before returning.
        #
        # The executor and other layers only need the
        # standard intent fields.
        # ----------------------------------------------------

        deterministic_intent.pop(
            "routing",
            None
        )

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
    # STEP 2 — BUILD LLM PROMPT
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
    # STEP 3 — ASK QWEN3
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

    except requests.ConnectionError as error:

        return {
            "type": "error",
            "error": (
                f"Could not connect to Ollama: {error}"
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
    # STEP 4 — PARSE JSON
    # ========================================================

    intent = _extract_json(
        raw_response
    )

    if intent is None:

        if raw_response:

            return {
                "type": "conversation",
                "response": raw_response,
                "fallback": True
            }

        return {
            "type": "error",
            "error": (
                "The AI returned an empty response."
            )
        }

    # ========================================================
    # STEP 5 — VALIDATE INTENT SHAPE
    # ========================================================

    if not validate_intent_shape(
        intent
    ):

        if raw_response:

            return {
                "type": "conversation",
                "response": raw_response,
                "fallback": True
            }

        return {
            "type": "error",
            "error": (
                "The AI returned an invalid intent."
            )
        }

    # ========================================================
    # STEP 6 — VALIDATE REGISTERED ACTION
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

    # ========================================================
    # STEP 7 — RETURN INTENT
    # ========================================================

    return intent


# ============================================================
# NORMAL CONVERSATION API
# ============================================================

def ask_benvin(message):
    """
    Public conversational API.
    """

    intent = analyze_intent(
        message
    )

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    if intent.get(
        "type"
    ) == "conversation":

        return intent.get(
            "response",
            ""
        )

    # --------------------------------------------------------
    # Error
    # --------------------------------------------------------

    if intent.get(
        "type"
    ) == "error":

        return (
            "I couldn't connect to my local "
            "AI engine right now."
        )

    # --------------------------------------------------------
    # Action
    # --------------------------------------------------------

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

    IMPORTANT:

    This function only explains the supplied result.

    It does not execute another action.
    """

    # --------------------------------------------------------
    # Serialize result
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Serialize parameters
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Deterministic fallback
    # --------------------------------------------------------

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
    Check whether Ollama is reachable.
    """

    try:

        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        models = [
            model.get("name")
            for model in data.get(
                "models",
                []
            )
        ]

        return {
            "success": True,
            "ollama": True,
            "model": MODEL,
            "available_models": models
        }

    except Exception as error:

        return {
            "success": False,
            "ollama": False,
            "model": MODEL,
            "error": str(error)
        }