from __future__ import annotations

from typing import Any, Mapping


def get_session_id(data: Mapping[str, Any] | None) -> str:
    if not data:
        return "default"
    raw = data.get("sessionId", "default")
    if raw is None:
        return "default"
    session_id = str(raw).strip()
    if not session_id:
        raise ValueError("sessionId must not be empty")
    return session_id


def bool_from_value(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"invalid boolean value: {value!r}")
