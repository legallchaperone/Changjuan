from __future__ import annotations

import re

PHONE_RE = re.compile(r"(?<!\d)(?:\+86\s*)?1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_pii(message: str) -> str:
    message = PHONE_RE.sub("[PHONE]", message)
    return ID_CARD_RE.sub("[ID_CARD]", message)
