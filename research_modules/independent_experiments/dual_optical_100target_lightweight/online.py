"""Causal per-revolution inference for the lightweight association routes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Literal, Mapping

import numpy as np

from dual_optical_100target_gnn.dataset import (
    candidate_graph_fingerprint,
    canonical_json_sha256,
)
from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)

from .assignment import assignment_acceptance_mask, solve_probability_assignment
from .models import LightweightModel


SNAPSHOT_SCHEMA_VERSION = "dual-optical-revolution-snapshot-v1"
PUBLICATION_SCHEMA_VERSION = "dual-optical-lightweight-online-publication-v1"
MODEL_BUNDLE_SCHEMA_VERSION = "dual-optical-lightweight-online-model-bundle-v1"
SnapshotMode = Literal["prefix", "cumulative"]
ConfirmationState = Literal["raw", "confirmed"]


def _require_exact_fields(values: Mapping[str, Any], expected: set[str], name: str) -> None:
    missing = expected - set(values)
    unexpected = set(values) - expected
    if missing or unexpected:
        raise ValueError(
            f"invalid {name} fields; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _graph_to_dict(graph: OnlineGraph) -> dict[str, Any]:
    return {
        "seed": graph.seed,
        "corruption_level": graph.corruption_level,
        "camera_ids": list(graph.camera_ids),
        "track_ids_a": list(graph.track_ids_a),
        "track_ids_b": list(graph.track_ids_b),
        "node_features_a": graph.node_features_a.tolist(),
        "node_features_b": graph.node_features_b.tolist(),
        "edge_index": graph.edge_index.tolist(),
        "edge_features": graph.edge_features.tolist(),
        "geometry_cost": graph.geometry_cost.tolist(),
        "corruption_summary": {
            "level": graph.corruption_summary.level,
            "corruption_seed": graph.corruption_summary.corruption_seed,
            "dropped_sample_count": graph.corruption_summary.dropped_sample_count,
            "retained_sample_count": graph.corruption_summary.retained_sample_count,
            "transient_false_track_count": (
                graph.corruption_summary.transient_false_track_count
            ),
            "persistent_false_track_count": (
                graph.corruption_summary.persistent_false_track_count
            ),
        },
    }


def _graph_from_dict(values: Mapping[str, Any]) -> OnlineGraph:
    _require_exact_fields(
        values,
        {
            "seed",
            "corruption_level",
            "camera_ids",
            "track_ids_a",
            "track_ids_b",
            "node_features_a",
            "node_features_b",
            "edge_index",
            "edge_features",
            "geometry_cost",
            "corruption_summary",
        },
        "online graph",
    )
    summary_values = values["corruption_summary"]
    if not isinstance(summary_values, Mapping):
        raise ValueError("corruption_summary must be an object")
    _require_exact_fields(
        summary_values,
        {
            "level",
            "corruption_seed",
            "dropped_sample_count",
            "retained_sample_count",
            "transient_false_track_count",
            "persistent_false_track_count",
        },
        "corruption summary",
    )
    edge_index = np.asarray(values["edge_index"], dtype=np.int64)
    if edge_index.size == 0:
        edge_index = np.empty((2, 0), dtype=np.int64)
    graph = OnlineGraph(
        seed=int(values["seed"]),
        corruption_level=str(values["corruption_level"]),
        camera_ids=tuple(str(value) for value in values["camera_ids"]),  # type: ignore[arg-type]
        track_ids_a=tuple(str(value) for value in values["track_ids_a"]),
        track_ids_b=tuple(str(value) for value in values["track_ids_b"]),
        node_features_a=np.asarray(
            values["node_features_a"], dtype=np.float32
        ).reshape((-1, len(NODE_FEATURE_NAMES))),
        node_features_b=np.asarray(
            values["node_features_b"], dtype=np.float32
        ).reshape((-1, len(NODE_FEATURE_NAMES))),
        edge_index=edge_index,
        edge_features=np.asarray(values["edge_features"], dtype=np.float32).reshape(
            (-1, len(EDGE_FEATURE_NAMES))
        ),
        geometry_cost=np.asarray(values["geometry_cost"], dtype=np.float32),
        corruption_summary=CorruptionSummary(
            level=str(summary_values["level"]),
            corruption_seed=int(summary_values["corruption_seed"]),
            dropped_sample_count=int(summary_values["dropped_sample_count"]),
            retained_sample_count=int(summary_values["retained_sample_count"]),
            transient_false_track_count=int(
                summary_values["transient_false_track_count"]
            ),
            persistent_false_track_count=int(
                summary_values["persistent_false_track_count"]
            ),
        ),
    )
    graph.validate()
    return graph


def snapshot_fingerprint_payload(
    graph: OnlineGraph,
    *,
    revolution_index: int,
    cutoff_timestamp: float,
    observation_max_timestamp: float,
    snapshot_mode: SnapshotMode,
) -> dict[str, Any]:
    """Return the causal metadata and candidate graph covered by the input hash."""

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "seed": graph.seed,
        "corruption_level": graph.corruption_level,
        "revolution_index": revolution_index,
        "cutoff_timestamp": cutoff_timestamp,
        "observation_max_timestamp": observation_max_timestamp,
        "snapshot_mode": snapshot_mode,
        "candidate_graph_fingerprint_sha256": candidate_graph_fingerprint(graph),
    }


@dataclass(frozen=True)
class RevolutionSnapshot:
    """Anonymous candidate graph frozen at the end of one 360-degree revolution."""

    graph: OnlineGraph
    revolution_index: int
    cutoff_timestamp: float
    observation_max_timestamp: float
    snapshot_mode: SnapshotMode
    input_fingerprint_sha256: str

    def __post_init__(self) -> None:
        self.graph.validate()
        if self.revolution_index < 1:
            raise ValueError("revolution_index must be positive")
        if self.snapshot_mode not in {"prefix", "cumulative"}:
            raise ValueError("snapshot_mode must be prefix or cumulative")
        if not math.isfinite(self.cutoff_timestamp) or self.cutoff_timestamp < 0.0:
            raise ValueError("cutoff_timestamp must be finite and nonnegative")
        if not math.isfinite(self.observation_max_timestamp):
            raise ValueError("observation_max_timestamp must be finite")
        if self.observation_max_timestamp > self.cutoff_timestamp + 1.0e-9:
            raise ValueError("snapshot contains an observation after cutoff_timestamp")
        expected = canonical_json_sha256(
            snapshot_fingerprint_payload(
                self.graph,
                revolution_index=self.revolution_index,
                cutoff_timestamp=self.cutoff_timestamp,
                observation_max_timestamp=self.observation_max_timestamp,
                snapshot_mode=self.snapshot_mode,
            )
        )
        if self.input_fingerprint_sha256 != expected:
            raise ValueError("snapshot input fingerprint mismatch")

    @property
    def seed(self) -> int:
        return self.graph.seed

    @property
    def corruption_level(self) -> str:
        return self.graph.corruption_level

    @classmethod
    def from_graph(
        cls,
        graph: OnlineGraph,
        *,
        revolution_index: int,
        cutoff_timestamp: float,
        observation_max_timestamp: float,
        snapshot_mode: SnapshotMode = "cumulative",
    ) -> "RevolutionSnapshot":
        fingerprint = canonical_json_sha256(
            snapshot_fingerprint_payload(
                graph,
                revolution_index=revolution_index,
                cutoff_timestamp=cutoff_timestamp,
                observation_max_timestamp=observation_max_timestamp,
                snapshot_mode=snapshot_mode,
            )
        )
        return cls(
            graph=graph,
            revolution_index=revolution_index,
            cutoff_timestamp=float(cutoff_timestamp),
            observation_max_timestamp=float(observation_max_timestamp),
            snapshot_mode=snapshot_mode,
            input_fingerprint_sha256=fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "revolution_index": self.revolution_index,
            "cutoff_timestamp": self.cutoff_timestamp,
            "observation_max_timestamp": self.observation_max_timestamp,
            "snapshot_mode": self.snapshot_mode,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "graph": _graph_to_dict(self.graph),
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "RevolutionSnapshot":
        _require_exact_fields(
            values,
            {
                "schema_version",
                "revolution_index",
                "cutoff_timestamp",
                "observation_max_timestamp",
                "snapshot_mode",
                "input_fingerprint_sha256",
                "graph",
            },
            "revolution snapshot",
        )
        if values["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported revolution snapshot schema")
        graph_values = values["graph"]
        if not isinstance(graph_values, Mapping):
            raise ValueError("snapshot graph must be an object")
        return cls(
            graph=_graph_from_dict(graph_values),
            revolution_index=int(values["revolution_index"]),
            cutoff_timestamp=float(values["cutoff_timestamp"]),
            observation_max_timestamp=float(values["observation_max_timestamp"]),
            snapshot_mode=str(values["snapshot_mode"]),  # type: ignore[arg-type]
            input_fingerprint_sha256=str(values["input_fingerprint_sha256"]),
        )

    def write_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output

    @classmethod
    def read_json(cls, path: str | Path) -> "RevolutionSnapshot":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class FrozenRoute:
    route_id: str
    model: LightweightModel
    probability_threshold: float
    model_fingerprint_sha256: str
    unmatched_cost: float | None = None

    def __post_init__(self) -> None:
        if self.route_id != self.model.kind:
            raise ValueError("route_id must equal the lightweight model kind")
        if not 0.0 < self.probability_threshold < 1.0:
            raise ValueError("route probability threshold must be in (0, 1)")
        if self.unmatched_cost is not None and (
            not math.isfinite(self.unmatched_cost) or self.unmatched_cost <= 0.0
        ):
            raise ValueError("route unmatched cost must be finite and positive")
        expected = canonical_json_sha256(self.model.to_dict())
        if self.model_fingerprint_sha256 != expected:
            raise ValueError("route model fingerprint mismatch")

    @classmethod
    def create(
        cls,
        model: LightweightModel,
        probability_threshold: float,
        unmatched_cost: float | None = None,
    ) -> "FrozenRoute":
        return cls(
            route_id=model.kind,
            model=model,
            probability_threshold=float(probability_threshold),
            model_fingerprint_sha256=canonical_json_sha256(model.to_dict()),
            unmatched_cost=(
                None if unmatched_cost is None else float(unmatched_cost)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "model_id": self.model.model_id,
            "probability_threshold": self.probability_threshold,
            "model_fingerprint_sha256": self.model_fingerprint_sha256,
            "model": self.model.to_dict(),
            "unmatched_cost": self.unmatched_cost,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "FrozenRoute":
        required = {
                "route_id",
                "model_id",
                "probability_threshold",
                "model_fingerprint_sha256",
                "model",
            }
        allowed = required | {"unmatched_cost"}
        if not required <= set(values) or not set(values) <= allowed:
            raise ValueError("invalid frozen route fields")
        model_values = values["model"]
        if not isinstance(model_values, Mapping):
            raise ValueError("frozen route model must be an object")
        model = LightweightModel.from_dict(model_values)
        if values["model_id"] != model.model_id:
            raise ValueError("frozen route model ID mismatch")
        return cls(
            route_id=str(values["route_id"]),
            model=model,
            probability_threshold=float(values["probability_threshold"]),
            model_fingerprint_sha256=str(values["model_fingerprint_sha256"]),
            unmatched_cost=(
                None
                if values.get("unmatched_cost") is None
                else float(values["unmatched_cost"])
            ),
        )


@dataclass(frozen=True)
class PublishedMatch:
    track_a_id: str
    track_b_id: str
    probability: float
    assignment_cost: float
    confirmation_state: ConfirmationState

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_a_id": self.track_a_id,
            "track_b_id": self.track_b_id,
            "probability": self.probability,
            "assignment_cost": self.assignment_cost,
            "confirmation_state": self.confirmation_state,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "PublishedMatch":
        _require_exact_fields(
            values,
            {
                "track_a_id",
                "track_b_id",
                "probability",
                "assignment_cost",
                "confirmation_state",
            },
            "published match",
        )
        state = str(values["confirmation_state"])
        if state not in {"raw", "confirmed"}:
            raise ValueError("invalid match confirmation state")
        probability = float(values["probability"])
        cost = float(values["assignment_cost"])
        if not 0.0 <= probability <= 1.0 or not math.isfinite(cost):
            raise ValueError("invalid published match score")
        return cls(
            track_a_id=str(values["track_a_id"]),
            track_b_id=str(values["track_b_id"]),
            probability=probability,
            assignment_cost=cost,
            confirmation_state=state,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class OnlineAssociationPublication:
    algorithm: str
    route_id: str
    model_id: str
    model_version: str
    seed: int
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    availability: str
    matches: tuple[PublishedMatch, ...]
    unmatched_track_ids_a: tuple[str, ...]
    unmatched_track_ids_b: tuple[str, ...]
    raw_match_count: int
    confirmed_match_count: int
    rejection_reasons: Mapping[str, int]
    scoring_ms: float
    hungarian_ms: float
    confirmation_ms: float
    end_to_end_ms: float
    latency_budget_ms: float
    latency_budget_met: bool
    input_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.availability not in {
            "available",
            "empty_graph",
            "no_candidates",
            "timeout",
        }:
            raise ValueError("invalid online publication availability")
        if self.revolution_index < 1:
            raise ValueError("publication revolution_index must be positive")
        if not math.isfinite(self.cutoff_timestamp) or self.cutoff_timestamp < 0.0:
            raise ValueError("publication cutoff_timestamp must be finite and nonnegative")
        if len(self.input_fingerprint_sha256) != 64 or any(
            char not in "0123456789abcdef"
            for char in self.input_fingerprint_sha256
        ):
            raise ValueError("publication input fingerprint must be a SHA256 hex digest")
        if not math.isfinite(self.latency_budget_ms) or self.latency_budget_ms <= 0.0:
            raise ValueError("publication latency budget must be finite and positive")
        if self.raw_match_count != sum(
            item.confirmation_state == "raw" for item in self.matches
        ):
            raise ValueError("raw_match_count does not match publications")
        if self.confirmed_match_count != sum(
            item.confirmation_state == "confirmed" for item in self.matches
        ):
            raise ValueError("confirmed_match_count does not match publications")
        latencies = (
            self.scoring_ms,
            self.hungarian_ms,
            self.confirmation_ms,
            self.end_to_end_ms,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in latencies):
            raise ValueError("online publication latencies must be finite and nonnegative")
        if self.latency_budget_met != (self.end_to_end_ms <= self.latency_budget_ms):
            raise ValueError("latency budget status is inconsistent")
        if self.availability == "timeout" and self.matches:
            raise ValueError("timed-out publications cannot contain matches")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLICATION_SCHEMA_VERSION,
            "algorithm": self.algorithm,
            "route_id": self.route_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "seed": self.seed,
            "corruption_level": self.corruption_level,
            "revolution_index": self.revolution_index,
            "cutoff_timestamp": self.cutoff_timestamp,
            "availability": self.availability,
            "matches": [item.to_dict() for item in self.matches],
            "unmatched_track_ids_a": list(self.unmatched_track_ids_a),
            "unmatched_track_ids_b": list(self.unmatched_track_ids_b),
            "raw_match_count": self.raw_match_count,
            "confirmed_match_count": self.confirmed_match_count,
            "rejection_reasons": dict(self.rejection_reasons),
            "scoring_ms": self.scoring_ms,
            "hungarian_ms": self.hungarian_ms,
            "confirmation_ms": self.confirmation_ms,
            "end_to_end_ms": self.end_to_end_ms,
            "latency_budget_ms": self.latency_budget_ms,
            "latency_budget_met": self.latency_budget_met,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "OnlineAssociationPublication":
        expected = {
            "schema_version",
            "algorithm",
            "route_id",
            "model_id",
            "model_version",
            "seed",
            "corruption_level",
            "revolution_index",
            "cutoff_timestamp",
            "availability",
            "matches",
            "unmatched_track_ids_a",
            "unmatched_track_ids_b",
            "raw_match_count",
            "confirmed_match_count",
            "rejection_reasons",
            "scoring_ms",
            "hungarian_ms",
            "confirmation_ms",
            "end_to_end_ms",
            "latency_budget_ms",
            "latency_budget_met",
            "input_fingerprint_sha256",
        }
        _require_exact_fields(values, expected, "online publication")
        if values["schema_version"] != PUBLICATION_SCHEMA_VERSION:
            raise ValueError("unsupported online publication schema")
        return cls(
            algorithm=str(values["algorithm"]),
            route_id=str(values["route_id"]),
            model_id=str(values["model_id"]),
            model_version=str(values["model_version"]),
            seed=int(values["seed"]),
            corruption_level=str(values["corruption_level"]),
            revolution_index=int(values["revolution_index"]),
            cutoff_timestamp=float(values["cutoff_timestamp"]),
            availability=str(values["availability"]),
            matches=tuple(PublishedMatch.from_dict(item) for item in values["matches"]),
            unmatched_track_ids_a=tuple(
                str(item) for item in values["unmatched_track_ids_a"]
            ),
            unmatched_track_ids_b=tuple(
                str(item) for item in values["unmatched_track_ids_b"]
            ),
            raw_match_count=int(values["raw_match_count"]),
            confirmed_match_count=int(values["confirmed_match_count"]),
            rejection_reasons={
                str(key): int(value)
                for key, value in values["rejection_reasons"].items()
            },
            scoring_ms=float(values["scoring_ms"]),
            hungarian_ms=float(values["hungarian_ms"]),
            confirmation_ms=float(values["confirmation_ms"]),
            end_to_end_ms=float(values["end_to_end_ms"]),
            latency_budget_ms=float(values["latency_budget_ms"]),
            latency_budget_met=bool(values["latency_budget_met"]),
            input_fingerprint_sha256=str(values["input_fingerprint_sha256"]),
        )


class OnlineLightweightAdapter:
    """Run every frozen lightweight route on identical causal candidate edges."""

    def __init__(
        self,
        routes: Iterable[FrozenRoute],
        geometry_gate: Mapping[str, Any],
        *,
        allowed_seeds: Iterable[int] | None = None,
        confirmation_window_revolutions: int = 3,
        confirmation_hits: int = 2,
        latency_budget_ms: float = 1000.0,
    ) -> None:
        route_values = tuple(routes)
        if not route_values:
            raise ValueError("at least one frozen lightweight route is required")
        if len({item.route_id for item in route_values}) != len(route_values):
            raise ValueError("frozen route IDs must be unique")
        if confirmation_window_revolutions < 1:
            raise ValueError("confirmation window must be positive")
        if not 1 <= confirmation_hits <= confirmation_window_revolutions:
            raise ValueError("confirmation hits must fit the confirmation window")
        if not math.isfinite(latency_budget_ms) or latency_budget_ms <= 0.0:
            raise ValueError("latency_budget_ms must be finite and positive")
        self.routes = route_values
        self.geometry_gate = dict(geometry_gate)
        self.allowed_seeds = (
            frozenset(int(value) for value in allowed_seeds)
            if allowed_seeds is not None
            else None
        )
        self.confirmation_window_revolutions = confirmation_window_revolutions
        self.confirmation_hits = confirmation_hits
        self.latency_budget_ms = float(latency_budget_ms)
        self._last_snapshot: dict[tuple[int, str], tuple[int, float]] = {}
        self._pair_history: dict[
            tuple[str, int, str], list[set[tuple[str, str]]]
        ] = {}

    def reset(self, seed: int | None = None, corruption_level: str | None = None) -> None:
        """Clear confirmation history for one scenario or for the whole adapter."""

        if seed is None and corruption_level is None:
            self._last_snapshot.clear()
            self._pair_history.clear()
            return
        if seed is None or corruption_level is None:
            raise ValueError("seed and corruption_level must be provided together")
        scenario = (int(seed), str(corruption_level))
        self._last_snapshot.pop(scenario, None)
        for route in self.routes:
            self._pair_history.pop((route.route_id, *scenario), None)

    def _validate_sequence(self, snapshot: RevolutionSnapshot) -> bool:
        if self.allowed_seeds is not None and snapshot.seed not in self.allowed_seeds:
            raise ValueError("snapshot seed is not in the frozen reserved-test split")
        scenario = (snapshot.seed, snapshot.corruption_level)
        previous = self._last_snapshot.get(scenario)
        if previous is not None:
            previous_index, previous_cutoff = previous
            if snapshot.revolution_index <= previous_index:
                raise ValueError("revolution snapshots must be processed in increasing order")
            if snapshot.cutoff_timestamp <= previous_cutoff:
                raise ValueError("snapshot cutoff timestamps must be strictly increasing")
            consecutive = snapshot.revolution_index == previous_index + 1
        else:
            consecutive = False
        self._last_snapshot[scenario] = (
            snapshot.revolution_index,
            snapshot.cutoff_timestamp,
        )
        return consecutive

    def process(
        self,
        snapshot: RevolutionSnapshot,
        *,
        upstream_elapsed_ms: float = 0.0,
    ) -> tuple[OnlineAssociationPublication, ...]:
        """Publish all routes without consulting truth labels or future observations."""

        if not math.isfinite(upstream_elapsed_ms) or upstream_elapsed_ms < 0.0:
            raise ValueError("upstream_elapsed_ms must be finite and nonnegative")
        consecutive = self._validate_sequence(snapshot)
        graph = snapshot.graph
        if not graph.track_ids_a or not graph.track_ids_b:
            availability = "empty_graph"
        elif graph.edge_index.shape[1] == 0:
            availability = "no_candidates"
        else:
            availability = "available"

        publications = []
        for route in self.routes:
            started_ns = time.perf_counter_ns()
            scoring_started_ns = started_ns
            probabilities = route.model.predict_proba(graph, self.geometry_gate)
            scoring_finished_ns = time.perf_counter_ns()
            assignment = solve_probability_assignment(
                graph,
                probabilities,
                route.probability_threshold,
                route.unmatched_cost,
            )
            assignment_finished_ns = time.perf_counter_ns()

            selected_pairs = {
                (graph.track_ids_a[item.index_a], graph.track_ids_b[item.index_b]): item
                for item in assignment.selected_pairs
            }
            history_key = (route.route_id, snapshot.seed, snapshot.corruption_level)
            confirmation_started_ns = assignment_finished_ns
            history = (
                list(self._pair_history.get(history_key, ()))
                if consecutive
                else []
            )
            publishable_from_this_revolution = snapshot.revolution_index >= 2
            proposed_history = list(history)
            proposed_history.append(set(selected_pairs))
            proposed_history = proposed_history[
                -self.confirmation_window_revolutions :
            ]

            proposed_matches = []
            if publishable_from_this_revolution:
                for pair, selected in sorted(selected_pairs.items()):
                    state: ConfirmationState = (
                        "confirmed"
                        if snapshot.revolution_index >= 3
                        and sum(pair in observed for observed in proposed_history)
                        >= self.confirmation_hits
                        else "raw"
                    )
                    proposed_matches.append(
                        PublishedMatch(
                            track_a_id=pair[0],
                            track_b_id=pair[1],
                            probability=float(probabilities[selected.edge_index]),
                            assignment_cost=float(selected.cost),
                            confirmation_state=state,
                        )
                    )

            effective_unmatched_cost = (
                -math.log(route.probability_threshold)
                if route.unmatched_cost is None
                else route.unmatched_cost
            )
            accepted_edge_count = int(
                np.sum(
                    assignment_acceptance_mask(
                        probabilities,
                        route.probability_threshold,
                        effective_unmatched_cost,
                    )
                )
            )
            confirmation_finished_ns = time.perf_counter_ns()
            scoring_ms = (scoring_finished_ns - scoring_started_ns) / 1.0e6
            hungarian_ms = (assignment_finished_ns - scoring_finished_ns) / 1.0e6
            confirmation_ms = (
                confirmation_finished_ns - confirmation_started_ns
            ) / 1.0e6
            end_to_end_ms = (
                upstream_elapsed_ms
                + (confirmation_finished_ns - started_ns) / 1.0e6
            )
            deadline_met = end_to_end_ms <= self.latency_budget_ms
            if deadline_met:
                self._pair_history[history_key] = proposed_history
            matches = proposed_matches if deadline_met else []
            publication_availability = availability if deadline_met else "timeout"

            rejection_reasons = {
                "candidate_edge_count": int(graph.edge_index.shape[1]),
                "probability_accepted_edge_count": accepted_edge_count,
                "hungarian_selected_count": len(selected_pairs),
                "below_probability_threshold": int(
                    len(probabilities) - accepted_edge_count
                ),
                "assignment_conflict_or_higher_cost": max(
                    accepted_edge_count - len(selected_pairs), 0
                ),
                "unmatched_a": len(assignment.unmatched_a),
                "unmatched_b": len(assignment.unmatched_b),
                "awaiting_two_of_three_confirmation": sum(
                    item.confirmation_state == "raw" for item in proposed_matches
                ),
                "confirmed_match_count_before_deadline": sum(
                    item.confirmation_state == "confirmed"
                    for item in proposed_matches
                ),
                "suppressed_before_second_revolution": (
                    len(selected_pairs) if not publishable_from_this_revolution else 0
                ),
                "suppressed_by_deadline": (
                    len(proposed_matches) if not deadline_met else 0
                ),
            }
            if availability != "available":
                rejection_reasons[availability] = 1
            if not deadline_met:
                rejection_reasons["deadline_exceeded"] = 1

            publications.append(
                OnlineAssociationPublication(
                    algorithm="dual_optical_lightweight",
                    route_id=route.route_id,
                    model_id=route.model.model_id,
                    model_version=route.model_fingerprint_sha256,
                    seed=snapshot.seed,
                    corruption_level=snapshot.corruption_level,
                    revolution_index=snapshot.revolution_index,
                    cutoff_timestamp=snapshot.cutoff_timestamp,
                    availability=publication_availability,
                    matches=tuple(matches),
                    unmatched_track_ids_a=tuple(
                        graph.track_ids_a[index] for index in assignment.unmatched_a
                    ),
                    unmatched_track_ids_b=tuple(
                        graph.track_ids_b[index] for index in assignment.unmatched_b
                    ),
                    raw_match_count=sum(
                        item.confirmation_state == "raw" for item in matches
                    ),
                    confirmed_match_count=sum(
                        item.confirmation_state == "confirmed" for item in matches
                    ),
                    rejection_reasons=rejection_reasons,
                    scoring_ms=scoring_ms,
                    hungarian_ms=hungarian_ms,
                    confirmation_ms=confirmation_ms,
                    end_to_end_ms=end_to_end_ms,
                    latency_budget_ms=self.latency_budget_ms,
                    latency_budget_met=deadline_met,
                    input_fingerprint_sha256=snapshot.input_fingerprint_sha256,
                )
            )
        return tuple(publications)
