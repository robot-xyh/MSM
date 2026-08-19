"""Small JSON/JSONL helpers that preserve online/offline separation."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any, Iterable


def _payload(value: Any) -> Any:
    return asdict(value) if is_dataclass(value) else value


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_payload(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path

def write_jsonl(path: Path, rows: Iterable[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(_payload(row), ensure_ascii=False) + "\n")
    return path
