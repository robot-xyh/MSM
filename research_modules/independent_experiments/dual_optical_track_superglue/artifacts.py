"""Deterministic artifact helpers for a weights-only frozen route."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from .config import ModelConfig
from .model import TrackSuperGlue


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: str | Path, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON artifact must contain an object")
    return payload


def save_weights(model: TrackSuperGlue, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), destination)


def load_weights(
    path: str | Path,
    config: ModelConfig,
    *,
    device: torch.device | str = "cpu",
) -> TrackSuperGlue:
    model = TrackSuperGlue(config).to(device)
    state = torch.load(Path(path), map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model
