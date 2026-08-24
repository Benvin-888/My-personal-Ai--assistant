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


def normalize_text(text):
    """
    Normalize text into lowercase words.

    Used by the memory search and similarity system.
    """

    return re.findall(
        r"\b[a-zA-Z0-9]+\b",
        text.lower()
    )


# ============================================================
# MEMORY CLASSIFICATION
# ============================================================

def classify_memory(fact):
    """
    Deterministically classify a memory.
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


# ============================================================
# MEMORY TOPICS
# ============================================================

def detect_topic(fact):
    """
    Detect the persistent topic represented by a memory.

    This is deterministic for now.

    Later we can make this more intelligent using
    BENVIN/Qwen3-assisted topic extraction.
    """

    text = fact.lower()

    # --------------------------------------------------------
    # Preferences
    # --------------------------------------------------------

    if "favorite programming language" in text:
        return "favorite_programming_language"

    if "favorite color" in text:
        return "favorite_color"

    if "favorite food" in text:
        return "favorite_food"

    if "favorite game" in text:
        return "favorite_game"

    if "favorite movie" in text:
        return "favorite_movie"

    if "favorite book" in text:
        return "favorite_book"

    # --------------------------------------------------------
    # Projects
    # --------------------------------------------------------

    if "building benvin" in text:
        return "current_project_benvin"

    if "building" in text:
        return "current_project"

    if "developing" in text:
        return "current_project"

    if "working on" in text:
        return "current_project"

    # --------------------------------------------------------
    # Identity
    # --------------------------------------------------------

    if "my name is" in text:
        return "user_name"

    # --------------------------------------------------------
    # Goals
    # --------------------------------------------------------

    if "my goal" in text:
        return "user_goal"

    if "want to" in text:
        return "user_goal"

    if "plan to" in text:
        return "user_goal"

    # --------------------------------------------------------
    # No known topic
    # --------------------------------------------------------

    return None


# ============================================================
# CREATE MEMORY
# ============================================================

def create_memory(fact):
    """
    Create a structured memory object.
    """

    timestamp = current_timestamp()

    return {
        "id": generate_id(),
        "content": fact,
        "topic": detect_topic(fact),
        "category": classify_memory(fact),
        "importance": 0.5,
        "confidence": 1.0,
        "source": "user",
        "created_at": timestamp,
        "updated_at": timestamp
    }


# ============================================================
# MEMORY MIGRATION
# ============================================================

def migrate_memory(memory):
    """
    Convert old BENVIN memory formats into the current format.

    Old format:

        {
            "fact": "..."
        }

    Current format:

        {
            "id": "...",
            "content": "...",
            "topic": "...",
            "category": "...",
            ...
        }

    Existing structured memories are preserved.
    Missing topics are automatically added.
    """

    migrated = []
    changed = False

    for item in memory:

        # ----------------------------------------------------
        # OLD FORMAT
        # ----------------------------------------------------

        if "fact" in item and "content" not in item:

            new_memory = create_memory(
                item["fact"]
            )

            migrated.append(new_memory)

            changed = True

            continue

        # ----------------------------------------------------
        # CURRENT FORMAT
        # ----------------------------------------------------

        if "content" in item:

            # Add missing topic
            if "topic" not in item:

                item["topic"] = detect_topic(
                    item["content"]
                )

                changed = True

            # Ensure missing fields are restored
            if "category" not in item:

                item["category"] = classify_memory(
                    item["content"]
                )

                changed = True

            if "importance" not in item:

                item["importance"] = 0.5

                changed = True

            if "confidence" not in item:

                item["confidence"] = 1.0

                changed = True

            if "source" not in item:

                item["source"] = "user"

                changed = True

            if "created_at" not in item:

                item["created_at"] = current_timestamp()

                changed = True

            if "updated_at" not in item:

                item["updated_at"] = (
                    item["created_at"]
                )

                changed = True

            migrated.append(item)

    return migrated, changed


# ============================================================
# LOAD / SAVE
# ============================================================

def load_memory():
    """
    Load memories from memory.json.

    Automatically migrates old memory formats.
    """

    if not os.path.exists(MEMORY_FILE):
        return []

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            memory = json.load(file)

    except (json.JSONDecodeError, OSError):

        return []

    # Make sure the root is a list
    if not isinstance(memory, list):
        return []

    memory, changed = migrate_memory(
        memory
    )

    if changed:
        save_memory(memory)

    return memory


def save_memory(memory):
    """
    Save memories to memory.json.
    """

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            memory,
            file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# CREATE / REMEMBER
# ============================================================

def remember(
    fact,
    category=None,
    importance=0.5,
    confidence=1.0
):
    """
    Store a new memory.

    Prevents exact duplicate memories.

    Returns:
        Existing or newly created memory.
    """

    memory = load_memory()

    normalized_fact = fact.lower().strip()

    # --------------------------------------------------------
    # Exact duplicate prevention
    # --------------------------------------------------------

    for existing in memory:

        if existing["content"].lower().strip() == normalized_fact:

            return existing

    # --------------------------------------------------------
    # Create new memory
    # --------------------------------------------------------

    new_memory = create_memory(
        fact
    )

    if category:
        new_memory["category"] = category

    new_memory["importance"] = importance
    new_memory["confidence"] = confidence

    memory.append(
        new_memory
    )

    save_memory(
        memory
    )

    return new_memory


# ============================================================
# RETRIEVE ALL MEMORIES
# ============================================================

def get_memories():
    """
    Return all stored memories.
    """

    return load_memory()


# ============================================================
# SEARCH MEMORIES
# ============================================================

def search_memories(query):
    """
    Search memories using normalized keyword matching.

    Features:

    - punctuation normalization
    - stop-word removal
    - meaningful word matching
    - relevance scoring
    - importance boost
    - confidence boost

    This is the foundation for future
    semantic/vector memory retrieval.
    """

    memories = load_memory()

    query_words = set(
        normalize_text(query)
    )

    # --------------------------------------------------------
    # Stop words
    # --------------------------------------------------------

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
        "who",
        "to",
        "of",
        "on",
        "in",
        "for"
    }

    query_words -= stop_words

    if not query_words:
        return []

    results = []

    # --------------------------------------------------------
    # Search every memory
    # --------------------------------------------------------

    for memory in memories:

        content_words = set(
            normalize_text(
                memory["content"]
            )
        )

        matched_words = (
            query_words.intersection(
                content_words
            )
        )

        if not matched_words:
            continue

        # Number of matching words
        match_score = len(
            matched_words
        )

        # Query coverage
        coverage = (
            match_score
            / len(query_words)
        )

        # Importance
        importance = memory.get(
            "importance",
            0.5
        )

        # Confidence
        confidence = memory.get(
            "confidence",
            1.0
        )

        # Final relevance score
        score = (
            match_score
            + (coverage * 0.5)
            + (importance * 0.1)
            + (confidence * 0.1)
        )

        results.append({
            "score": score,
            "memory": memory
        })

    # --------------------------------------------------------
    # Highest relevance first
    # --------------------------------------------------------

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return [
        item["memory"]
        for item in results
    ]


# ============================================================
# FIND MEMORY
# ============================================================

def find_memory(query):
    """
    Find the most relevant memory.

    Returns:
        memory object
        or None
    """

    results = search_memories(
        query
    )

    if not results:
        return None

    return results[0]


# ============================================================
# FIND MEMORY BY TOPIC
# ============================================================

def find_memory_by_topic(topic):
    """
    Find a memory using its persistent topic.

    Example:

        find_memory_by_topic(
            "favorite_programming_language"
        )
    """

    memories = load_memory()

    for memory in memories:

        if memory.get("topic") == topic:

            return memory

    return None


# ============================================================
# CALCULATE MEMORY SIMILARITY
# ============================================================

def calculate_similarity(text_a, text_b):
    """
    Calculate a simple word-based similarity score.

    Returns a value between 0.0 and 1.0.
    """

    words_a = set(
        normalize_text(text_a)
    )

    words_b = set(
        normalize_text(text_b)
    )

    if not words_a or not words_b:
        return 0.0

    intersection = words_a.intersection(
        words_b
    )

    union = words_a.union(
        words_b
    )

    return len(intersection) / len(union)


# ============================================================
# REMEMBER OR UPDATE
# ============================================================

def remember_or_update(
    fact,
    category=None,
    importance=0.5,
    confidence=1.0
):
    """
    Store a new memory or update an existing
    strongly matching memory.

    Topic matching is preferred over
    general text similarity.
    """

    # --------------------------------------------------------
    # Determine topic
    # --------------------------------------------------------

    topic = detect_topic(
        fact
    )

    # --------------------------------------------------------
    # First try exact topic matching
    # --------------------------------------------------------

    if topic:

        existing = find_memory_by_topic(
            topic
        )

        if existing:

            updated = update_memory(
                existing["id"],
                content=fact,
                topic=topic,
                category=(
                    category
                    or existing.get(
                        "category",
                        "fact"
                    )
                ),
                importance=importance,
                confidence=confidence
            )

            return {
                "action": "updated",
                "memory": updated
            }

    # --------------------------------------------------------
    # No topic match — use similarity
    # --------------------------------------------------------

    memories = load_memory()

    best_memory = None
    best_score = 0.0

    for memory in memories:

        similarity = calculate_similarity(
            fact,
            memory["content"]
        )

        if similarity > best_score:

            best_score = similarity
            best_memory = memory

    # --------------------------------------------------------
    # Similarity threshold
    # --------------------------------------------------------

    UPDATE_THRESHOLD = 0.40

    if (
        best_memory
        and best_score >= UPDATE_THRESHOLD
    ):

        updated = update_memory(
            best_memory["id"],
            content=fact,
            topic=(
                topic
                or best_memory.get("topic")
            ),
            category=(
                category
                or best_memory.get(
                    "category",
                    "fact"
                )
            ),
            importance=importance,
            confidence=confidence
        )

        return {
            "action": "updated",
            "memory": updated
        }

    # --------------------------------------------------------
    # Otherwise create new memory
    # --------------------------------------------------------

    new_memory = remember(
        fact,
        category=category,
        importance=importance,
        confidence=confidence
    )

    return {
        "action": "created",
        "memory": new_memory
    }


# ============================================================
# UPDATE MEMORY
# ============================================================

def update_memory(
    memory_id,
    **updates
):
    """
    Update an existing memory.
    """

    memory = load_memory()

    allowed_fields = {
        "content",
        "topic",
        "category",
        "importance",
        "confidence"
    }

    for item in memory:

        if item["id"] == memory_id:

            for key, value in updates.items():

                if key in allowed_fields:

                    item[key] = value

            item["updated_at"] = (
                current_timestamp()
            )

            save_memory(
                memory
            )

            return item

    return None


# ============================================================
# DELETE MEMORY
# ============================================================

def delete_memory(memory_id):
    """
    Delete a memory by ID.

    Returns:
        True  -> deleted
        False -> memory not found
    """

    memory = load_memory()

    new_memory = [
        item
        for item in memory
        if item["id"] != memory_id
    ]

    if len(new_memory) == len(memory):

        return False

    save_memory(
        new_memory
    )

    return True