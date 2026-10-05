import sys
import os
import re
import unicodedata

def normalize_wake_phrase(text: str) -> str:
    """Robust normalization for wake-word matching:
    - lowercase
    - strip diacritics / unicode accents ('arōgya' -> 'arogya', 'arogyā' -> 'arogya')
    - punctuation stripped
    - repeated spaces collapsed
    - acoustic phonetic variants ('arogia', 'arogy', 'aarogya', 'erogya' -> 'arogya')
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower().strip())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = re.sub(r"[^\w\s]", " ", stripped)
    cleaned = " ".join(cleaned.split())

    # Normalize wake word token variations
    cleaned = re.sub(r"\b(aarogya|arogia|arogy|aroga|aroya|erogya|aerogya|arogyam|arokya|arokiya)\b", "arogya", cleaned)
    # Common salutations
    cleaned = re.sub(r"\b(hay|hai|hi|hello)\b", "hey", cleaned)
    return cleaned

def is_wake_word(text: str) -> tuple[bool, str, str, float]:
    """Check wake word and return (detected, remaining, normalized, confidence)."""
    norm = normalize_wake_phrase(text)
    if not norm:
        return False, "", norm, 0.0

    # Pattern check
    pattern = r"\b(hey\s+arogya|arogya)\b"
    m = re.search(pattern, norm)
    if m:
        start, end = m.span()
        rem = (norm[:start] + " " + norm[end:]).strip()
        conf = 1.0 if norm in ("hey arogya", "arogya") else 0.95
        return True, rem, norm, conf

    return False, text, norm, 0.0

test_phrases = [
    'Hey Arogya',
    'Hey Arogya!',
    'hey arogya',
    'Hey Arōgya',
    'Hey Arogyā',
    'Hey Arogia',
    'Hi Arogya',
    'Hey Arogy',
    'Hey, Arogya',
    'Hey Aarogya',
    'Hey Arogyam',
    'Arogya',
    'Hey Arogya go to ICU',
    'Hey Arogya, deliver medicine to P003',
    'Go to ICU',
    'Deliver Paracetamol to Room 205',
]

print("--- PROPOSED WAKE NORMALIZATION & DETECTION ---")
for p in test_phrases:
    det, rem, norm, conf = is_wake_word(p)
    print(f"{p:<38} -> Det: {str(det):<5} | Conf: {conf:.2f} | Norm: '{norm:<15}' | Rem: '{rem}'")
