import re


_DASH_TRANSLATION = str.maketrans(
    {
        "–": "-",  # en dash
        "—": "-",  # em dash
        "−": "-",  # minus
        "‒": "-",  # figure dash
    }
)


_SPACE_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")

# Token splits (case-insensitive).
_TOKEN_SPLIT_RE = re.compile(r"\b(sec|s|jc|j|p|k|year)(\d{1,2})\b", re.IGNORECASE)

# Time punctuation:
# - 7.30pm -> 7:30pm
_TIME_DOT_WITH_AMPM_RE = re.compile(r"\b(\d{1,2})\.(\d{2})\s*([ap]m)\b", re.IGNORECASE)

# - 2.30-5.30pm -> 2:30-5:30pm (only when second side has am/pm)
_TIME_RANGE_LEFT_DOT_RE = re.compile(
    r"\b(\d{1,2})\.(\d{2})(?=\s*-\s*\d{1,2}\.\d{2}\s*[ap]m\b)",
    re.IGNORECASE,
)


def normalize_text(raw: str) -> str:
    """
    Deterministically normalize raw assignment text.

    Conservative: mechanical transforms only (no paraphrasing, no inference).
    """
    if raw is None:
        return ""

    s = str(raw)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.translate(_DASH_TRANSLATION)

    # Normalize time punctuation first (after dash normalization to keep "-" stable).
    s = _TIME_RANGE_LEFT_DOT_RE.sub(r"\1:\2", s)
    s = _TIME_DOT_WITH_AMPM_RE.sub(r"\1:\2\3", s)

    # Split common academic tokens: sec3 -> sec 3, p5 -> p 5, etc.
    def _split_token(m: re.Match[str]) -> str:
        prefix = m.group(1)
        num = m.group(2)
        return f"{prefix} {num}"

    s = _TOKEN_SPLIT_RE.sub(_split_token, s)

    # Whitespace normalization (preserve newlines).
    s = s.replace("\t", " ")
    s = "\n".join(_SPACE_RE.sub(" ", line).strip() for line in s.split("\n"))
    s = _BLANKLINES_RE.sub("\n\n", s).strip()
    return s

