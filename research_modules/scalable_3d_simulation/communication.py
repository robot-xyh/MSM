"""Deterministic latency, loss, and bandwidth model for episode messages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import heapq
import json
from typing import Any

import numpy as np

from .episode_bus import VersionedEnvelope, assert_online_payload_truth_free, jsonable


@dataclass(frozen=True)
class LinkProfile:
    """One directed communication link profile."""

    latency_s: float = 0.04
    jitter_s: float = 0.01
    drop_probability: float = 0.01
    bandwidth_bytes_per_s: float = 5_000_000.0

    def __post_init__(self) -> None:
        if self.latency_s < 0.0 or self.jitter_s < 0.0:
            raise ValueError("latency and jitter must be non-negative")
        if not 0.0 <= self.drop_probability <= 1.0:
            raise ValueError("drop_probability must be in [0, 1]")
        if self.bandwidth_bytes_per_s <= 0.0:
            raise ValueError("bandwidth_bytes_per_s must be positive")


@dataclass(frozen=True)
class DeliveredMessage:
    """A message released to a destination after simulated transport."""

    source: str
    destination: str
    send_timestamp: float
    arrival_timestamp: float
    envelope: VersionedEnvelope
    payload_size_bytes: int


@dataclass(frozen=True)
class CommunicationStats:
    sent_count: int
    delivered_count: int
    dropped_count: int
    pending_count: int
    sent_bytes: int
    delivered_bytes: int


class DeterministicCommunicationNetwork:
    """Seeded network queue with directed-link overrides."""

    def __init__(self, *, seed: int, default_profile: LinkProfile | None = None) -> None:
        self._base_seed = int(seed)
        self.rng = np.random.default_rng(self._base_seed)
        self._rng_by_stream: dict[str, np.random.Generator] = {}
        self.default_profile = default_profile or LinkProfile()
        self._profiles: dict[tuple[str, str], LinkProfile] = {}
        self._queue: list[tuple[float, int, DeliveredMessage]] = []
        self._counter = 0
        self._sent_count = 0
        self._delivered_count = 0
        self._dropped_count = 0
        self._sent_bytes = 0
        self._delivered_bytes = 0

    def set_link_profile(self, source: str, destination: str, profile: LinkProfile) -> None:
        self._profiles[(str(source), str(destination))] = profile

    def send(
        self,
        *,
        source: str,
        destination: str,
        send_timestamp: float,
        envelope: VersionedEnvelope,
        random_stream: str = "shared_v1",
    ) -> bool:
        """Queue one message and return False when the seeded loss model drops it."""

        if not source or not destination:
            raise ValueError("source and destination must be non-empty")
        stream = str(random_stream).strip()
        if not stream:
            raise ValueError("random_stream must be non-empty")
        if not np.isfinite(send_timestamp) or send_timestamp < 0.0:
            raise ValueError("send_timestamp must be finite and non-negative")
        assert_online_payload_truth_free(envelope.payload)
        profile = self._profiles.get((source, destination), self.default_profile)
        payload_size = len(
            json.dumps(envelope.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        self._sent_count += 1
        self._sent_bytes += payload_size
        rng = self._random_stream(stream)
        if rng.random() < profile.drop_probability:
            self._dropped_count += 1
            return False
        jitter = (
            float(rng.normal(0.0, profile.jitter_s))
            if profile.jitter_s > 0.0
            else 0.0
        )
        serialization_delay = payload_size / profile.bandwidth_bytes_per_s
        arrival = float(send_timestamp) + max(0.0, profile.latency_s + jitter) + serialization_delay
        message = DeliveredMessage(
            source=str(source),
            destination=str(destination),
            send_timestamp=float(send_timestamp),
            arrival_timestamp=arrival,
            envelope=envelope,
            payload_size_bytes=payload_size,
        )
        self._counter += 1
        heapq.heappush(self._queue, (arrival, self._counter, message))
        return True

    def _random_stream(self, stream: str) -> np.random.Generator:
        if stream == "shared_v1":
            return self.rng
        existing = self._rng_by_stream.get(stream)
        if existing is not None:
            return existing
        stream_digest = hashlib.sha256(stream.encode("utf-8")).digest()
        stream_seed = int.from_bytes(stream_digest[:8], "big", signed=False)
        generated = np.random.default_rng(
            np.random.SeedSequence([self._base_seed, stream_seed])
        )
        self._rng_by_stream[stream] = generated
        return generated

    def deliver(self, timestamp: float) -> tuple[DeliveredMessage, ...]:
        """Release all messages whose arrival time is no later than timestamp."""

        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("timestamp must be finite and non-negative")
        delivered: list[DeliveredMessage] = []
        while self._queue and self._queue[0][0] <= float(timestamp) + 1.0e-12:
            _, _, message = heapq.heappop(self._queue)
            delivered.append(message)
            self._delivered_count += 1
            self._delivered_bytes += message.payload_size_bytes
        return tuple(delivered)

    def stats(self) -> CommunicationStats:
        return CommunicationStats(
            sent_count=self._sent_count,
            delivered_count=self._delivered_count,
            dropped_count=self._dropped_count,
            pending_count=len(self._queue),
            sent_bytes=self._sent_bytes,
            delivered_bytes=self._delivered_bytes,
        )

    def reset(self, *, seed: int | None = None) -> None:
        if seed is not None:
            self._base_seed = int(seed)
            self.rng = np.random.default_rng(self._base_seed)
            self._rng_by_stream.clear()
        self._queue.clear()
        self._counter = 0
        self._sent_count = 0
        self._delivered_count = 0
        self._dropped_count = 0
        self._sent_bytes = 0
        self._delivered_bytes = 0
