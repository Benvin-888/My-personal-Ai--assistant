import requests
from memory import search_memories


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:1.7b"


def build_memory_context(user_message):
    memories = search_memories(user_message)

    if not memories:
        return "No relevant memories were found."

    memory_text = "\n".join(
        f"- {memory['content']}"
        for memory in memories[:5]
    )

    return memory_text


def ask_benvin(message):

    memory_context = build_memory_context(message)

    prompt = f"""
You are BENVIN, a personal AI assistant.

ASSISTANT = BENVIN
USER = the person talking to you

Relevant facts about the USER:

{memory_context}

Rules:
1. The memories above belong to the USER.
2. Never treat a USER memory as your own preference.
3. Use memories only when they are relevant to the user's question.
4. Do not mention the memory system unless the user asks.
5. Do not invent personal information.
6. Answer directly and naturally.
7. Keep responses concise.

USER:
{message}

BENVIN:
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    response.raise_for_status()

    data = response.json()

    return data["response"].strip()