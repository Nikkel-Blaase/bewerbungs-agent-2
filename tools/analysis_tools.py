"""Language detection utility."""

try:
    from langdetect import detect as _langdetect
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False


def detect_language(text: str) -> dict:
    if _LANGDETECT_AVAILABLE:
        try:
            lang = _langdetect(text[:2000])
            if lang.startswith("de"):
                return {"language": "de"}
            return {"language": "en"}
        except Exception:
            pass
    # Heuristic fallback
    german_indicators = ["und", "die", "der", "das", "für", "mit", "wir", "sie", "haben"]
    lower = text.lower()
    count = sum(1 for w in german_indicators if f" {w} " in lower)
    return {"language": "de" if count >= 3 else "en"}
