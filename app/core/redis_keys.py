from __future__ import annotations

from config import settings


def redis_key(*parts: object) -> str:
    segments = [settings.REDIS_KEY_PREFIX]
    for part in parts:
        if part is None:
            continue
        value = str(part).strip().strip(":")
        if value:
            segments.append(value)
    return ":".join(segments)


def redis_pattern(*parts: object) -> str:
    segments = [settings.REDIS_KEY_PREFIX]
    for part in parts:
        if part is None:
            continue
        value = str(part).strip()
        if not value:
            continue
        if value == "*":
            segments.append(value)
        else:
            segments.append(value.strip(":"))
    return ":".join(segments)

