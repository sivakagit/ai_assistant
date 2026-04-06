"""
Embedding service for semantic memory search.

Uses Ollama embeddings to:
- Generate vector embeddings for memory items and user queries
- Cache embeddings for performance
- Search memory semantically using cosine similarity
- Fall back gracefully if Ollama is unavailable
"""

import json
import os
from threading import Lock
from typing import Optional

import ollama

from core.logger import get_logger
from core.config import resource_path

logger = get_logger()

# Thread-safe cache management
_embedding_lock = Lock()

# Configuration
EMBEDDINGS_CACHE_FILE = resource_path("data/config/embeddings.json")
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
CACHE_VERSION = "1"


def cosine_similarity(vec1: list, vec2: list) -> float:
    """
    Calculate cosine similarity between two vectors.
    Returns value between 0 and 1 (0 = dissimilar, 1 = identical).
    No external dependencies needed.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = sum(a ** 2 for a in vec1) ** 0.5
    mag2 = sum(b ** 2 for b in vec2) ** 0.5

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


def embed_text(text: str, model: str = DEFAULT_EMBEDDING_MODEL) -> Optional[list]:
    """
    Generate embedding for text using Ollama.
    Returns list of floats, or None if embedding fails.
    """
    if not text or not isinstance(text, str):
        return None

    try:
        response = ollama.embeddings(model=model, prompt=text.strip())
        return response.get("embedding")
    except Exception as e:
        logger.warning(f"[embedding] Failed to embed text with {model}: {e}")
        return None


def load_embedding_cache() -> dict:
    """
    Load embedding cache from disk.
    Returns dict with structure: {"embeddings": {key: [float, ...]}, "version": "1", ...}
    """
    if not os.path.exists(EMBEDDINGS_CACHE_FILE):
        return {"embeddings": {}, "version": CACHE_VERSION, "model": DEFAULT_EMBEDDING_MODEL}

    try:
        with _embedding_lock:
            with open(EMBEDDINGS_CACHE_FILE, "r") as f:
                cache = json.load(f)

            # Validate cache structure
            if "embeddings" not in cache or "version" not in cache:
                logger.warning("[embedding] Cache corrupted, creating new")
                return {"embeddings": {}, "version": CACHE_VERSION, "model": DEFAULT_EMBEDDING_MODEL}

            return cache
    except Exception as e:
        logger.warning(f"[embedding] Failed to load cache: {e}")
        return {"embeddings": {}, "version": CACHE_VERSION, "model": DEFAULT_EMBEDDING_MODEL}


def save_embedding_cache(cache: dict) -> bool:
    """Save embedding cache to disk. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(EMBEDDINGS_CACHE_FILE), exist_ok=True)

        with _embedding_lock:
            with open(EMBEDDINGS_CACHE_FILE, "w") as f:
                json.dump(cache, f, indent=2)

        return True
    except Exception as e:
        logger.error(f"[embedding] Failed to save cache: {e}")
        return False


def embed_and_cache_item(key: str, value: str, model: str = DEFAULT_EMBEDDING_MODEL) -> bool:
    """
    Generate embedding for a key-value memory pair and cache it.
    Cache key format: "key|value" to handle duplicates.
    Returns True on success.
    """
    if not key or not value:
        return False

    # Create cache key
    cache_key = f"{key}|{value}"

    # Generate embedding
    embedding = embed_text(f"{key} {value}", model)
    if not embedding:
        logger.debug(f"[embedding] Could not embed memory item: {cache_key}")
        return False

    # Load cache and update
    cache = load_embedding_cache()
    cache["embeddings"][cache_key] = embedding
    cache["model"] = model

    # Save updated cache
    return save_embedding_cache(cache)


def search_memory(
    query: str,
    memory_items: dict,
    top_k: int = 5,
    model: str = DEFAULT_EMBEDDING_MODEL,
    min_similarity: float = 0.3
) -> list:
    """
    Search memory items by semantic similarity to query.

    Args:
        query: User's question/input to search for
        memory_items: Dict of memory items {key: value, ...}
        top_k: Number of top results to return (default 5)
        model: Embedding model to use
        min_similarity: Minimum similarity score to include (0-1)

    Returns:
        List of dicts: [{"key": ..., "value": ..., "similarity": 0.85}, ...]
        Sorted by similarity descending (highest first).
    """
    if not query or not memory_items:
        return []

    # Embed the query
    query_embedding = embed_text(query, model)
    if not query_embedding:
        logger.debug("[embedding] Query embedding failed, returning empty results")
        return []

    # Load embedding cache
    cache = load_embedding_cache()
    cached_embeddings = cache.get("embeddings", {})

    # Score all memory items
    scored_items = []

    for key, value in memory_items.items():
        # Handle nested profile dict
        if isinstance(value, dict):
            continue

        cache_key = f"{key}|{value}"

        # Get embedding from cache or generate fresh
        if cache_key in cached_embeddings:
            embedding = cached_embeddings[cache_key]
        else:
            embedding = embed_text(f"{key} {value}", model)
            if embedding:
                cached_embeddings[cache_key] = embedding
                cache["embeddings"] = cached_embeddings
                save_embedding_cache(cache)

        # Calculate similarity
        if embedding:
            similarity = cosine_similarity(query_embedding, embedding)
            if similarity >= min_similarity:
                scored_items.append({
                    "key": key,
                    "value": value,
                    "similarity": round(similarity, 3)
                })

    # Sort by similarity (highest first) and return top_k
    scored_items.sort(key=lambda x: x["similarity"], reverse=True)
    return scored_items[:top_k]


def clear_embedding_cache() -> bool:
    """Clear all cached embeddings. Useful for debugging or resetting."""
    try:
        with _embedding_lock:
            empty_cache = {
                "embeddings": {},
                "version": CACHE_VERSION,
                "model": DEFAULT_EMBEDDING_MODEL
            }
            return save_embedding_cache(empty_cache)
    except Exception as e:
        logger.error(f"[embedding] Failed to clear cache: {e}")
        return False


def get_cache_stats() -> dict:
    """Get statistics about the embedding cache."""
    cache = load_embedding_cache()
    embeddings = cache.get("embeddings", {})

    return {
        "cached_items": len(embeddings),
        "version": cache.get("version"),
        "model": cache.get("model"),
        "cache_file": EMBEDDINGS_CACHE_FILE,
        "cache_exists": os.path.exists(EMBEDDINGS_CACHE_FILE)
    }


def is_embedding_model_available(model: str = DEFAULT_EMBEDDING_MODEL) -> bool:
    """Check if the embedding model is available in Ollama."""
    try:
        response = ollama.list()
        models = [m.get("name") for m in response.get("models", [])]
        for m in models:
            if m and model in m:
                return True
        return False
    except Exception as e:
        logger.debug(f"[embedding] Failed to check model availability: {e}")
        return False
