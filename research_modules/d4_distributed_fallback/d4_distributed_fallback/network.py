"""In-memory simulated network with packet loss and delivery delay."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import NetworkMessage, NetworkStats, to_jsonable


@dataclass
class SimulatedNetwork:
    """Small deterministic network simulator for offline experiments.

    Messages are stored in memory and delivered when the caller advances
    simulated time. No sockets, real frequencies, or hardware APIs are used.
    """

    node_ids: list[str]
    packet_loss: float = 0.0
    min_delay_s: float = 0.1
    max_delay_s: float = 0.5
    seed: int = 7
    _pending: list[NetworkMessage] = field(default_factory=list, init=False)
    _stats: NetworkStats = field(default_factory=NetworkStats, init=False)
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.packet_loss <= 1.0:
            raise ValueError("packet_loss must be in [0, 1]")
        if self.min_delay_s < 0 or self.max_delay_s < self.min_delay_s:
            raise ValueError("invalid delay range")
        self._rng = random.Random(self.seed)

    @property
    def stats(self) -> NetworkStats:
        return self._stats

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def send(
        self,
        sender: str,
        recipient: str,
        kind: str,
        payload: dict[str, Any],
        now_s: float,
        epoch: int,
    ) -> bool:
        if sender == recipient:
            return False
        if recipient not in self.node_ids:
            raise ValueError(f"unknown recipient: {recipient}")
        size_bytes = self._estimate_size(payload)
        self._stats.sent_count += 1
        self._stats.estimated_bytes += size_bytes
        if self._rng.random() < self.packet_loss:
            self._stats.dropped_count += 1
            return False
        delay_s = self._rng.uniform(self.min_delay_s, self.max_delay_s)
        self._pending.append(
            NetworkMessage(
                sender=sender,
                recipient=recipient,
                kind=kind,
                payload=payload,
                epoch=epoch,
                sent_at_s=now_s,
                deliver_at_s=now_s + delay_s,
                size_bytes=size_bytes,
            )
        )
        return True

    def broadcast(
        self,
        sender: str,
        kind: str,
        payload: dict[str, Any],
        now_s: float,
        epoch: int,
        recipients: Iterable[str] | None = None,
    ) -> int:
        targets = list(recipients) if recipients is not None else self.node_ids
        delivered_or_queued = 0
        for recipient in targets:
            if recipient == sender:
                continue
            if self.send(sender, recipient, kind, payload, now_s, epoch):
                delivered_or_queued += 1
        return delivered_or_queued

    def deliver(self, recipient: str, now_s: float) -> list[NetworkMessage]:
        ready: list[NetworkMessage] = []
        remaining: list[NetworkMessage] = []
        for message in self._pending:
            if message.recipient == recipient and message.deliver_at_s <= now_s:
                ready.append(message)
            else:
                remaining.append(message)
        self._pending = remaining
        self._stats.delivered_count += len(ready)
        ready.sort(key=lambda msg: (msg.deliver_at_s, msg.sender, msg.kind))
        return ready

    def drain_due(self, now_s: float) -> dict[str, list[NetworkMessage]]:
        by_node: dict[str, list[NetworkMessage]] = {node_id: [] for node_id in self.node_ids}
        remaining: list[NetworkMessage] = []
        for message in self._pending:
            if message.deliver_at_s <= now_s:
                by_node[message.recipient].append(message)
            else:
                remaining.append(message)
        self._pending = remaining
        delivered = 0
        for messages in by_node.values():
            messages.sort(key=lambda msg: (msg.deliver_at_s, msg.sender, msg.kind))
            delivered += len(messages)
        self._stats.delivered_count += delivered
        return by_node

    @staticmethod
    def _estimate_size(payload: dict[str, Any]) -> int:
        encoded = json.dumps(to_jsonable(payload), sort_keys=True, separators=(",", ":"))
        return len(encoded.encode("utf-8"))
