"""Causal one-snapshot inference adapter for the main-owned benchmark contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Literal, Mapping

import numpy as np
import torch

from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
    RevolutionSnapshot,
    snapshot_fingerprint,
)

from .assignment import solve_assignment
from .graph import GeometryGate, build_online_graph
from .model import BipartiteEdgeGNN, FeatureNormalizer, graph_tensors, load_weights_only
from .schema import (
    EDGE_FEATURE_NAMES,
    AnonymousTrack,
    CorruptionSummary,
    OnlineEpisode,
    TrackSample,
)
from .training import verify_freeze_manifest


ONLINE_ROUTE_VERSION = "dual-optical-edge-gnn-online-v2"
ConfirmationStrategy = Literal[
    "legacy_strict",
    "early_repeat",
    "graded",
    "direct_1of1_diagnostic",
]
CONFIRMATION_STRATEGIES: tuple[ConfirmationStrategy, ...] = (
    "legacy_strict",
    "early_repeat",
    "graded",
    "direct_1of1_diagnostic",
)
GRADED_PROBABILITY_THRESHOLDS = (0.7, 0.8, 0.9)
GRADED_MARGIN_THRESHOLDS = (0.10, 0.20)
GRADED_MAX_NORMALIZED_COPLANARITY_RESIDUAL = 4.0
_MISSING = object()


def _field(value: Any, *names: str, default: Any = _MISSING) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    if default is _MISSING:
        raise AttributeError(f"missing required field aliases: {names}")
    return default


def _optional_tuple(value: Any, *names: str) -> tuple[float, ...] | None:
    raw = _field(value, *names, default=None)
    if raw is None:
        return None
    array = np.asarray(raw, dtype=float)
    if array.ndim == 2:
        array = array.reshape(-1)
    return tuple(float(item) for item in array)


def _snapshot_contract(snapshot: RevolutionSnapshot) -> str:
    tracker_fingerprint = str(
        _field(snapshot, "tracker_fingerprint", default="legacy-unfrozen-tracker")
    )
    if tracker_fingerprint == "legacy-unfrozen-tracker":
        return "v1"
    return "v2"


def _candidate_pairs(snapshot: RevolutionSnapshot) -> tuple[tuple[str, str], ...] | None:
    raw = _field(
        snapshot,
        "geometry_candidate_pairs",
        "geometry_candidates",
        "geometry_candidate_edges",
        "candidate_edges",
        default=None,
    )
    if raw is None:
        return None
    # A pre-whitelist v2 snapshot is restored by the new main dataclass with
    # empty defaults. Only a non-empty graph fingerprint makes an empty tuple
    # an authoritative, fail-closed whitelist.
    fingerprint = _field(
        snapshot,
        "candidate_graph_fingerprint",
        "candidate_graph_fingerprint_sha256",
        "geometry_candidate_fingerprint",
        default=None,
    )
    if not raw and not fingerprint:
        return None
    pairs = []
    for item in raw:
        if isinstance(item, Mapping) or hasattr(item, "track_a_id"):
            track_a = str(_field(item, "track_a_id", "track_id_a"))
            track_b = str(_field(item, "track_b_id", "track_id_b"))
        else:
            track_a, track_b = (str(value) for value in item)
        pairs.append((track_a, track_b))
    return tuple(pairs)


def _candidate_graph_fingerprint(snapshot: RevolutionSnapshot) -> str | None:
    value = _field(
        snapshot,
        "candidate_graph_fingerprint",
        "candidate_graph_fingerprint_sha256",
        "geometry_candidate_fingerprint",
        default=None,
    )
    if value is None or str(value) == "":
        return None
    fingerprint = str(value).lower()
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise ValueError("snapshot candidate graph fingerprint is not SHA-256")
    return fingerprint


def _snapshot_target_count(snapshot: RevolutionSnapshot) -> int | None:
    value = _field(snapshot, "target_count", default=None)
    if value is None:
        value = _field(
            snapshot,
            "configured_target_count",
            "scenario_target_count",
            default=None,
        )
    if value is None:
        return None
    target_count = int(value)
    if target_count <= 0 or float(value) != float(target_count):
        raise ValueError("snapshot target_count must be a positive integer")
    return target_count


def _has_any_field(value: Any, names: tuple[str, ...]) -> bool:
    return any(
        (isinstance(value, Mapping) and name in value) or hasattr(value, name)
        for name in names
    )


def _effective_snapshot_contract(
    snapshot: RevolutionSnapshot,
    declared_contract: str,
    candidate_pairs: tuple[tuple[str, str], ...] | None,
) -> tuple[str, tuple[str, ...]]:
    if declared_contract != "v2":
        return "v1", ()
    missing: set[str] = set()
    for camera_id in snapshot.camera_ids:
        for track in snapshot.tracks[camera_id]:
            requirements = {
                "recent_hits": (
                    "recent_sweep_hits",
                    "recent_revolution_hits",
                    "recent_three_hits",
                    "hit_history",
                ),
                "track_state": ("track_state", "state"),
            }
            for label, aliases in requirements.items():
                if not _has_any_field(track, aliases):
                    missing.add(label)
    if missing:
        return "v1_fallback_from_v2", tuple(sorted(missing))
    return "v2", ()


def _v2_sample_state(track: Any) -> tuple[tuple[float, float] | None, tuple[float, ...] | None]:
    samples = tuple(_field(track, "samples", default=()))
    if not samples:
        return None, None
    latest = samples[-1]
    state = _field(latest, "state_vector", default=None)
    covariance = _field(latest, "state_covariance", default=None)
    velocity = None
    converted_covariance = None
    if state is not None and len(state) == 4:
        velocity = (float(state[2]), float(state[3]))
    if covariance is not None:
        matrix = np.asarray(covariance, dtype=float).reshape(4, 4)
        degrees_to_mrad = np.deg2rad(1.0) * 1000.0
        transform = np.diag((degrees_to_mrad, degrees_to_mrad, 1.0, 1.0))
        matrix = transform @ matrix @ transform.T
        converted_covariance = tuple(float(value) for value in matrix.reshape(-1))
    return velocity, converted_covariance


def _measurement_covariance_mrad2(sample: Any) -> tuple[float, ...] | None:
    covariance = _field(
        sample,
        "measurement_covariance_deg2",
        default=None,
    )
    if covariance is not None:
        factor = (np.deg2rad(1.0) * 1000.0) ** 2
        return tuple(float(value) * factor for value in covariance)
    return _optional_tuple(
        sample,
        "direction_covariance_mrad2",
        "bearing_covariance_mrad2",
        "measurement_covariance_mrad2",
    )


def _summary_count(values: Any, name: str, *aliases: str) -> int:
    value = values.get(name, 0)
    if name not in values:
        for alias in aliases:
            if alias in values:
                value = values[alias]
                break
    return int(float(value))


def anonymous_graph_from_snapshot(
    snapshot: RevolutionSnapshot,
    gate: GeometryGate,
) -> tuple[Any, dict[str, int]]:
    """Build the graph consumed by both calibration and online publication."""

    declared_contract = _snapshot_contract(snapshot)
    candidate_pairs = _candidate_pairs(snapshot)
    candidate_fingerprint = _candidate_graph_fingerprint(snapshot)
    target_count = _snapshot_target_count(snapshot)
    contract_version, missing_v2_fields = _effective_snapshot_contract(
        snapshot, declared_contract, candidate_pairs
    )
    tracks: dict[str, tuple[AnonymousTrack, ...]] = {}
    for camera_id in snapshot.camera_ids:
        converted = []
        for track in snapshot.tracks[camera_id]:
            sample_velocity, sample_covariance = _v2_sample_state(track)
            samples = tuple(
                TrackSample(
                    sweep_index=sample.sweep_index,
                    timestamp=sample.timestamp,
                    direction_ned=sample.direction_ned,
                    detection_count=sample.detection_count,
                    bbox_area_px2=sample.bbox_area_px2,
                    confidence=sample.confidence,
                    direction_covariance_mrad2=_measurement_covariance_mrad2(sample),
                )
                for sample in track.samples
            )
            converted.append(
                AnonymousTrack(
                    track_id=track.track_id,
                    camera_id=track.camera_id,
                    samples=samples,
                    source_kind="anonymous",
                    angular_velocity_deg_s=sample_velocity or (
                        tuple(
                            float(value)
                            for value in _field(
                                track,
                                "angular_velocity_deg_s",
                                "angular_rate_deg_s",
                                default=(),
                            )
                        )
                        or None
                    ),
                    state_covariance=sample_covariance or _optional_tuple(
                        track,
                        "state_covariance",
                        "track_state_covariance",
                        "covariance",
                    ),
                    recent_revolution_hits=tuple(
                        bool(value)
                        for value in _field(
                            track,
                            "recent_sweep_hits",
                            "recent_revolution_hits",
                            "recent_three_hits",
                            "hit_history",
                            default=(),
                        )
                    )[-3:],
                    track_state=str(
                        _field(
                            track,
                            "track_state",
                            "state",
                            default="legacy_v1" if contract_version == "v1" else "unknown",
                        )
                    ),
                    snapshot_contract_version=contract_version,
                )
            )
        tracks[camera_id] = tuple(converted)
    episode = OnlineEpisode(
        seed=snapshot.seed,
        schema_version=f"dual-optical-online-benchmark-{contract_version}",
        configured_target_count=target_count,
        camera_ids=snapshot.camera_ids,
        camera_positions_ned=snapshot.camera_positions_ned,
        focal_length_px=snapshot.focal_length_px,
        tracks=tracks,
        source_hashes=snapshot.source_hashes,
        snapshot_contract_version=contract_version,
        geometry_candidate_pairs=(
            candidate_pairs if contract_version == "v2" else None
        ),
        candidate_graph_fingerprint=candidate_fingerprint,
    )
    summary = CorruptionSummary(
        level=snapshot.corruption_level,
        corruption_seed=_summary_count(
            snapshot.corruption_summary, "corruption_seed"
        ),
        dropped_sample_count=_summary_count(
            snapshot.corruption_summary,
            "dropped_sample_count",
            "dropped_detection_count",
        ),
        retained_sample_count=_summary_count(
            snapshot.corruption_summary,
            "retained_sample_count",
            "retained_real_detection_count",
        ),
        transient_false_track_count=_summary_count(
            snapshot.corruption_summary, "transient_false_track_count"
        ),
        persistent_false_track_count=_summary_count(
            snapshot.corruption_summary, "persistent_false_track_count"
        ),
    )
    graph, diagnostics = build_online_graph(episode, summary, gate=gate)
    diagnostics["snapshot_contract_version"] = contract_version
    diagnostics["snapshot_declared_contract_version"] = declared_contract
    diagnostics["snapshot_v1_fallback"] = int(contract_version != "v2")
    diagnostics["snapshot_v2_missing_field_count"] = len(missing_v2_fields)
    diagnostics["snapshot_v2_missing_fields"] = "|".join(missing_v2_fields)
    diagnostics["snapshot_target_count"] = target_count if target_count is not None else -1
    diagnostics["snapshot_target_count_missing"] = int(target_count is None)
    diagnostics["candidate_graph_fingerprint"] = candidate_fingerprint or ""
    diagnostics["candidate_graph_fingerprint_missing"] = int(
        candidate_fingerprint is None
    )
    return graph, diagnostics


@dataclass(frozen=True)
class OnlineInferenceResult:
    """Public main-compatible publication plus explicit route diagnostics."""

    publication: AssociationPublication
    raw_matches: tuple[AssociationMatch, ...]
    tentative_matches: tuple[AssociationMatch, ...]
    fast_confirmed_matches: tuple[AssociationMatch, ...]
    confirmed_matches: tuple[AssociationMatch, ...]
    rejection_reasons: dict[str, int]
    inference_backend: str
    gpu_inference_ms: float | None
    cpu_inference_ms: float | None
    model_fingerprint_sha256: str
    input_fingerprint_sha256: str
    snapshot_contract_version: str
    snapshot_v1_fallback: bool
    target_count: int | None
    candidate_graph_fingerprint_sha256: str | None
    stage_latency_ms: Mapping[str, float]
    confirmation_strategy: ConfirmationStrategy
    diagnostic_mode: bool
    route_version: str


class OnlineGNNAssociator:
    """Consume one cumulative revolution snapshot; never load labels or future data."""

    def __init__(
        self,
        freeze_manifest: str,
        *,
        device: str = "auto",
        confirmation_revolutions: int | None = None,
        confirmation_window: int = 3,
        confirmation_hits: int = 2,
        confirmation_strategy: ConfirmationStrategy = "legacy_strict",
        graded_probability_threshold: float | None = None,
        graded_margin: float | None = None,
        diagnostic_mode: bool = False,
        geometry_gate: GeometryGate | None = None,
    ) -> None:
        if confirmation_revolutions is not None:
            confirmation_hits = int(confirmation_revolutions)
        if confirmation_window != 3 or confirmation_hits != 2:
            raise ValueError("online publication requires two hits in the latest three revolutions")
        if confirmation_strategy not in CONFIRMATION_STRATEGIES:
            raise ValueError(f"unsupported confirmation strategy: {confirmation_strategy}")
        if confirmation_strategy == "graded":
            if graded_probability_threshold not in GRADED_PROBABILITY_THRESHOLDS:
                raise ValueError(
                    "graded confirmation requires an explicit probability threshold "
                    "from 0.7, 0.8, or 0.9"
                )
            if graded_margin not in GRADED_MARGIN_THRESHOLDS:
                raise ValueError(
                    "graded confirmation requires an explicit margin from 0.10 or 0.20"
                )
        elif graded_probability_threshold is not None or graded_margin is not None:
            raise ValueError("graded thresholds are only valid for the graded strategy")
        if confirmation_strategy == "direct_1of1_diagnostic" and not diagnostic_mode:
            raise ValueError(
                "direct_1of1_diagnostic requires diagnostic_mode=True"
            )
        if confirmation_strategy != "direct_1of1_diagnostic" and diagnostic_mode:
            raise ValueError(
                "diagnostic_mode is reserved for direct_1of1_diagnostic"
            )
        freeze, root = verify_freeze_manifest(freeze_manifest)
        requested = (
            "cuda"
            if device == "auto" and torch.cuda.is_available()
            else "cpu"
            if device == "auto"
            else device
        )
        runtime_device = torch.device(requested)
        if runtime_device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        config = json.loads((root / freeze["model_config"]).read_text(encoding="utf-8"))
        model = BipartiteEdgeGNN(
            int(config["node_feature_dim"]),
            int(config["edge_feature_dim"]),
            hidden_dim=int(config["hidden_dim"]),
            dropout=float(config["dropout"]),
        ).to(runtime_device)
        load_weights_only(model, root / freeze["weights"], map_location=runtime_device)
        model.eval()
        self._model = model
        self._normalizer = FeatureNormalizer.load(root / freeze["normalizer"])
        self._device = runtime_device
        self._freeze = freeze
        self._confirmation_window = int(confirmation_window)
        self._confirmation_hits = int(confirmation_hits)
        self._confirmation_strategy = confirmation_strategy
        self._graded_probability_threshold = graded_probability_threshold
        self._graded_margin = graded_margin
        self._diagnostic_mode = bool(diagnostic_mode)
        frozen_gate = GeometryGate(**dict(freeze.get("geometry_gate", {})))
        if geometry_gate is not None and geometry_gate != frozen_gate:
            raise ValueError("online geometry gate must match the frozen training gate")
        self._geometry_gate = frozen_gate
        self._histories: dict[tuple[int, str, str, str], list[tuple[int, bool]]] = {}
        self._last_revolution: dict[tuple[int, str], int] = {}

    @property
    def model_fingerprint(self) -> str:
        return str(self._freeze["model_fingerprint_sha256"])

    @property
    def inference_backend(self) -> str:
        return "gpu" if self._device.type == "cuda" else "cpu_fallback"

    @property
    def runtime_device(self) -> str:
        return str(self._device)

    @property
    def confirmation_strategy(self) -> ConfirmationStrategy:
        return self._confirmation_strategy

    @property
    def diagnostic_mode(self) -> bool:
        return self._diagnostic_mode

    @property
    def route_version(self) -> str:
        if self._confirmation_strategy == "legacy_strict":
            return ONLINE_ROUTE_VERSION
        if self._confirmation_strategy == "direct_1of1_diagnostic":
            return f"{ONLINE_ROUTE_VERSION}-direct-1of1-diagnostic"
        return (
            f"{ONLINE_ROUTE_VERSION}-confirmation-ablation-"
            f"{self._confirmation_strategy.replace('_', '-')}"
        )

    def _graded_fast_confirmation_keys(
        self,
        snapshot: RevolutionSnapshot,
        graph: Any,
        probabilities: np.ndarray,
        selected: Mapping[tuple[str, str], Any],
    ) -> set[tuple[str, str]]:
        if self._confirmation_strategy != "graded":
            return set()
        residual_index = EDGE_FEATURE_NAMES.index(
            "normalized_coplanarity_residual"
        )
        if graph.edge_features.shape[1] <= residual_index:
            return set()

        camera_a, camera_b = snapshot.camera_ids
        states_a = {
            str(_field(track, "track_id")): str(
                _field(track, "track_state", "state", default="")
            ).strip().lower()
            for track in snapshot.tracks[camera_a]
        }
        states_b = {
            str(_field(track, "track_id")): str(
                _field(track, "track_state", "state", default="")
            ).strip().lower()
            for track in snapshot.tracks[camera_b]
        }
        allowed_states = {"confirmed", "coasting"}
        by_a: dict[int, list[tuple[int, float]]] = {}
        by_b: dict[int, list[tuple[int, float]]] = {}
        for edge_id, (index_a, index_b) in enumerate(graph.edge_index.T):
            probability = float(probabilities[edge_id])
            by_a.setdefault(int(index_a), []).append((edge_id, probability))
            by_b.setdefault(int(index_b), []).append((edge_id, probability))

        threshold = float(self._graded_probability_threshold)
        required_margin = float(self._graded_margin)
        fast: set[tuple[str, str]] = set()
        for (track_a, track_b), item in selected.items():
            edge_id = int(item.edge_index)
            probability = float(probabilities[edge_id])
            alternatives_a = [
                score for other_edge, score in by_a[int(item.index_a)]
                if other_edge != edge_id
            ]
            alternatives_b = [
                score for other_edge, score in by_b[int(item.index_b)]
                if other_edge != edge_id
            ]
            second_a = max(alternatives_a, default=float("-inf"))
            second_b = max(alternatives_b, default=float("-inf"))
            top_a = max(score for _, score in by_a[int(item.index_a)])
            top_b = max(score for _, score in by_b[int(item.index_b)])
            residual = float(graph.edge_features[edge_id, residual_index])
            if (
                states_a.get(track_a) in allowed_states
                and states_b.get(track_b) in allowed_states
                and probability >= threshold
                and probability >= top_a
                and probability >= top_b
                and probability - second_a >= required_margin
                and probability - second_b >= required_margin
                and residual <= GRADED_MAX_NORMALIZED_COPLANARITY_RESIDUAL
            ):
                fast.add((track_a, track_b))
        return fast

    def _probabilities(self, graph: Any) -> tuple[np.ndarray, float, float]:
        if graph.edge_index.shape[1] == 0:
            return np.empty(0, dtype=np.float32), 0.0, 0.0
        tensor_start = time.perf_counter()
        tensors = graph_tensors(graph, self._normalizer, self._device)
        tensor_ms = (time.perf_counter() - tensor_start) * 1000.0
        if self._device.type == "cuda":
            torch.cuda.synchronize(self._device)
        start = time.perf_counter()
        with torch.no_grad():
            probabilities = torch.sigmoid(self._model(*tensors))
        if self._device.type == "cuda":
            torch.cuda.synchronize(self._device)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return (
            probabilities.detach().cpu().numpy().astype(np.float32),
            tensor_ms,
            elapsed_ms,
        )

    def associate(self, snapshot: RevolutionSnapshot) -> OnlineInferenceResult:
        """Associate one prefix. The caller owns persistence and deadline handling."""

        end_to_end_start = time.perf_counter()
        expected_protocol = self._freeze.get("protocol_fingerprint_sha256")
        if expected_protocol and snapshot.protocol_fingerprint != expected_protocol:
            raise ValueError("snapshot protocol fingerprint does not match frozen route")
        target_count = _snapshot_target_count(snapshot)
        frozen_target_count = self._freeze.get("target_count")
        if (
            frozen_target_count is not None
            and target_count is not None
            and int(frozen_target_count) != target_count
        ):
            raise ValueError("snapshot target_count does not match frozen route")
        if target_count is None and frozen_target_count is not None:
            target_count = int(frozen_target_count)
        prefix = (snapshot.seed, snapshot.corruption_level)
        previous_revolution = self._last_revolution.get(prefix, 0)
        if snapshot.revolution_index <= previous_revolution:
            raise ValueError("snapshot revolution must advance monotonically")
        input_fingerprint = snapshot_fingerprint(snapshot)
        candidate_start = time.perf_counter()
        graph, diagnostics = anonymous_graph_from_snapshot(
            snapshot, self._geometry_gate
        )
        confirmation_graph = graph
        candidate_build_ms = (time.perf_counter() - candidate_start) * 1000.0
        expected_node_dim = int(self._model.node_encoder[0].in_features)
        expected_edge_dim = int(self._model.edge_encoder[0].in_features)
        if graph.node_features_a.shape[1] < expected_node_dim or graph.edge_features.shape[1] < expected_edge_dim:
            raise ValueError("snapshot feature contract is older than the frozen model")
        if graph.node_features_a.shape[1] != expected_node_dim or graph.edge_features.shape[1] != expected_edge_dim:
            from dataclasses import replace

            graph = replace(
                graph,
                node_features_a=graph.node_features_a[:, :expected_node_dim],
                node_features_b=graph.node_features_b[:, :expected_node_dim],
                edge_features=graph.edge_features[:, :expected_edge_dim],
            )
            graph.validate()
        probability_result = self._probabilities(graph)
        if len(probability_result) == 2:
            # Compatibility for route-local test doubles and pre-v3 adapters.
            probabilities, scoring_ms = probability_result
            tensor_preparation_ms = 0.0
        else:
            probabilities, tensor_preparation_ms, scoring_ms = probability_result
        assignment_start = time.perf_counter()
        if graph.edge_index.shape[1]:
            assignment = solve_assignment(
                graph,
                probabilities,
                str(self._freeze["selected_route"]),  # type: ignore[arg-type]
                unmatched_cost=float(self._freeze["selected_unmatched_cost"]),
            )
            selected_pairs = assignment.selected_pairs
        else:
            selected_pairs = ()
        hungarian_ms = (time.perf_counter() - assignment_start) * 1000.0

        selected = {
            (graph.track_ids_a[item.index_a], graph.track_ids_b[item.index_b]): item
            for item in selected_pairs
        }
        raw_matches = tuple(
            AssociationMatch(
                track_a_id=track_a,
                track_b_id=track_b,
                score=float(probabilities[item.edge_index]),
                decision_state="raw",
            )
            for (track_a, track_b), item in sorted(selected.items())
        )
        confirmation_start = time.perf_counter()
        confirmed = []
        fast_confirmed = []
        graded_fast_keys = self._graded_fast_confirmation_keys(
            snapshot,
            confirmation_graph,
            probabilities,
            selected,
        )
        prefix_keys = [key for key in self._histories if key[:2] == prefix]
        for key in prefix_keys:
            history = self._histories[key]
            last_revolution = history[-1][0] if history else 0
            for revolution in range(last_revolution + 1, snapshot.revolution_index):
                history.append((revolution, False))
            history.append((snapshot.revolution_index, False))
            self._histories[key] = history[-self._confirmation_window :]
        for match in raw_matches:
            key = (*prefix, match.track_a_id, match.track_b_id)
            history = self._histories.get(key, [])
            if history and history[-1][0] == snapshot.revolution_index:
                history[-1] = (snapshot.revolution_index, True)
            else:
                history.append((snapshot.revolution_index, True))
            history = history[-self._confirmation_window :]
            self._histories[key] = history
            pair = (match.track_a_id, match.track_b_id)
            decision_state = None
            if self._confirmation_strategy == "direct_1of1_diagnostic":
                decision_state = "diagnostic_direct"
            elif self._confirmation_strategy == "graded" and pair in graded_fast_keys:
                decision_state = "fast_confirmed"
            elif self._confirmation_strategy == "legacy_strict":
                if (
                    snapshot.revolution_index >= 3
                    and sum(int(present) for _, present in history)
                    >= self._confirmation_hits
                ):
                    decision_state = "confirmed"
            elif (
                snapshot.revolution_index >= 2
                and sum(int(present) for _, present in history)
                >= self._confirmation_hits
            ):
                decision_state = "confirmed"
            if decision_state is not None:
                confirmed_match = AssociationMatch(
                    match.track_a_id,
                    match.track_b_id,
                    match.score,
                    decision_state,
                )
                confirmed.append(confirmed_match)
                if decision_state == "fast_confirmed":
                    fast_confirmed.append(confirmed_match)
        stale = [
            key
            for key, history in self._histories.items()
            if key[:2] == prefix
            and history
            and history[-1][0] <= snapshot.revolution_index - self._confirmation_window
        ]
        for key in stale:
            del self._histories[key]
        confirmation_ms = (time.perf_counter() - confirmation_start) * 1000.0

        rejected_by_threshold = max(
            0,
            int(graph.edge_index.shape[1]) - len(raw_matches),
        )
        rejection_reasons = {
            key.removeprefix("rejected_"): int(value)
            for key, value in diagnostics.items()
            if key.startswith("rejected_") and value
        }
        if rejected_by_threshold:
            rejection_reasons["assignment_or_probability_threshold"] = rejected_by_threshold
        contract_version = str(diagnostics.get("snapshot_contract_version", "v1"))
        if contract_version != "v2":
            rejection_reasons["snapshot_v1_feature_fallback"] = 1
        backend_suffix = "gpu" if self._device.type == "cuda" else "cpu_fallback"
        availability = (
            f"empty_candidate_graph_{backend_suffix}"
            if graph.edge_index.shape[1] == 0
            else f"available_{backend_suffix}"
        )
        end_to_end_ms = (time.perf_counter() - end_to_end_start) * 1000.0
        confirmed_keys = {
            (match.track_a_id, match.track_b_id) for match in confirmed
        }
        tentative_matches = tuple(
            AssociationMatch(
                match.track_a_id,
                match.track_b_id,
                match.score,
                "tentative" if snapshot.revolution_index >= 2 else "raw",
            )
            for match in raw_matches
            if snapshot.revolution_index >= 2
            if (match.track_a_id, match.track_b_id) not in confirmed_keys
        )
        publication_matches = tuple(confirmed)
        candidate_fingerprint = _candidate_graph_fingerprint(snapshot)
        stage_latencies = {
            "candidate_build_ms": candidate_build_ms,
            "tensor_preparation_ms": tensor_preparation_ms,
            "gpu_scoring_ms": scoring_ms if self._device.type == "cuda" else 0.0,
            "cpu_scoring_ms": scoring_ms if self._device.type == "cpu" else 0.0,
            "hungarian_ms": hungarian_ms,
            "confirmation_ms": confirmation_ms,
        }
        if graph.edge_index.shape[1] and not publication_matches:
            availability = f"tentative_{backend_suffix}"
        publication = AssociationPublication(
            route_name="gnn",
            route_version=self.route_version,
            model_fingerprint=self.model_fingerprint,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            input_fingerprint=input_fingerprint,
            availability=availability,
            matches=publication_matches,
            rejection_reasons=rejection_reasons,
            candidate_graph_fingerprint=candidate_fingerprint or "",
            stage_latencies_ms=stage_latencies,
            scoring_ms=tensor_preparation_ms + scoring_ms,
            hungarian_ms=hungarian_ms,
            end_to_end_ms=max(
                end_to_end_ms,
                candidate_build_ms
                + tensor_preparation_ms
                + scoring_ms
                + hungarian_ms
                + confirmation_ms,
            ),
            deadline_ms=1000.0,
        )
        self._last_revolution[prefix] = snapshot.revolution_index
        return OnlineInferenceResult(
            publication=publication,
            raw_matches=raw_matches,
            tentative_matches=tentative_matches,
            fast_confirmed_matches=tuple(fast_confirmed),
            confirmed_matches=tuple(confirmed),
            rejection_reasons=rejection_reasons,
            inference_backend=self.inference_backend,
            gpu_inference_ms=scoring_ms if self._device.type == "cuda" else None,
            cpu_inference_ms=scoring_ms if self._device.type == "cpu" else None,
            model_fingerprint_sha256=self.model_fingerprint,
            input_fingerprint_sha256=input_fingerprint,
            snapshot_contract_version=contract_version,
            snapshot_v1_fallback=contract_version != "v2",
            target_count=target_count,
            candidate_graph_fingerprint_sha256=candidate_fingerprint,
            stage_latency_ms={
                **stage_latencies,
                "end_to_end_ms": publication.end_to_end_ms,
            },
            confirmation_strategy=self._confirmation_strategy,
            diagnostic_mode=self._diagnostic_mode,
            route_version=self.route_version,
        )
