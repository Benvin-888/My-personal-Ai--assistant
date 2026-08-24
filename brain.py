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
    The brain NEVER executes tools directly.

    Qwen3 can propose an action.
    BENVIN's validator, permission engine, and executor
    decide whether that action is actually performed.

LONG-TERM MEMORY:
    memory.py
        Stores persistent user knowledge.

SHORT-TERM CONTEXT:
    context.py
        Stores current conversation and task state.
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

REQUEST_TIMEOUT = 120


# ============================================================
# OLLAMA COMMUNICATION
# ============================================================

def _ask_ollama(prompt):
    """
    Send a prompt to the local Ollama server.

    Returns:
        str: Model response.
    """

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    return data.get(
        "response",
        ""
    ).strip()


# ============================================================
# TOOL CONTEXT
# ============================================================

def build_tool_context():
    """
    Build the tool description supplied to Qwen3.

    The registry is the single source of truth.

    Adding a registered tool automatically makes it
    available to the brain's intent system.
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
    Retrieve relevant long-term memories for the
    current request.

    This function only retrieves persistent memory.

    Short-term conversation state is handled separately
    by context.py.
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
    Build the short-term context supplied to Qwen3.

    This includes:

        - current session
        - recent conversation
        - current task
        - last action
        - last tool result
        - active application
        - temporary variables

    This information belongs to context.py, not memory.py.
    """

    try:

        snapshot = get_context_snapshot()

    except Exception:

        return "No short-term context available."

    # --------------------------------------------------------
    # Remove information that does not need to be shown
    # --------------------------------------------------------

    context = {
        "session_id": snapshot.get(
            "session_id"
        ),
        "conversation": snapshot.get(
            "conversation",
            []
        ),
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
# INTENT PROMPT
# ============================================================

def build_intent_prompt(user_input):
    """
    Build the structured-intent prompt.

    Qwen3 has two possible outputs:

        conversation
        action

    The model does NOT execute anything.
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

Your task is to understand the user's request.

You MUST return exactly ONE JSON object.

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

Format:

{{
    "type": "conversation",
    "response": "your answer"
}}

============================================================
RESPONSE TYPE 2 — ACTION
============================================================

Use this when the user wants BENVIN to perform
a registered computer action.

Format:

{{
    "type": "action",
    "action": "registered_action_name",
    "parameters": {{}}
}}

============================================================
AVAILABLE TOOLS
============================================================

{tools}

============================================================
RELEVANT LONG-TERM USER MEMORY
============================================================

{memory_context}

============================================================
CURRENT SHORT-TERM CONTEXT
============================================================

{short_term_context}

============================================================
HOW TO USE CONTEXT
============================================================

The CURRENT SHORT-TERM CONTEXT describes what has
happened during the current session.

Use it to understand references such as:

- "it"
- "that"
- "the file"
- "the application"
- "again"
- "what we just did"
- "continue"
- "close it"
- "open it"
- "what happened"

Long-term memory describes persistent user knowledge.

Do NOT treat short-term context as permanent user memory.

Do NOT invent information that is not present in the
provided context.

============================================================
STRICT RULES
============================================================

1. Return ONLY valid JSON.

2. Do NOT use Markdown.

3. Do NOT put the JSON inside ``` blocks.

4. Never invent a tool.

5. Only use actions listed in AVAILABLE TOOLS.

6. Never invent parameters.

7. Only use parameters defined by the selected tool.

8. If the user asks a normal question, use:
   "type": "conversation"

9. If the user requests a registered computer action,
   use:
   "type": "action"

10. Never claim that an action has already happened.

11. Do not execute tools.

12. Do not invent tool results.

13. Use relevant long-term memory when answering
    questions about the user.

14. Use short-term context when the request refers
    to the current conversation or task.

15. Keep conversation responses concise and useful.

16. If you are unsure whether an action is required,
    prefer conversation instead of inventing an action.

17. The existence of a tool does NOT mean the action
    should automatically be performed.

18. Never output an action that is not explicitly
    supported by AVAILABLE TOOLS.

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
    Safely extract a JSON object from model output.

    Qwen3 may occasionally return surrounding text,
    Markdown fences, or other formatting.
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
    # Attempt 1 — Direct JSON
    # --------------------------------------------------------

    try:

        return json.loads(
            text
        )

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # Attempt 2 — Remove Markdown fences
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

        return json.loads(
            cleaned
        )

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # Attempt 3 — Extract first JSON object
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

            return json.loads(
                candidate
            )

        except json.JSONDecodeError:
            pass

    return None


# ============================================================
# INTENT SHAPE VALIDATION
# ============================================================

def validate_intent_shape(intent):
    """
    Validate the basic structure of an intent.

    This does NOT replace tools.validator.py.

    tools.validator.py performs deeper validation
    of an actual action and its parameters.
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

        return isinstance(
            response,
            str
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
# ANALYZE INTENT
# ============================================================

def analyze_intent(user_input):
    """
    Analyze a user request with Qwen3.

    Returns one of:

        {
            "type": "conversation",
            "response": "..."
        }

    OR:

        {
            "type": "action",
            "action": "...",
            "parameters": {...}
        }

    OR:

        {
            "type": "error",
            "error": "..."
        }
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

    # --------------------------------------------------------
    # Build prompt
    # --------------------------------------------------------

    prompt = build_intent_prompt(
        user_input
    )

    # --------------------------------------------------------
    # Ask Qwen3
    # --------------------------------------------------------

    try:

        raw_response = _ask_ollama(
            prompt
        )

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

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    intent = _extract_json(
        raw_response
    )

    # --------------------------------------------------------
    # JSON failure
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Validate structure
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Return structured intent
    # --------------------------------------------------------

    return intent


# ============================================================
# NORMAL CONVERSATION
# ============================================================

def ask_benvin(message):
    """
    Public conversational API.

    If the request is conversational, return the answer.

    If the request is an action, return a structured
    ACTION_INTENT marker for compatibility with older
    code paths.
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
    Convert a completed tool result into a natural
    language response.

    IMPORTANT:

    This function does NOT execute another tool.

    It only explains what already happened.
    """

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

Your job is ONLY to explain the result to the user.

Do NOT perform another action.

Do NOT suggest that you performed something
that the execution result does not confirm.

Do NOT invent information.

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
    Clearly tell the user what was completed.

If success is false:
    Clearly explain that the action failed
    and give the reason when available.

Do not mention internal Python functions,
registries, validators, permissions, or JSON.

Respond with ONLY the natural-language response.
""".strip()

    try:

        response = _ask_ollama(
            prompt
        )

        if response:

            return response

    except Exception:
        pass

    # --------------------------------------------------------
    # Safe deterministic fallback
    # --------------------------------------------------------

    readable_action = action.replace(
        "_",
        " "
    )

    if result.get(
        "success"
    ):

        return (
            f"I successfully completed "
            f"{readable_action}."
        )

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

    Returns a structured result instead of raising
    an exception.
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