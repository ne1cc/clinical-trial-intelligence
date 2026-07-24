import re

_NON_WORD = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: object) -> str | None:
    """Deterministic text normalization for matching: lowercase, apostrophes
    removed, punctuation to spaces, whitespace collapsed."""
    if value is None:
        return None
    text = str(value).replace("\u2019", "'").replace("'", "")
    text = _NON_WORD.sub(" ", text.lower())
    text = _WHITESPACE.sub(" ", text).strip()
    return text or None
