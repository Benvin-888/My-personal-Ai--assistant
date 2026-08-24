"""
BENVIN Main Controller

Main responsibilities:

    User input
        ↓
    Short-term context
        ↓
    Brain / Intent
        ↓
    Conversation OR Action
        ↓
    Validation
        ↓
    Permission
        ↓
    User Confirmation (when required)
        ↓
    Execution
        ↓
    Context update
        ↓
    Response


IMPORTANT:

    memory.py
        Long-term persistent user knowledge.

    context.py
        Short-term session and task state.

    brain.py
        Understands requests but NEVER executes tools.

    validator.py
        Validates proposed actions.

    permissions.py
        Determines whether actions are allowed.

    executor.py
        Executes approved actions.

The LLM never directly executes tools.
"""


from brain import (
    analyze_intent,
    respond_to_action_result
)

from context import (
    add_message,
    set_last_action,
    set_last_tool_result,
    get_current_task,
    start_task,
    complete_task,
    update_task
)

from tools.validator import (
    validate_action
)

from tools.executor import (
    execute_action
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def print_separator():
    """
    Print a visual separator.
    """

    print()
    print("-" * 60)
    print()


def print_tool_result(result):
    """
    Display a tool execution result cleanly.
    """

    print()

    if result.get("success"):

        print(
            f"BENVIN: Action completed → "
            f"{result.get('action')}"
        )

    else:

        print(
            f"BENVIN: Action failed → "
            f"{result.get('action')}"
        )

        if result.get("error"):

            print(
                f"Reason: {result['error']}"
            )

    print()


# ============================================================
# STORE ASSISTANT RESPONSE
# ============================================================

def store_assistant_response(response):
    """
    Store a BENVIN response in short-term context.
    """

    if not response:
        return

    try:

        add_message(
            "assistant",
            response
        )

    except Exception as error:

        print(
            f"[Context warning] "
            f"Could not store assistant response: "
            f"{error}"
        )


# ============================================================
# HANDLE CONVERSATION
# ============================================================

def handle_conversation(intent):
    """
    Display and store a normal conversational response.
    """

    response = intent.get(
        "response",
        ""
    )

    if response:

        print(
            f"BENVIN: {response}"
        )

        store_assistant_response(
            response
        )

    else:

        fallback = (
            "I don't have a response "
            "for that yet."
        )

        print(
            f"BENVIN: {fallback}"
        )

        store_assistant_response(
            fallback
        )


# ============================================================
# START ACTION TASK
# ============================================================

def prepare_action_task(
    action,
    parameters
):
    """
    Create or update short-term task state
    before executing an action.

    A task represents the current operation BENVIN
    is attempting to perform.
    """

    current_task = get_current_task()

    # --------------------------------------------------------
    # If no task is active, create one.
    # --------------------------------------------------------

    if not isinstance(
        current_task,
        dict
    ) or not current_task.get(
        "active",
        False
    ):

        description = (
            f"Execute action '{action}'"
        )

        try:

            return start_task(
                description
            )

        except Exception:

            return None

    # --------------------------------------------------------
    # Continue existing task.
    # --------------------------------------------------------

    try:

        return update_task(
            status="running"
        )

    except Exception:

        return current_task


# ============================================================
# CONFIRMATION INPUT
# ============================================================

def request_user_confirmation(
    action,
    parameters
):
    """
    Ask the user to explicitly confirm an action.

    IMPORTANT:

        The LLM does not answer this question.

        The actual user must provide confirmation.

    Returns:

        True
            User confirmed.

        False
            User rejected the action.
    """

    print()

    print(
        "BENVIN: This action requires your "
        "confirmation before I can continue."
    )

    print(
        f"Action: {action}"
    )

    if parameters:

        print(
            f"Parameters: {parameters}"
        )

    print()

    while True:

        try:

            answer = input(
                "Confirm? (yes/no): "
            ).strip().lower()

        except (
            KeyboardInterrupt,
            EOFError
        ):

            print()

            return False

        if answer in {
            "yes",
            "y",
            "confirm",
            "confirmed"
        }:

            return True

        if answer in {
            "no",
            "n",
            "cancel",
            "cancelled"
        }:

            return False

        print(
            "BENVIN: Please answer yes or no."
        )


# ============================================================
# HANDLE CONFIRMATION DENIAL
# ============================================================

def handle_confirmation_denied(
    action
):
    """
    Handle a user declining a confirmation request.
    """

    message = (
        f"I did not perform '{action}' "
        "because you did not confirm it."
    )

    print(
        f"BENVIN: {message}"
    )

    store_assistant_response(
        message
    )

    try:

        update_task(
            status="cancelled"
        )

    except Exception as error:

        print(
            f"[Context warning] "
            f"Could not update cancelled task: "
            f"{error}"
        )


# ============================================================
# HANDLE ACTION
# ============================================================

def handle_action(intent):
    """
    Process a structured action.

    Action flow:

        intent
          ↓
        validator
          ↓
        executor
          ↓
        permission
          ↓
        confirmation if required
          ↓
        executor
          ↓
        context update
          ↓
        brain response
    """

    action = intent.get(
        "action"
    )

    parameters = intent.get(
        "parameters",
        {}
    )

    # --------------------------------------------------------
    # STEP 1 — VALIDATE
    # --------------------------------------------------------

    validation = validate_action(
        action,
        parameters
    )

    if not validation["valid"]:

        message = (
            "I couldn't safely perform "
            "that action."
        )

        print(
            f"BENVIN: {message}"
        )

        print(
            f"Reason: {validation['error']}"
        )

        store_assistant_response(
            f"{message} "
            f"Reason: {validation['error']}"
        )

        return

    # --------------------------------------------------------
    # STEP 2 — RECORD CURRENT TASK
    # --------------------------------------------------------

    prepare_action_task(
        action,
        parameters
    )

    # --------------------------------------------------------
    # STEP 3 — RECORD LAST ACTION
    # --------------------------------------------------------

    try:

        set_last_action(
            action,
            parameters
        )

    except Exception as error:

        print(
            f"[Context warning] "
            f"Could not store action: "
            f"{error}"
        )

    # --------------------------------------------------------
    # STEP 4 — FIRST EXECUTION ATTEMPT
    #
    # The executor will perform validation and permission
    # checking again.
    #
    # This is intentional.
    #
    # The executor remains a security boundary even if
    # another part of the program calls it directly.
    # --------------------------------------------------------

    result = execute_action(
        action,
        parameters,
        user_confirmed=False
    )

    # --------------------------------------------------------
    # STEP 5 — CHECK FOR REQUIRED CONFIRMATION
    # --------------------------------------------------------

    if result.get(
        "status"
    ) == "confirmation_required":

        try:

            update_task(
                status="waiting_confirmation"
            )

        except Exception as error:

            print(
                f"[Context warning] "
                f"Could not update task state: "
                f"{error}"
            )

        confirmed = request_user_confirmation(
            action,
            parameters
        )

        # ----------------------------------------------------
        # User rejected
        # ----------------------------------------------------

        if not confirmed:

            handle_confirmation_denied(
                action
            )

            return

        # ----------------------------------------------------
        # User confirmed
        # ----------------------------------------------------

        try:

            update_task(
                status="running"
            )

        except Exception as error:

            print(
                f"[Context warning] "
                f"Could not resume task: "
                f"{error}"
            )

        result = execute_action(
            action,
            parameters,
            user_confirmed=True
        )

    # --------------------------------------------------------
    # STEP 6 — STORE FINAL TOOL RESULT
    # --------------------------------------------------------

    try:

        set_last_tool_result(
            result
        )

    except Exception as error:

        print(
            f"[Context warning] "
            f"Could not store tool result: "
            f"{error}"
        )

    # --------------------------------------------------------
    # STEP 7 — UPDATE TASK STATE
    # --------------------------------------------------------

    if result.get(
        "success"
    ):

        try:

            complete_task()

        except Exception as error:

            print(
                f"[Context warning] "
                f"Could not complete task: "
                f"{error}"
            )

    else:

        try:

            update_task(
                status="failed"
            )

        except Exception as error:

            print(
                f"[Context warning] "
                f"Could not update failed task: "
                f"{error}"
            )

    # --------------------------------------------------------
    # STEP 8 — DISPLAY BASIC RESULT
    # --------------------------------------------------------

    print_tool_result(
        result
    )

    # --------------------------------------------------------
    # STEP 9 — NATURAL LANGUAGE RESPONSE
    # --------------------------------------------------------

    response = respond_to_action_result(
        action,
        parameters,
        result
    )

    if response:

        print(
            f"BENVIN: {response}"
        )

        store_assistant_response(
            response
        )


# ============================================================
# HANDLE INTENT
# ============================================================

def handle_intent(intent):
    """
    Route an intent to the correct handler.
    """

    if not isinstance(
        intent,
        dict
    ):

        message = (
            "I couldn't understand "
            "that request."
        )

        print(
            f"BENVIN: {message}"
        )

        store_assistant_response(
            message
        )

        return

    intent_type = intent.get(
        "type"
    )

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    if intent_type == "conversation":

        handle_conversation(
            intent
        )

        return

    # --------------------------------------------------------
    # Action
    # --------------------------------------------------------

    if intent_type == "action":

        handle_action(
            intent
        )

        return

    # --------------------------------------------------------
    # Error
    # --------------------------------------------------------

    if intent_type == "error":

        message = (
            "I encountered an internal "
            "AI engine error."
        )

        print(
            f"BENVIN: {message}"
        )

        if intent.get(
            "error"
        ):

            print(
                f"Reason: {intent['error']}"
            )

            message = (
                f"{message} "
                f"Reason: {intent['error']}"
            )

        store_assistant_response(
            message
        )

        return

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    message = (
        "I received an unknown "
        "instruction type."
    )

    print(
        f"BENVIN: {message}"
    )

    store_assistant_response(
        message
    )


# ============================================================
# STORE USER MESSAGE
# ============================================================

def store_user_message(
    user_input
):
    """
    Store the user's message in short-term context.
    """

    try:

        add_message(
            "user",
            user_input
        )

    except Exception as error:

        print(
            f"[Context warning] "
            f"Could not store user message: "
            f"{error}"
        )


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print()

    print(
        "=" * 60
    )

    print(
        "                    BENVIN"
    )

    print(
        "             Local AI Assistant"
    )

    print(
        "=" * 60
    )

    print()

    print(
        "BENVIN: Online. How can I help?"
    )

    print()

    while True:

        try:

            user_input = input(
                "You: "
            ).strip()

        except KeyboardInterrupt:

            print()

            print(
                "BENVIN: Goodbye."
            )

            break

        except EOFError:

            print()

            print(
                "BENVIN: Goodbye."
            )

            break

        # ----------------------------------------------------
        # Empty input
        # ----------------------------------------------------

        if not user_input:

            continue

        # ----------------------------------------------------
        # Exit
        # ----------------------------------------------------

        if user_input.lower() in {
            "exit",
            "quit",
            "bye",
            "goodbye"
        }:

            print()

            print(
                "BENVIN: Goodbye."
            )

            break

        # ----------------------------------------------------
        # Store user message
        # ----------------------------------------------------

        store_user_message(
            user_input
        )

        # ----------------------------------------------------
        # Analyze request
        # ----------------------------------------------------

        try:

            intent = analyze_intent(
                user_input
            )

        except Exception as error:

            print()

            print(
                "BENVIN: Something went wrong "
                "while understanding that request."
            )

            print(
                f"Error: {error}"
            )

            store_assistant_response(
                "Something went wrong while "
                "understanding that request."
            )

            continue

        # ----------------------------------------------------
        # Handle intent
        # ----------------------------------------------------

        handle_intent(
            intent
        )

        print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()