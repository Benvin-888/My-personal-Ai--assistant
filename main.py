import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:1.7b"


def ask_benvin(message):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": message,
            "stream": False
        }
    )

    response.raise_for_status()

    data = response.json()
    return data["response"]


while True:
    user_input = input("You: ").strip()

    # Ignore empty input
    if not user_input:
        continue

    # Exit BENVIN
    if user_input.lower() in ["exit", "quit", "bye"]:
        print("BENVIN: Goodbye.")
        break

    answer = ask_benvin(user_input)

    print(f"BENVIN: {answer}")