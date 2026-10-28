import json
import os
import tempfile
from typing import Any

EMPTY_STATE: dict[str, Any] = {"tracks": {}}


def load(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"tracks": {}}
    except (json.JSONDecodeError, OSError):
        return {"tracks": {}}
    if not isinstance(data, dict):
        return {"tracks": {}}
    data.setdefault("tracks", {})
    return data


def save(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
