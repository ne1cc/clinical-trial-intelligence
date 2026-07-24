import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: Any) -> str:
    """Stable hash of any JSON-serializable object (canonical key order)."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(canonical)
