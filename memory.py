import json
import os
import uuid
import re
from datetime import datetime, timezone


MEMORY_FILE = "memory.json"


# ============================================================
# INTERNAL HELPERS
# ============================================================

def generate_id():
    """Generate a unique memory ID."""
    return f"mem_{uuid.uuid4().hex[:12]}"


def current_timestamp():
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def classify_memory(fact):
    """
    Basic deterministic memory classification.
    """

    text = fact.lower()

    if any(word in text for word in [
        "favorite",
        "prefer",
        "like",
        "love",
        "enjoy"
    ]):
        return "preference"

    if any(word in text for word in [
        "building",
        "developing",
        "working on",
        "project"
    ]):
        return "project"

    if any(word in text for word in [
        "goal",
        "want to",
        "plan to",
        "planning to"
    ]):
        return "goal"

    if any(word in text for word in [
        "my name",
        "i am",
        "i'm"
    ]):
        return "identity"

    return "fact"


def create_memory(fact):
    """Create a structured memory object."""

    timestamp = current_timestamp()

    return {
        "id": generate_id(),
        "content": fact,
        "category": classify_memory(fact),
        "importance": 0.5,
        "confidence": 1.0,
        "source": "user",
        "created_at": timestamp,
        "updated_at": timestamp
    }


def migrate_memory(memory):
    """
    Convert old BENVIN memory format into the new structure.
    """

    migrated = []
    changed = False

    for item in memory:

        # Already using the new format
        if "content" in item:
            migrated.append(item)
            continue

        # Convert old {"fact": "..."} format
        if "fact" in item:
            new_memory = create_memory(item["fact"])
            migrated.append(new_memory)
            changed = True

    return migrated, changed


# ============================================================
# LOAD / SAVE
# ============================================================

def load_memory():
    """Load memories and automatically migrate old memories."""

    if not os.path.exists(MEMORY_FILE):
        return []

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            memory = json.load(file)

    except (json.JSONDecodeError, OSError):
        return []

    memory, changed = migrate_memory(memory)

    if changed:
        save_memory(memory)

    return memory


def save_memory(memory):
    """Save memories to the local JSON file."""

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            memory,
            file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# CREATE MEMORY
# ============================================================

def remember(
    fact,
    category=None,
    importance=0.5,
    confidence=1.0
):
    """
    Store a new memory.

    Returns the created memory.
    """

    memory = load_memory()

    # Prevent exact duplicate memories
    for existing in memory:

        if existing["content"].lower().strip() == fact.lower().strip():
            return existing

    new_memory = create_memory(fact)

    if category:
        new_memory["category"] = category

    new_memory["importance"] = importance
    new_memory["confidence"] = confidence

    memory.append(new_memory)

    save_memory(memory)

    return new_memory


# ============================================================
# RETRIEVE ALL MEMORIES
# ============================================================

def get_memories():
    """Return all stored memories."""

    return load_memory()


# ============================================================
# SEARCH MEMORIES
# ============================================================

def search_memories(query):
    """
    Search memories using normalized keyword matching.

    Features:
    - Removes punctuation
    - Removes common stop words
    - Matches meaningful words
    - Scores relevance
    - Uses memory importance as a ranking boost

    This is the foundation for future semantic/vector search.
    """

    memories = load_memory()

    # Normalize query and extract words
    query_words = set(
        re.findall(r"\b[a-zA-Z0-9]+\b", query.lower())
    )

    # Common words that don't help identify memories
    stop_words = {
        "what",
        "is",
        "am",
        "are",
        "do",
        "does",
        "did",
        "the",
        "a",
        "an",
        "i",
        "my",
        "me",
        "you",
        "your",
        "about",
        "tell",
        "can",
        "could",
        "would",
        "please",
        "how",
        "why",
        "when",
        "where",
        "which",
        "who"
    }

    query_words -= stop_words

    if not query_words:
        return []

    results = []

    for memory in memories:

        content = memory["content"].lower()

        content_words = set(
            re.findall(r"\b[a-zA-Z0-9]+\b", content)
        )

        matched_words = query_words.intersection(content_words)

        if matched_words:

            # Base relevance score
            score = len(matched_words)

            # Small importance boost
            score += memory.get("importance", 0.5) * 0.1

            results.append({
                "score": score,
                "memory": memory
            })

    # Highest relevance first
    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return [
        item["memory"]
        for item in results
    ]


# ============================================================
# UPDATE MEMORY
# ============================================================

def update_memory(memory_id, **updates):
    """Update an existing memory."""

    memory = load_memory()

    allowed_fields = {
        "content",
        "category",
        "importance",
        "confidence"
    }

    for item in memory:

        if item["id"] == memory_id:

            for key, value in updates.items():

                if key in allowed_fields:
                    item[key] = value

            item["updated_at"] = current_timestamp()

            save_memory(memory)

            return item

    return None


# ============================================================
# DELETE MEMORY
# ============================================================

def delete_memory(memory_id):
    """Delete a memory by its ID."""

    memory = load_memory()

    new_memory = [
        item
        for item in memory
        if item["id"] != memory_id
    ]

    if len(new_memory) == len(memory):
        return False

    save_memory(new_memory)

    return True