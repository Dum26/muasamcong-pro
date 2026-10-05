"""Comparison keys; never replace the original source value."""
from __future__ import annotations

import re
import unicodedata


def normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


def safe_display_text(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()
