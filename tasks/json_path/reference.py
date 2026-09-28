import re
from typing import Any

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def get_path(data: Any, path: str, default: Any = None) -> Any:
    if path in ("", "$"):
        return data
    if path.startswith("$"):
        path = path[1:]
        if path.startswith("."):
            path = path[1:]
            if not re.match(IDENT, path):
                raise ValueError("expected identifier")
        elif not path.startswith("["):
            raise ValueError("invalid root")
    parts: list[str | int] = []
    pos = 0
    first = re.match(IDENT, path)
    if first:
        parts.append(first.group())
        pos = first.end()
    while pos < len(path):
        index = re.match(r"\[([0-9]+)\]", path[pos:])
        key = re.match(r"\.(" + IDENT + ")", path[pos:]) if parts else None
        if index:
            parts.append(int(index.group(1)))
            pos += index.end()
        elif key:
            parts.append(key.group(1))
            pos += key.end()
        else:
            raise ValueError("invalid path")
    if not parts:
        raise ValueError("empty rooted path")
    for part in parts:
        if isinstance(part, int):
            if not isinstance(data, list) or part >= len(data):
                return default
            data = data[part]
        else:
            if not isinstance(data, dict) or part not in data:
                return default
            data = data[part]
    return data
