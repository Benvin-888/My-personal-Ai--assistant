from tools.system import get_system_info
from memory import remember, get_memories


def route_command(user_input):
    command = user_input.lower().strip()

    # -------------------------
    # SYSTEM INFORMATION
    # -------------------------

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

    if any(keyword in command for keyword in system_keywords):
        return {
            "tool": "system_info",
            "success": True,
            "data": get_system_info()
        }

    # -------------------------
    # REMEMBER
    # -------------------------

    if command.startswith("remember that "):
        fact = user_input[len("remember that "):].strip()

        if fact:
            remember(fact)

            return {
                "tool": "memory",
                "success": True,
                "data": {
                    "message": f"I'll remember that: {fact}"
                }
            }

    # -------------------------
    # SHOW MEMORY
    # -------------------------

    memory_keywords = [
        "what do you remember",
        "show my memories",
        "show memories",
        "my memories",
        "what have you remembered"
    ]

    if any(keyword in command for keyword in memory_keywords):
        memories = get_memories()

        return {
            "tool": "memory",
            "success": True,
            "data": {
                "memories": memories
            }
        }

    return None