from brain import ask_benvin
from router import route_command


while True:
    user_input = input("You: ").strip()

    if not user_input:
        continue

    # Exit commands
    if user_input.lower() in ["exit", "quit", "bye"]:
        print("BENVIN: Goodbye.")
        break

    # Check if the user command should use a tool
    tool_result = route_command(user_input)

    if tool_result is not None:

        print(f"\nBENVIN: Tool used → {tool_result['tool']}")

        # -------------------------
        # MEMORY TOOL
        # -------------------------

        if tool_result["tool"] == "memory":

            data = tool_result["data"]

            # Remember command
            if "message" in data:
                print(f"BENVIN: {data['message']}")

            # Show memories command
            elif "memories" in data:

                memories = data["memories"]

                if not memories:
                    print("BENVIN: I don't have any memories yet.")

                else:
                    print("BENVIN: Here is what I remember:\n")

                    for index, memory in enumerate(memories, start=1):
                        print(f"{index}. {memory['fact']}")

        # -------------------------
        # OTHER TOOLS
        # -------------------------

        else:

            print("BENVIN: Here is the information I found:\n")

            for key, value in tool_result["data"].items():
                print(f"{key}: {value}")

        print()
        continue

    # -------------------------
    # NORMAL AI CONVERSATION
    # -------------------------

    answer = ask_benvin(user_input)

    print(f"BENVIN: {answer}")