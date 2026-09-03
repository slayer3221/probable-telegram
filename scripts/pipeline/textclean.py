"""Deterministic cleanup for model-written prose fields.

Structured-output text occasionally carries broken escapes: a literal
"\\u2014" instead of the character, a newline standing in for a dash, or a
control character left by an accidental JSON escape. Dashes themselves are
replaced with commas to match the site's house style. No words are added.
"""
import re

_LITERAL_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def clean_text(text):
    if not text:
        return text or ""
    out = _LITERAL_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)
    out = out.replace("\u2014", ", ").replace("\u2013", ", ")
    out = re.sub(r"\s*[\r\n]+\s*", ", ", out.strip())
    out = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", out)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",(\s*,)+", ",", out)
    out = re.sub(r"([:;,])\s*,", r"\1", out)
    return out.strip()


def has_broken_escapes(text):
    """True when the text carries a line break or a control character. Those
    repairs are lossy (a control character may have eaten a letter), so the
    record should be regenerated. A literal \\uXXXX escape is repaired
    exactly and does not count."""
    return bool(re.search(r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text or ""))
