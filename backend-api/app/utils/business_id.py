from __future__ import annotations

import re
import uuid


BUSINESS_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def generate_business_id() -> str:
    return uuid.uuid4().hex


def normalize_business_id(value: str | None) -> str:
    return (value or "").strip().lower()


def is_valid_business_id(value: str | None) -> bool:
    return bool(BUSINESS_ID_PATTERN.fullmatch(normalize_business_id(value)))

