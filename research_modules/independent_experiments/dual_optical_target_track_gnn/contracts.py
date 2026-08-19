"""Public records for anonymous target-hypothesis to local-track association."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np


SCHEMA_VERSION = "dual-optical-target-track-gnn-v1"
PAIR_PUBLICATION_SCHEMA_VERSION = "dual-optical-v5-online-pair-publication-v1"
PAIR_PUBLICATION_ROUTE = "asynchronous_geometry"
_FORBIDDEN_PROVENANCE_KEYS = (
    "truth_id",
    "actor_id",
    "global_track_id",
    "label_path",
    "label_sha256",
    "offline_truth",
)
TARGET_FEATURE_NAMES = (
    "position_n_km",
    "position_e_km",
    "position_d_km",
    "velocity_n_100mps",
    "velocity_e_100mps",
    "velocity_d_100mps",
    "speed_100mps",
    "position_sigma_n_100m",
    "position_sigma_e_100m",
    "position_sigma_d_100m",
    "velocity_sigma_n_10mps",
    "velocity_sigma_e_10mps",
    "velocity_sigma_d_10mps",
    "age_revolutions",
    "support_count_10",
    "fit_rms_mrad",
)
TRACK_FEATURE_NAMES = (
    "sample_count",
    "duration_s",
    "sweep_count",
    "azimuth_span_deg",
    "elevation_span_deg",
    "angular_speed_deg_s",
    "missing_ratio",
    "detection_stability",
    "azimuth_rate_deg_s",
    "elevation_rate_deg_s",
    "bearing_sigma_mrad",
    "angular_rate_sigma_deg_s",
    "recent_three_hit_ratio",
    "track_state_quality",
    "snapshot_v2_available",
)
EDGE_FEATURE_NAMES = (
    "bearing_residual_median_mrad",
    "bearing_residual_p90_mrad",
    "mahalanobis2_median",
    "mahalanobis2_p90",
    "angular_rate_residual_deg_s",
    "prediction_age_s",
    "range_km",
    "transverse_position_sigma_m",
    "track_bearing_sigma_mrad",
    "recent_three_hit_ratio",
    "hypothesis_fit_rms_mrad",
    "sample_count",
)


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def payload_fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()


def _contains_forbidden_provenance_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _FORBIDDEN_PROVENANCE_KEYS):
                return True
            if _contains_forbidden_provenance_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_provenance_key(item) for item in value)
    return False


def online_pair_publication_fingerprint(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("publication_fingerprint", None)
    return payload_fingerprint(unsigned)


def validate_online_pair_publication(payload: Mapping[str, Any]) -> str:
    """Validate one anonymous online A/B publication and return its hash."""

    if _contains_forbidden_provenance_key(payload):
        raise ValueError("online pair publication contains offline identity evidence")
    if payload.get("schema_version") != PAIR_PUBLICATION_SCHEMA_VERSION:
        raise ValueError("unsupported online pair publication schema")
    if payload.get("online_anonymous") is not True:
        raise ValueError("confirmed pairs require an anonymous online publication")
    if payload.get("route_name") != PAIR_PUBLICATION_ROUTE:
        raise ValueError("confirmed pair publication route is invalid")
    if int(payload.get("seed", -1)) < 0:
        raise ValueError("online pair publication seed is invalid")
    if int(payload.get("revolution_index", 0)) < 1:
        raise ValueError("online pair publication revolution is invalid")
    if not str(payload.get("protocol_fingerprint") or ""):
        raise ValueError("online pair publication lacks a protocol fingerprint")
    if not str(payload.get("input_fingerprint") or ""):
        raise ValueError("online pair publication lacks an input fingerprint")
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("online pair publication matches must be a list")
    pairs: list[tuple[str, str]] = []
    for match in matches:
        if not isinstance(match, Mapping):
            raise ValueError("online pair publication match is invalid")
        track_a_id = str(match.get("track_a_id") or "")
        track_b_id = str(match.get("track_b_id") or "")
        if not track_a_id or not track_b_id:
            raise ValueError("online pair publication match lacks track IDs")
        if str(match.get("decision_state")) not in {"tentative", "confirmed"}:
            raise ValueError("online pair publication match state is invalid")
        rule_cost = float(match.get("rule_cost", float("nan")))
        if not math.isfinite(rule_cost) or rule_cost < 0.0:
            raise ValueError("online pair publication match cost is invalid")
        pairs.append((track_a_id, track_b_id))
    if len({left for left, _ in pairs}) != len(pairs) or len(
        {right for _, right in pairs}
    ) != len(pairs):
        raise ValueError("online pair publication violates one-to-one assignment")
    latency_ms = float(payload.get("latency_ms", float("nan")))
    if not math.isfinite(latency_ms) or latency_ms < 0.0:
        raise ValueError("online pair publication latency is invalid")
    stored = str(payload.get("publication_fingerprint") or "")
    expected = online_pair_publication_fingerprint(payload)
    if stored != expected:
        raise ValueError("online pair publication fingerprint mismatch")
    return stored


def _finite_tuple(values: tuple[float, ...], length: int, name: str) -> None:
    if len(values) != length or not all(math.isfinite(value) for value in values):
        raise ValueError(f"{name} must contain {length} finite values")


@dataclass(frozen=True)
class ConfirmedTrackPair:
    """One anonymous A/B pairing confirmed at a past revolution boundary."""

    revolution_index: int
    track_a_id: str
    track_b_id: str
    publication_fingerprint: str
    publication_input_fingerprint: str
    publication_protocol_fingerprint: str
    publication_seed: int
    publication_route: str = PAIR_PUBLICATION_ROUTE
    publication_source: str = "online_anonymous"

    def __post_init__(self) -> None:
        if self.revolution_index < 1:
            raise ValueError("confirmed pair revolution must be positive")
        if not self.track_a_id or not self.track_b_id:
            raise ValueError("confirmed pair track identifiers cannot be empty")
        if len(self.publication_fingerprint) != 64 or any(
            value not in "0123456789abcdef" for value in self.publication_fingerprint
        ):
            raise ValueError("confirmed pair publication fingerprint is invalid")
        if not self.publication_input_fingerprint:
            raise ValueError("confirmed pair lacks its online input fingerprint")
        if not self.publication_protocol_fingerprint:
            raise ValueError("confirmed pair lacks its protocol fingerprint")
        if self.publication_seed < 0:
            raise ValueError("confirmed pair publication seed is invalid")
        if self.publication_route != PAIR_PUBLICATION_ROUTE:
            raise ValueError("confirmed pair publication route is invalid")
        if self.publication_source != "online_anonymous":
            raise ValueError("confirmed pair must originate from an anonymous online source")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate_publication(self, payload: Mapping[str, Any]) -> None:
        fingerprint = validate_online_pair_publication(payload)
        if fingerprint != self.publication_fingerprint:
            raise ValueError("confirmed pair references a different online publication")
        if int(payload["revolution_index"]) != self.revolution_index:
            raise ValueError("confirmed pair and publication revolution disagree")
        if int(payload["seed"]) != self.publication_seed:
            raise ValueError("confirmed pair and publication seed disagree")
        if str(payload["protocol_fingerprint"]) != self.publication_protocol_fingerprint:
            raise ValueError("confirmed pair and publication protocol disagree")
        if str(payload["input_fingerprint"]) != self.publication_input_fingerprint:
            raise ValueError("confirmed pair and publication input disagree")
        matches = {
            (str(item["track_a_id"]), str(item["track_b_id"]))
            for item in payload["matches"]
            if str(item.get("decision_state")) == "confirmed"
        }
        if (self.track_a_id, self.track_b_id) not in matches:
            raise ValueError("confirmed pair is absent from the confirmed online matches")

    @classmethod
    def from_online_publication(
        cls,
        payload: Mapping[str, Any],
        track_a_id: str,
        track_b_id: str,
    ) -> "ConfirmedTrackPair":
        fingerprint = validate_online_pair_publication(payload)
        pair = cls(
            revolution_index=int(payload["revolution_index"]),
            track_a_id=str(track_a_id),
            track_b_id=str(track_b_id),
            publication_fingerprint=fingerprint,
            publication_input_fingerprint=str(payload["input_fingerprint"]),
            publication_protocol_fingerprint=str(payload["protocol_fingerprint"]),
            publication_seed=int(payload["seed"]),
            publication_route=str(payload["route_name"]),
        )
        pair.validate_publication(payload)
        return pair

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmedTrackPair":
        allowed = {
            "revolution_index",
            "track_a_id",
            "track_b_id",
            "publication_fingerprint",
            "publication_input_fingerprint",
            "publication_protocol_fingerprint",
            "publication_seed",
            "publication_route",
            "publication_source",
        }
        if set(payload) - allowed or _contains_forbidden_provenance_key(payload):
            raise ValueError("confirmed pair payload contains non-online provenance")
        return cls(
            revolution_index=int(payload["revolution_index"]),
            track_a_id=str(payload["track_a_id"]),
            track_b_id=str(payload["track_b_id"]),
            publication_fingerprint=str(payload["publication_fingerprint"]),
            publication_input_fingerprint=str(payload["publication_input_fingerprint"]),
            publication_protocol_fingerprint=str(
                payload["publication_protocol_fingerprint"]
            ),
            publication_seed=int(payload["publication_seed"]),
            publication_route=str(
                payload.get("publication_route", PAIR_PUBLICATION_ROUTE)
            ),
            publication_source=str(
                payload.get("publication_source", "online_anonymous")
            ),
        )


@dataclass(frozen=True)
class BearingObservation:
    """Anonymous line-of-sight observation used by the weighted fit."""

    camera_id: str
    track_id: str
    timestamp: float
    camera_position_ned: tuple[float, float, float]
    direction_ned: tuple[float, float, float]
    bearing_variance_rad2: float
    source_revolution_index: int

    def __post_init__(self) -> None:
        if not self.camera_id or not self.track_id:
            raise ValueError("bearing observation identifiers cannot be empty")
        if self.timestamp < 0.0 or not math.isfinite(self.timestamp):
            raise ValueError("bearing observation timestamp is invalid")
        _finite_tuple(self.camera_position_ned, 3, "camera_position_ned")
        _finite_tuple(self.direction_ned, 3, "direction_ned")
        norm = math.sqrt(sum(value * value for value in self.direction_ned))
        if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError("bearing observation direction must be normalized")
        if self.bearing_variance_rad2 <= 0.0 or not math.isfinite(
            self.bearing_variance_rad2
        ):
            raise ValueError("bearing variance must be finite and positive")
        if self.source_revolution_index < 1:
            raise ValueError("source revolution must be positive")


@dataclass(frozen=True)
class TargetHypothesis:
    """Anonymous constant-velocity target estimate in the NED working frame."""

    hypothesis_id: str
    created_revolution_index: int
    reference_timestamp: float
    state_ned: tuple[float, float, float, float, float, float]
    covariance_6x6: tuple[float, ...]
    support_count: int
    confirmed_pairs: tuple[ConfirmedTrackPair, ...]
    fit_rms_mrad: float
    fit_condition_number: float
    last_observation_timestamp: float
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id cannot be empty")
        if self.created_revolution_index < 2:
            raise ValueError("a causal hypothesis cannot be created before revolution 2")
        if self.reference_timestamp < 0.0 or self.last_observation_timestamp < 0.0:
            raise ValueError("hypothesis timestamps must be non-negative")
        if self.last_observation_timestamp > self.reference_timestamp + 20.0:
            raise ValueError("hypothesis timestamp fields are inconsistent")
        _finite_tuple(self.state_ned, 6, "state_ned")
        _finite_tuple(self.covariance_6x6, 36, "covariance_6x6")
        covariance = np.asarray(self.covariance_6x6, dtype=float).reshape(6, 6)
        if not np.allclose(covariance, covariance.T, atol=1e-8):
            raise ValueError("hypothesis covariance must be symmetric")
        if float(np.min(np.linalg.eigvalsh(covariance))) < -1e-8:
            raise ValueError("hypothesis covariance must be positive semidefinite")
        if self.support_count < 4:
            raise ValueError("hypothesis requires at least four line-of-sight observations")
        if not self.confirmed_pairs:
            raise ValueError("hypothesis requires at least one confirmed A/B pair")
        if any(
            pair.revolution_index >= self.created_revolution_index
            for pair in self.confirmed_pairs
        ):
            raise ValueError("hypothesis contains a non-causal confirmed pair")
        if self.fit_rms_mrad < 0.0 or not math.isfinite(self.fit_rms_mrad):
            raise ValueError("fit RMS must be finite and non-negative")
        if self.fit_condition_number < 1.0 or not math.isfinite(
            self.fit_condition_number
        ):
            raise ValueError("fit condition number must be finite and at least one")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported target hypothesis schema")

    @property
    def position_ned(self) -> tuple[float, float, float]:
        return self.state_ned[:3]

    @property
    def velocity_ned(self) -> tuple[float, float, float]:
        return self.state_ned[3:]

    def predict(self, timestamp: float) -> tuple[np.ndarray, np.ndarray]:
        dt = float(timestamp) - self.reference_timestamp
        transition = np.eye(6, dtype=float)
        transition[:3, 3:] = np.eye(3) * dt
        state = transition @ np.asarray(self.state_ned, dtype=float)
        covariance = transition @ np.asarray(self.covariance_6x6, dtype=float).reshape(
            6, 6
        ) @ transition.T
        return state, covariance

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confirmed_pairs"] = [pair.to_dict() for pair in self.confirmed_pairs]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TargetHypothesis":
        return cls(
            hypothesis_id=str(payload["hypothesis_id"]),
            created_revolution_index=int(payload["created_revolution_index"]),
            reference_timestamp=float(payload["reference_timestamp"]),
            state_ned=tuple(float(value) for value in payload["state_ned"]),
            covariance_6x6=tuple(
                float(value) for value in payload["covariance_6x6"]
            ),
            support_count=int(payload["support_count"]),
            confirmed_pairs=tuple(
                ConfirmedTrackPair.from_dict(value)
                for value in payload["confirmed_pairs"]
            ),
            fit_rms_mrad=float(payload["fit_rms_mrad"]),
            fit_condition_number=float(payload["fit_condition_number"]),
            last_observation_timestamp=float(payload["last_observation_timestamp"]),
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
        )

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "TargetHypothesis":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class TargetTrackGraph:
    """One-camera bipartite graph after the immutable hard geometry gate."""

    seed: int
    revolution_index: int
    camera_id: str
    hypothesis_ids: tuple[str, ...]
    track_ids: tuple[str, ...]
    target_features: np.ndarray
    track_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    rule_cost: np.ndarray
    whitelist_fingerprint: str
    rejection_counts: Mapping[str, int] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if self.revolution_index < 1 or not self.camera_id:
            raise ValueError("graph revolution and camera must be valid")
        if len(set(self.hypothesis_ids)) != len(self.hypothesis_ids):
            raise ValueError("graph contains duplicate hypothesis IDs")
        if len(set(self.track_ids)) != len(self.track_ids):
            raise ValueError("graph contains duplicate track IDs")
        expected_shapes = (
            self.target_features.shape
            == (len(self.hypothesis_ids), len(TARGET_FEATURE_NAMES)),
            self.track_features.shape
            == (len(self.track_ids), len(TRACK_FEATURE_NAMES)),
            self.edge_index.ndim == 2 and self.edge_index.shape[0] == 2,
        )
        if not all(expected_shapes):
            raise ValueError("target-track graph node or edge-index shape is invalid")
        edge_count = self.edge_index.shape[1]
        if self.edge_features.shape != (edge_count, len(EDGE_FEATURE_NAMES)):
            raise ValueError("target-track edge feature shape is invalid")
        if self.rule_cost.shape != (edge_count,):
            raise ValueError("target-track rule cost shape is invalid")
        if edge_count:
            if int(np.min(self.edge_index)) < 0:
                raise ValueError("graph edge indices cannot be negative")
            if int(np.max(self.edge_index[0])) >= len(self.hypothesis_ids):
                raise ValueError("hypothesis edge index is out of range")
            if int(np.max(self.edge_index[1])) >= len(self.track_ids):
                raise ValueError("track edge index is out of range")
            pairs = [tuple(int(value) for value in pair) for pair in self.edge_index.T]
            if len(pairs) != len(set(pairs)):
                raise ValueError("hard whitelist contains duplicate edges")
        for values in (
            self.target_features,
            self.track_features,
            self.edge_features,
            self.rule_cost,
        ):
            if not np.all(np.isfinite(values)):
                raise ValueError("graph arrays must contain finite values")
        if any(int(value) < 0 for value in self.rejection_counts.values()):
            raise ValueError("graph rejection counts cannot be negative")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported target-track graph schema")
        if self.whitelist_fingerprint != self.compute_whitelist_fingerprint():
            raise ValueError("hard whitelist fingerprint mismatch")

    def compute_whitelist_fingerprint(self) -> str:
        edges = [
            [self.hypothesis_ids[int(target)], self.track_ids[int(track)]]
            for target, track in self.edge_index.T
        ]
        return payload_fingerprint(
            {
                "schema_version": self.schema_version,
                "seed": self.seed,
                "revolution_index": self.revolution_index,
                "camera_id": self.camera_id,
                "edges": edges,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "revolution_index": self.revolution_index,
            "camera_id": self.camera_id,
            "hypothesis_ids": list(self.hypothesis_ids),
            "track_ids": list(self.track_ids),
            "target_features": self.target_features.tolist(),
            "track_features": self.track_features.tolist(),
            "edge_index": self.edge_index.tolist(),
            "edge_features": self.edge_features.tolist(),
            "rule_cost": self.rule_cost.tolist(),
            "whitelist_fingerprint": self.whitelist_fingerprint,
            "rejection_counts": dict(self.rejection_counts),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TargetTrackGraph":
        graph = cls(
            seed=int(payload["seed"]),
            revolution_index=int(payload["revolution_index"]),
            camera_id=str(payload["camera_id"]),
            hypothesis_ids=tuple(str(value) for value in payload["hypothesis_ids"]),
            track_ids=tuple(str(value) for value in payload["track_ids"]),
            target_features=np.asarray(payload["target_features"], dtype=np.float32).reshape(
                -1, len(TARGET_FEATURE_NAMES)
            ),
            track_features=np.asarray(payload["track_features"], dtype=np.float32).reshape(
                -1, len(TRACK_FEATURE_NAMES)
            ),
            edge_index=np.asarray(payload["edge_index"], dtype=np.int64).reshape(2, -1),
            edge_features=np.asarray(payload["edge_features"], dtype=np.float32).reshape(
                -1, len(EDGE_FEATURE_NAMES)
            ),
            rule_cost=np.asarray(payload["rule_cost"], dtype=np.float32),
            whitelist_fingerprint=str(payload["whitelist_fingerprint"]),
            rejection_counts={
                str(key): int(value)
                for key, value in payload.get("rejection_counts", {}).items()
            },
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
        )
        graph.validate()
        return graph

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "TargetTrackGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class TargetTrackPublication:
    """Causal online publication for one hypothesis in one camera."""

    seed: int
    revolution_index: int
    camera_id: str
    hypothesis_id: str
    local_track_id: str | None
    route: str
    decision_state: str
    agreement_count: int
    window_size: int
    final_cost: float | None
    whitelist_fingerprint: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.revolution_index < 1 or not self.camera_id or not self.hypothesis_id:
            raise ValueError("publication identifiers are invalid")
        if self.route not in {"deterministic", "gnn_assisted"}:
            raise ValueError("publication route is invalid")
        if self.decision_state not in {"unmatched", "tentative", "confirmed"}:
            raise ValueError("publication decision state is invalid")
        if not 0 <= self.agreement_count <= self.window_size <= 3:
            raise ValueError("publication confirmation window is invalid")
        if self.decision_state == "unmatched" and self.local_track_id is not None:
            raise ValueError("an unmatched publication cannot carry a local track")
        if self.local_track_id is None and self.decision_state != "unmatched":
            raise ValueError("a matched publication requires a local track")
        if self.final_cost is not None and not math.isfinite(self.final_cost):
            raise ValueError("publication cost must be finite")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported publication schema")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TargetTrackPublication":
        return cls(
            seed=int(payload["seed"]),
            revolution_index=int(payload["revolution_index"]),
            camera_id=str(payload["camera_id"]),
            hypothesis_id=str(payload["hypothesis_id"]),
            local_track_id=(
                None
                if payload.get("local_track_id") is None
                else str(payload["local_track_id"])
            ),
            route=str(payload["route"]),
            decision_state=str(payload["decision_state"]),
            agreement_count=int(payload["agreement_count"]),
            window_size=int(payload["window_size"]),
            final_cost=(
                None if payload.get("final_cost") is None else float(payload["final_cost"])
            ),
            whitelist_fingerprint=str(payload["whitelist_fingerprint"]),
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
        )

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "TargetTrackPublication":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
