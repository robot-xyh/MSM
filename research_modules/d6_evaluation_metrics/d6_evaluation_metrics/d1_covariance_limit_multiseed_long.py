"""Read-only multi-seed and long-duration admission for the D1 optimization.

The matrix is preregistered by explicit group, seed, duration, episode, GNU
``time -v`` resource, and cross-build paths.  No arm, seed, duration, or scale
is inferred from a directory name.  D6 only consumes persisted evidence and
never writes to a runtime or control path.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import fmean, median
from typing import Any, Mapping, Sequence

from .d1_covariance_limit_clean_pair import (
    D1CovarianceLimitCleanPairInput,
    evaluate_d1_covariance_limit_explicit_pair,
)


D1_COVARIANCE_LIMIT_MULTISEED_LONG_SCHEMA_VERSION = (
    "d6.d1-covariance-limit-multiseed-long.v1"
)
D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-covariance-limit-multiseed-evidence-v1"
)
D1_COVARIANCE_LIMIT_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-covariance-limit-multiseed-matrix-v1"
)
D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID = (
    "d1-covariance-limit-multiseed-20260724-v1"
)
D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID = (
    "d1-covariance-limit-multiseed-20260724-v2"
)
D1_COVARIANCE_LIMIT_V3_EXPERIMENT_ID = (
    "d1-covariance-limit-multiseed-20260724-v3"
)
D1_COVARIANCE_LIMIT_EXPERIMENT_ID = (
    D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID
)
D1_COVARIANCE_LIMIT_MULTISEED_LONG_EVALUATION_DATE = "2026-07-24"
D1_COVARIANCE_LIMIT_REFERENCE_COMMIT = (
    "7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d"
)
D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT = (
    "95bf46e34321127313757986bb28bfb14b7e3c59"
)
D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT = (
    "3c134c34655618b2e4d41302f9fbf3b6b4b78929"
)
D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT = (
    "8c1188267c37c5e4a546abc8e7dd6c5a4bb48dba"
)
D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT = "e4147b8"
D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT = (
    "fix(d2): align false alarm exclusion audit"
)
D1_COVARIANCE_LIMIT_V3_REFERENCE_COMMIT = (
    "a5a472cf81496d94a98db3deb88a3d5c6951f0ce"
)
D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT = (
    "064cbb979d3bab68fee995e476df25709eb666db"
)
D1_COVARIANCE_LIMIT_V3_REFERENCE_BASE_COMMIT = (
    D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT
)
D1_COVARIANCE_LIMIT_V3_CANDIDATE_BASE_COMMIT = (
    D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT
)
D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SOURCE_COMMIT = (
    D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT
)
D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SUBJECT = (
    D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT
)
D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SOURCE_COMMIT = (
    D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT
)
D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SUBJECT = (
    "fix(d1): preserve covariance positive semidefiniteness"
)
D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_COMMIT = (
    D1_COVARIANCE_LIMIT_V3_REFERENCE_COMMIT
)
D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_SUBJECT = (
    "test(d1): select scalar covariance reference"
)
D1_COVARIANCE_LIMIT_SHORT_SEEDS = tuple(range(1101, 1111))
D1_COVARIANCE_LIMIT_LONG_SEEDS = tuple(range(1101, 1104))
D1_COVARIANCE_LIMIT_SHORT_DURATION_S = 2.2
D1_COVARIANCE_LIMIT_LONG_DURATION_S = 10.0
D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES = 10000
D1_COVARIANCE_LIMIT_BOOTSTRAP_RNG_SEED = 20260724
D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256 = (
    "deabac3fbf2a788f68a0b807945e5f1bedacf8c5917c4d3b49c5cffb3c90da70"
)
D1_COVARIANCE_LIMIT_RUN_FLAGS = (
    "--integrated-stack",
    "--d1-d2-structural-ambiguity-hold",
)
D1_COVARIANCE_LIMIT_MINIMUM_SHORT_FASTER_COUNT = 8
D1_COVARIANCE_LIMIT_MINIMUM_LONG_FASTER_COUNT = 2
D1_COVARIANCE_LIMIT_MINIMUM_MEAN_IMPROVEMENT_PCT = 5.0
D1_COVARIANCE_LIMIT_MAXIMUM_DEGRADATION_PCT = 5.0

_SHORT_GROUP = "short"
_LONG_GROUP = "long"
_GROUP_ORDER = {_SHORT_GROUP: 0, _LONG_GROUP: 1}
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_METRICS = (
    "d1_fusion_wall_s",
    "d1_fusion_p95_ms",
    "d1_scan_input_wall_s",
    "core_wall_s",
    "external_elapsed_s",
    "maximum_rss_kib",
    "real_time_factor",
)
_GROWTH_METRICS = (
    "d1_fusion_wall_s",
    "core_wall_s",
    "external_elapsed_s",
)
_EXPECTED_ADMISSION_GATES = {
    "short_minimum_candidate_faster_count": 8,
    "short_minimum_fusion_improvement_pct": 5.0,
    "short_bootstrap_relative_change_upper_bound_pct": 0.0,
    "long_minimum_candidate_faster_count": 2,
    "long_minimum_fusion_improvement_pct": 5.0,
    "maximum_long_short_unit_cost_growth_degradation_pct": 5.0,
    "maximum_core_wall_mean_increase_pct": 5.0,
    "maximum_rss_mean_increase_pct": 5.0,
    "maximum_any_pair_rss_increase_pct": 5.0,
}
_EXPECTED_EVIDENCE_BOUNDARY = {
    "simulation_mode": "three_dimensional_point_mass",
    "airsim_evidence": False,
    "truth_is_online_control_input": False,
    "system_realtime_requires_real_time_factor_at_least_one": True,
}
_EXPECTED_CASES = (
    ("short_seed_1101", "short", 1101, 2.2, ("reference", "candidate")),
    ("short_seed_1102", "short", 1102, 2.2, ("candidate", "reference")),
    ("short_seed_1103", "short", 1103, 2.2, ("reference", "candidate")),
    ("short_seed_1104", "short", 1104, 2.2, ("candidate", "reference")),
    ("short_seed_1105", "short", 1105, 2.2, ("reference", "candidate")),
    ("short_seed_1106", "short", 1106, 2.2, ("candidate", "reference")),
    ("short_seed_1107", "short", 1107, 2.2, ("reference", "candidate")),
    ("short_seed_1108", "short", 1108, 2.2, ("candidate", "reference")),
    ("short_seed_1109", "short", 1109, 2.2, ("reference", "candidate")),
    ("short_seed_1110", "short", 1110, 2.2, ("candidate", "reference")),
    ("long_seed_1101", "long", 1101, 10.0, ("candidate", "reference")),
    ("long_seed_1102", "long", 1102, 10.0, ("reference", "candidate")),
    ("long_seed_1103", "long", 1103, 10.0, ("candidate", "reference")),
)


class D1CovarianceLimitEvidenceManifestError(ValueError):
    """Raised when the preregistered evidence manifest fails closed."""


@dataclass(frozen=True)
class D1CovarianceLimitKnownMatrixRegistration:
    """One immutable producer matrix identity accepted by D6."""

    experiment_id: str
    reference_commit: str
    candidate_commit: str
    reference_base_commit: str | None = None
    candidate_base_commit: str | None = None
    common_d2_fix_source_commit: str | None = None
    common_d2_fix_subject: str | None = None
    v1_outputs_reused: bool | None = None
    common_d1_psd_fix_source_commit: str | None = None
    common_d1_psd_fix_subject: str | None = None
    reference_treatment_commit: str | None = None
    reference_treatment_subject: str | None = None
    v2_outputs_reused: bool | None = None
    reference_vectorized_covariance_limit: bool | None = None
    candidate_vectorized_covariance_limit: bool | None = None

    def __post_init__(self) -> None:
        experiment_id = str(self.experiment_id).strip()
        if not experiment_id:
            raise ValueError("experiment_id must not be empty")
        object.__setattr__(self, "experiment_id", experiment_id)
        for field in (
            "reference_commit",
            "candidate_commit",
            "reference_base_commit",
            "candidate_base_commit",
            "common_d1_psd_fix_source_commit",
            "reference_treatment_commit",
        ):
            value = getattr(self, field)
            if value is None:
                continue
            normalized_commit = str(value).strip().lower()
            if _GIT_COMMIT_RE.fullmatch(normalized_commit) is None:
                raise ValueError(
                    f"{field} must be a 40-character hexadecimal commit"
                )
            object.__setattr__(
                self,
                field,
                normalized_commit,
            )
        fix_source = self.common_d2_fix_source_commit
        if fix_source is not None:
            normalized = str(fix_source).strip().lower()
            if re.fullmatch(r"[0-9a-f]{7,40}", normalized) is None:
                raise ValueError(
                    "common_d2_fix_source_commit must be a hexadecimal "
                    "Git commit identifier"
                )
            object.__setattr__(
                self,
                "common_d2_fix_source_commit",
                normalized,
            )
        for field in (
            "common_d2_fix_subject",
            "common_d1_psd_fix_subject",
            "reference_treatment_subject",
        ):
            subject = getattr(self, field)
            if subject is None:
                continue
            normalized_subject = str(subject).strip()
            if not normalized_subject:
                raise ValueError(f"{field} must not be empty")
            object.__setattr__(
                self,
                field,
                normalized_subject,
            )
        provenance_groups = {
            "base fix provenance": (
                "reference_base_commit",
                "candidate_base_commit",
                "common_d2_fix_source_commit",
                "common_d2_fix_subject",
                "v1_outputs_reused",
            ),
            "v3 treatment provenance": (
                "common_d1_psd_fix_source_commit",
                "common_d1_psd_fix_subject",
                "reference_treatment_commit",
                "reference_treatment_subject",
                "v2_outputs_reused",
                "reference_vectorized_covariance_limit",
                "candidate_vectorized_covariance_limit",
            ),
        }
        group_presence: dict[str, bool] = {}
        for group_name, fields in provenance_groups.items():
            values = tuple(getattr(self, field) for field in fields)
            any_present = any(value is not None for value in values)
            if any_present and any(value is None for value in values):
                raise ValueError(
                    f"{group_name} fields must be all absent or all present"
                )
            group_presence[group_name] = any_present
        if (
            group_presence["v3 treatment provenance"]
            and not group_presence["base fix provenance"]
        ):
            raise ValueError(
                "v3 treatment provenance requires base fix provenance"
            )
        for field in (
            "v1_outputs_reused",
            "v2_outputs_reused",
            "reference_vectorized_covariance_limit",
            "candidate_vectorized_covariance_limit",
        ):
            value = getattr(self, field)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{field} must be a bool when present")


D1_COVARIANCE_LIMIT_V1_KNOWN_MATRIX_REGISTRATION = (
    D1CovarianceLimitKnownMatrixRegistration(
        experiment_id=D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID,
        reference_commit=D1_COVARIANCE_LIMIT_REFERENCE_COMMIT,
        candidate_commit=D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT,
    )
)
D1_COVARIANCE_LIMIT_V2_KNOWN_MATRIX_REGISTRATION = (
    D1CovarianceLimitKnownMatrixRegistration(
        experiment_id=D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID,
        reference_commit=D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT,
        candidate_commit=D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT,
        reference_base_commit=D1_COVARIANCE_LIMIT_REFERENCE_COMMIT,
        candidate_base_commit=D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT,
        common_d2_fix_source_commit=(
            D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT
        ),
        common_d2_fix_subject=(
            D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT
        ),
        v1_outputs_reused=False,
    )
)
D1_COVARIANCE_LIMIT_V3_KNOWN_MATRIX_REGISTRATION = (
    D1CovarianceLimitKnownMatrixRegistration(
        experiment_id=D1_COVARIANCE_LIMIT_V3_EXPERIMENT_ID,
        reference_commit=D1_COVARIANCE_LIMIT_V3_REFERENCE_COMMIT,
        candidate_commit=D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT,
        reference_base_commit=(
            D1_COVARIANCE_LIMIT_V3_REFERENCE_BASE_COMMIT
        ),
        candidate_base_commit=(
            D1_COVARIANCE_LIMIT_V3_CANDIDATE_BASE_COMMIT
        ),
        common_d2_fix_source_commit=(
            D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SOURCE_COMMIT
        ),
        common_d2_fix_subject=(
            D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SUBJECT
        ),
        v1_outputs_reused=False,
        common_d1_psd_fix_source_commit=(
            D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SOURCE_COMMIT
        ),
        common_d1_psd_fix_subject=(
            D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SUBJECT
        ),
        reference_treatment_commit=(
            D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_COMMIT
        ),
        reference_treatment_subject=(
            D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_SUBJECT
        ),
        v2_outputs_reused=False,
        reference_vectorized_covariance_limit=False,
        candidate_vectorized_covariance_limit=True,
    )
)
_KNOWN_MATRIX_REGISTRATIONS = {
    registration.experiment_id: registration
    for registration in (
        D1_COVARIANCE_LIMIT_V1_KNOWN_MATRIX_REGISTRATION,
        D1_COVARIANCE_LIMIT_V2_KNOWN_MATRIX_REGISTRATION,
        D1_COVARIANCE_LIMIT_V3_KNOWN_MATRIX_REGISTRATION,
    )
}


@dataclass(frozen=True)
class D1CovarianceLimitMatrixPairInput:
    """One explicitly registered matrix cell."""

    group: str
    seed: int
    duration_s: float
    reference_episode_dir: Path
    candidate_episode_dir: Path
    reference_resource_path: Path
    candidate_resource_path: Path
    cross_build_path: Path

    def __post_init__(self) -> None:
        group = str(self.group).strip().lower()
        if not group:
            raise ValueError("group must not be empty")
        if (
            not isinstance(self.seed, int)
            or isinstance(self.seed, bool)
            or self.seed < 0
        ):
            raise ValueError("seed must be a nonnegative integer")
        if not _is_finite_number(self.duration_s) or self.duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "duration_s", float(self.duration_s))
        for field in (
            "reference_episode_dir",
            "candidate_episode_dir",
            "reference_resource_path",
            "candidate_resource_path",
            "cross_build_path",
        ):
            object.__setattr__(
                self,
                field,
                Path(getattr(self, field)).expanduser().resolve(),
            )

    @property
    def matrix_key(self) -> tuple[str, int]:
        return (self.group, self.seed)

    def clean_pair_input(self) -> D1CovarianceLimitCleanPairInput:
        return D1CovarianceLimitCleanPairInput(
            round_id=f"{self.group}-seed-{self.seed}",
            reference_episode_dir=self.reference_episode_dir,
            candidate_episode_dir=self.candidate_episode_dir,
            cross_build_path=self.cross_build_path,
            reference_resource_path=self.reference_resource_path,
            candidate_resource_path=self.candidate_resource_path,
        )


@dataclass(frozen=True)
class D1CovarianceLimitEvidenceManifest:
    """Validated explicit bindings from one completed main-run manifest."""

    source_path: Path
    source_sha256: str
    experiment_id: str
    reference_commit: str
    candidate_commit: str
    reference_base_commit: str | None
    candidate_base_commit: str | None
    common_d2_fix_source_commit: str | None
    common_d2_fix_subject: str | None
    v1_outputs_reused: bool | None
    common_d1_psd_fix_source_commit: str | None
    common_d1_psd_fix_subject: str | None
    reference_treatment_commit: str | None
    reference_treatment_subject: str | None
    v2_outputs_reused: bool | None
    reference_vectorized_covariance_limit: bool | None
    candidate_vectorized_covariance_limit: bool | None
    runtime_profile_sha256: str
    bootstrap_resamples: int
    bootstrap_rng_seed: int
    pairs: tuple[D1CovarianceLimitMatrixPairInput, ...]

    def provenance(self) -> dict[str, Any]:
        return {
            "schema_version": (
                D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION
            ),
            "experiment_id": self.experiment_id,
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "manifest_status": "complete",
            "case_count": len(self.pairs),
            "reference_commit": self.reference_commit,
            "candidate_commit": self.candidate_commit,
            "reference_base_commit": self.reference_base_commit,
            "candidate_base_commit": self.candidate_base_commit,
            "common_d2_fix_source_commit": (
                self.common_d2_fix_source_commit
            ),
            "common_d2_fix_subject": self.common_d2_fix_subject,
            "v1_outputs_reused": self.v1_outputs_reused,
            "common_d1_psd_fix_source_commit": (
                self.common_d1_psd_fix_source_commit
            ),
            "common_d1_psd_fix_subject": (
                self.common_d1_psd_fix_subject
            ),
            "reference_treatment_commit": (
                self.reference_treatment_commit
            ),
            "reference_treatment_subject": (
                self.reference_treatment_subject
            ),
            "v2_outputs_reused": self.v2_outputs_reused,
            "reference_vectorized_covariance_limit": (
                self.reference_vectorized_covariance_limit
            ),
            "candidate_vectorized_covariance_limit": (
                self.candidate_vectorized_covariance_limit
            ),
            "runtime_profile_sha256": self.runtime_profile_sha256,
            "bootstrap_resamples": self.bootstrap_resamples,
            "bootstrap_rng_seed": self.bootstrap_rng_seed,
            "arm_seed_duration_inferred_from_path": False,
        }


@dataclass(frozen=True)
class D1CovarianceLimitMatrixRegistration:
    """Frozen matrix definition used by both evaluator and report."""

    short_seeds: tuple[int, ...] = D1_COVARIANCE_LIMIT_SHORT_SEEDS
    long_seeds: tuple[int, ...] = D1_COVARIANCE_LIMIT_LONG_SEEDS
    short_duration_s: float = D1_COVARIANCE_LIMIT_SHORT_DURATION_S
    long_duration_s: float = D1_COVARIANCE_LIMIT_LONG_DURATION_S
    target_count: int = 200
    resource_count: int = 200
    recon_count: int = 2
    structural_ambiguity_hold_required: bool = True
    runtime_profile_sha256: str = (
        D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256
    )

    def __post_init__(self) -> None:
        for name in ("short_seeds", "long_seeds"):
            seeds = tuple(getattr(self, name))
            if (
                not seeds
                or len(seeds) != len(set(seeds))
                or any(
                    not isinstance(seed, int)
                    or isinstance(seed, bool)
                    or seed < 0
                    for seed in seeds
                )
            ):
                raise ValueError(f"{name} must contain unique nonnegative seeds")
            object.__setattr__(self, name, seeds)
        for name in ("short_duration_s", "long_duration_s"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        for name in ("target_count", "resource_count", "recon_count"):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{name} must be a nonnegative integer")
        runtime_profile_sha256 = str(
            self.runtime_profile_sha256
        ).strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", runtime_profile_sha256) is None:
            raise ValueError(
                "runtime_profile_sha256 must be a lowercase sha256 digest"
            )
        object.__setattr__(
            self,
            "runtime_profile_sha256",
            runtime_profile_sha256,
        )

    def expected_keys(self) -> set[tuple[str, int]]:
        return {
            *{(_SHORT_GROUP, seed) for seed in self.short_seeds},
            *{(_LONG_GROUP, seed) for seed in self.long_seeds},
        }

    def seeds_for(self, group: str) -> tuple[int, ...]:
        if group == _SHORT_GROUP:
            return self.short_seeds
        if group == _LONG_GROUP:
            return self.long_seeds
        return ()

    def duration_for(self, group: str) -> float | None:
        if group == _SHORT_GROUP:
            return self.short_duration_s
        if group == _LONG_GROUP:
            return self.long_duration_s
        return None


DEFAULT_D1_COVARIANCE_LIMIT_MATRIX_REGISTRATION = (
    D1CovarianceLimitMatrixRegistration()
)


def load_d1_covariance_limit_evidence_manifest(
    source: str | Path,
) -> D1CovarianceLimitEvidenceManifest:
    """Load one completed, preregistered manifest without path inference."""

    path = Path(source).expanduser().resolve()
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise D1CovarianceLimitEvidenceManifestError(
            f"unable to read evidence manifest: {path}: {exc}"
        ) from exc
    manifest = _manifest_mapping(payload, "evidence manifest")
    _manifest_equal(
        manifest.get("schema_version"),
        D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "evidence manifest schema_version",
    )
    experiment_id = _manifest_text(
        manifest.get("experiment_id"),
        "evidence manifest experiment_id",
    )
    known_registration = _known_matrix_registration(experiment_id)
    _manifest_equal(
        manifest.get("status"),
        "complete",
        "evidence manifest status",
    )
    _manifest_text(
        manifest.get("completed_at_utc"),
        "evidence manifest completed_at_utc",
    )
    _manifest_text(
        manifest.get("matrix_path"),
        "evidence manifest matrix_path",
    )
    output_root = _manifest_explicit_path(
        manifest.get("output_root"),
        "evidence manifest output_root",
        base=path.parent,
        require="directory",
    )

    matrix = _manifest_mapping(
        manifest.get("matrix"),
        "embedded matrix",
    )
    _validate_embedded_matrix(
        matrix,
        known_registration=known_registration,
    )
    _manifest_equal(
        matrix.get("experiment_id"),
        manifest.get("experiment_id"),
        "manifest and embedded matrix experiment_id",
    )

    raw_cases = _manifest_sequence(
        manifest.get("cases"),
        "evidence manifest cases",
    )
    if len(raw_cases) != len(_EXPECTED_CASES):
        raise D1CovarianceLimitEvidenceManifestError(
            "evidence manifest must contain exactly 13 preregistered cases"
        )
    pairs: list[D1CovarianceLimitMatrixPairInput] = []
    used_paths: set[Path] = set()
    for raw_case, expected in zip(
        raw_cases,
        _EXPECTED_CASES,
        strict=True,
    ):
        case = _manifest_mapping(raw_case, "evidence manifest case")
        metadata = _normalized_manifest_case(case)
        if metadata != expected:
            raise D1CovarianceLimitEvidenceManifestError(
                "evidence manifest case metadata does not match the "
                f"preregistered matrix: expected {expected!r}, got "
                f"{metadata!r}"
            )
        case_id, group, seed, duration_s, arm_order = metadata
        arms = _manifest_mapping(
            case.get("arms"),
            f"{case_id} arms",
        )
        if set(arms) != {"reference", "candidate"}:
            raise D1CovarianceLimitEvidenceManifestError(
                f"{case_id} arms must be exactly reference and candidate"
            )
        arm_paths: dict[str, tuple[Path, Path]] = {}
        for arm in ("reference", "candidate"):
            record = _manifest_mapping(
                arms.get(arm),
                f"{case_id} {arm} arm",
            )
            _manifest_equal(
                record.get("arm"),
                arm,
                f"{case_id} {arm} arm label",
            )
            expected_commit = (
                known_registration.reference_commit
                if arm == "reference"
                else known_registration.candidate_commit
            )
            _manifest_equal(
                record.get("expected_commit"),
                expected_commit,
                f"{case_id} {arm} expected_commit",
            )
            if record.get("status") not in {"complete", "reused"}:
                raise D1CovarianceLimitEvidenceManifestError(
                    f"{case_id} {arm} status must be complete or reused"
                )
            return_code = record.get("return_code")
            if (
                not isinstance(return_code, int)
                or isinstance(return_code, bool)
                or return_code != 0
            ):
                raise D1CovarianceLimitEvidenceManifestError(
                    f"{case_id} {arm} return_code must be integer zero"
                )
            for field in (
                "worktree",
                "stdout_path",
                "stderr_path",
            ):
                _manifest_text(
                    record.get(field),
                    f"{case_id} {arm} {field}",
                )
            command = _manifest_sequence(
                record.get("command"),
                f"{case_id} {arm} command",
            )
            if not command or any(
                not isinstance(item, str) or not item.strip()
                for item in command
            ):
                raise D1CovarianceLimitEvidenceManifestError(
                    f"{case_id} {arm} command must be a non-empty string list"
                )
            episode_dir = _manifest_explicit_path(
                record.get("episode_dir"),
                f"{case_id} {arm} episode_dir",
                base=path.parent,
                require="directory",
            )
            resource_path = _manifest_explicit_path(
                record.get("resource_path"),
                f"{case_id} {arm} resource_path",
                base=path.parent,
                require="file",
            )
            _require_under_output_root(
                episode_dir,
                output_root,
                f"{case_id} {arm} episode_dir",
            )
            _require_under_output_root(
                resource_path,
                output_root,
                f"{case_id} {arm} resource_path",
            )
            for evidence_path in (episode_dir, resource_path):
                if evidence_path in used_paths:
                    raise D1CovarianceLimitEvidenceManifestError(
                        f"duplicate evidence path in manifest: {evidence_path}"
                    )
                used_paths.add(evidence_path)
            arm_paths[arm] = (episode_dir, resource_path)

        _manifest_equal(
            tuple(arm_order),
            expected[4],
            f"{case_id} arm_order",
        )
        _manifest_text(
            case.get("cross_build_dir"),
            f"{case_id} cross_build_dir",
        )
        _manifest_equal(
            case.get("cross_build_status"),
            "passed",
            f"{case_id} cross_build_status",
        )
        cross_build_path = _manifest_explicit_path(
            case.get("cross_build_json"),
            f"{case_id} cross_build_json",
            base=path.parent,
            require="file",
        )
        _require_under_output_root(
            cross_build_path,
            output_root,
            f"{case_id} cross_build_json",
        )
        if cross_build_path in used_paths:
            raise D1CovarianceLimitEvidenceManifestError(
                f"duplicate evidence path in manifest: {cross_build_path}"
            )
        used_paths.add(cross_build_path)
        pairs.append(
            D1CovarianceLimitMatrixPairInput(
                group=group,
                seed=seed,
                duration_s=duration_s,
                reference_episode_dir=arm_paths["reference"][0],
                candidate_episode_dir=arm_paths["candidate"][0],
                reference_resource_path=arm_paths["reference"][1],
                candidate_resource_path=arm_paths["candidate"][1],
                cross_build_path=cross_build_path,
            )
        )

    return D1CovarianceLimitEvidenceManifest(
        source_path=path,
        source_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        experiment_id=known_registration.experiment_id,
        reference_commit=known_registration.reference_commit,
        candidate_commit=known_registration.candidate_commit,
        reference_base_commit=known_registration.reference_base_commit,
        candidate_base_commit=known_registration.candidate_base_commit,
        common_d2_fix_source_commit=(
            known_registration.common_d2_fix_source_commit
        ),
        common_d2_fix_subject=known_registration.common_d2_fix_subject,
        v1_outputs_reused=known_registration.v1_outputs_reused,
        common_d1_psd_fix_source_commit=(
            known_registration.common_d1_psd_fix_source_commit
        ),
        common_d1_psd_fix_subject=(
            known_registration.common_d1_psd_fix_subject
        ),
        reference_treatment_commit=(
            known_registration.reference_treatment_commit
        ),
        reference_treatment_subject=(
            known_registration.reference_treatment_subject
        ),
        v2_outputs_reused=known_registration.v2_outputs_reused,
        reference_vectorized_covariance_limit=(
            known_registration.reference_vectorized_covariance_limit
        ),
        candidate_vectorized_covariance_limit=(
            known_registration.candidate_vectorized_covariance_limit
        ),
        runtime_profile_sha256=(
            D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256
        ),
        bootstrap_resamples=D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed=D1_COVARIANCE_LIMIT_BOOTSTRAP_RNG_SEED,
        pairs=tuple(pairs),
    )


def evaluate_d1_covariance_limit_evidence_manifest(
    source: str | Path,
) -> dict[str, Any]:
    """Validate and evaluate one completed main-produced manifest."""

    evidence = load_d1_covariance_limit_evidence_manifest(source)
    result = evaluate_d1_covariance_limit_multiseed_long(
        evidence.pairs,
        expected_reference_commit=evidence.reference_commit,
        expected_candidate_commit=evidence.candidate_commit,
        bootstrap_resamples=evidence.bootstrap_resamples,
        bootstrap_rng_seed=evidence.bootstrap_rng_seed,
    )
    result["input_contract"] = {
        "mode": "evidence_manifest",
        **evidence.provenance(),
    }
    return result


def evaluate_d1_covariance_limit_multiseed_long(
    pairs: Sequence[D1CovarianceLimitMatrixPairInput],
    *,
    expected_reference_commit: str = (
        D1_COVARIANCE_LIMIT_REFERENCE_COMMIT
    ),
    expected_candidate_commit: str = (
        D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT
    ),
    registration: D1CovarianceLimitMatrixRegistration = (
        DEFAULT_D1_COVARIANCE_LIMIT_MATRIX_REGISTRATION
    ),
    bootstrap_resamples: int = D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = D1_COVARIANCE_LIMIT_BOOTSTRAP_RNG_SEED,
) -> dict[str, Any]:
    """Evaluate the frozen short/long matrix without touching runtime state."""

    reference_commit = _validated_commit(
        expected_reference_commit, "expected_reference_commit"
    )
    candidate_commit = _validated_commit(
        expected_candidate_commit, "expected_candidate_commit"
    )
    if (
        not isinstance(bootstrap_resamples, int)
        or isinstance(bootstrap_resamples, bool)
        or bootstrap_resamples <= 0
    ):
        raise ValueError("bootstrap_resamples must be a positive integer")
    if not isinstance(bootstrap_rng_seed, int) or isinstance(
        bootstrap_rng_seed, bool
    ):
        raise ValueError("bootstrap_rng_seed must be an integer")

    ordered_inputs = sorted(
        pairs,
        key=lambda item: (
            _GROUP_ORDER.get(item.group, 99),
            item.seed,
            str(item.reference_episode_dir),
        ),
    )
    evaluated_pairs = [
        _evaluate_matrix_pair(
            pair,
            registration=registration,
            expected_reference_commit=reference_commit,
            expected_candidate_commit=candidate_commit,
        )
        for pair in ordered_inputs
    ]
    registration_checks = _registration_checks(
        evaluated_pairs,
        registration=registration,
    )
    groups = {
        group: _summarize_group(
            [
                pair
                for pair in evaluated_pairs
                if pair["group"] == group
            ],
            group=group,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )
        for group in (_SHORT_GROUP, _LONG_GROUP)
    }
    growth = _summarize_long_short_growth(
        evaluated_pairs,
        registration=registration,
    )
    gates = _admission_gates(
        evaluated_pairs,
        groups=groups,
        growth=growth,
        registration_checks=registration_checks,
    )
    admitted = all(gate["passed"] for gate in gates.values())
    point_mass_realtime = _point_mass_realtime_conditions(evaluated_pairs)
    realtime_reasons = ["target_runtime_or_airsim_evidence_not_in_matrix"]
    if not point_mass_realtime["passed"]:
        realtime_reasons.append(
            "candidate_point_mass_realtime_conditions_not_met"
        )

    return {
        "schema_version": (
            D1_COVARIANCE_LIMIT_MULTISEED_LONG_SCHEMA_VERSION
        ),
        "evaluation_date": (
            D1_COVARIANCE_LIMIT_MULTISEED_LONG_EVALUATION_DATE
        ),
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "online_truth_used_for_business": False,
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "target_runtime_evidence": False,
            "airsim_evidence": False,
            "reference_commit": reference_commit,
            "candidate_commit": candidate_commit,
            "target_count": registration.target_count,
            "resource_count": registration.resource_count,
            "recon_count": registration.recon_count,
            "structural_ambiguity_hold_required": (
                registration.structural_ambiguity_hold_required
            ),
            "runtime_profile_sha256": (
                registration.runtime_profile_sha256
            ),
            "short_seeds": list(registration.short_seeds),
            "short_duration_s": registration.short_duration_s,
            "long_seeds": list(registration.long_seeds),
            "long_duration_s": registration.long_duration_s,
            "input_pair_count": len(evaluated_pairs),
            "arm_seed_duration_inferred_from_path": False,
            "core_wall_and_external_elapsed_summed": False,
        },
        "bootstrap": {
            "statistic": "mean_paired_relative_change_pct",
            "confidence_level": 0.95,
            "resamples": bootstrap_resamples,
            "rng_seed": bootstrap_rng_seed,
            "resampling_unit": "explicit_seed_pair",
            "percentile_method": "linear_interpolation_n_minus_one",
        },
        "thresholds": {
            "short_minimum_faster_count": (
                D1_COVARIANCE_LIMIT_MINIMUM_SHORT_FASTER_COUNT
            ),
            "long_minimum_faster_count": (
                D1_COVARIANCE_LIMIT_MINIMUM_LONG_FASTER_COUNT
            ),
            "minimum_mean_improvement_pct": (
                D1_COVARIANCE_LIMIT_MINIMUM_MEAN_IMPROVEMENT_PCT
            ),
            "maximum_degradation_pct": (
                D1_COVARIANCE_LIMIT_MAXIMUM_DEGRADATION_PCT
            ),
        },
        "pairs": evaluated_pairs,
        "registration_checks": registration_checks,
        "groups": groups,
        "long_short_unit_cost_growth": growth,
        "admission_gates": gates,
        "d1_optimization_admitted": admitted,
        "point_mass_realtime_conditions": point_mass_realtime,
        "system_realtime_gap_closed": False,
        "system_realtime_gap_reasons": realtime_reasons,
        "not_evaluated": {
            "airsim_runtime": "not_applicable_point_mass_matrix",
            "target_hardware_runtime": "unavailable",
            "rmse": "unavailable_not_in_performance_matrix",
            "nees": "unavailable_not_in_performance_matrix",
            "nis": "unavailable_not_in_performance_matrix",
        },
    }


def write_d1_covariance_limit_multiseed_long_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write JSON, LF-only per-pair CSV, and Chinese Markdown."""

    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = (
        directory / "d1_covariance_limit_multiseed_long_evaluation.json"
    )
    csv_path = directory / "d1_covariance_limit_multiseed_long_pairs.csv"
    markdown_path = (
        directory / "D1_COVARIANCE_LIMIT_MULTISEED_LONG_EVALUATION_CN.md"
    )
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    _write_pair_csv(result, csv_path)
    markdown_path.write_text(
        render_d1_covariance_limit_multiseed_long_markdown(result),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
    }


def render_d1_covariance_limit_multiseed_long_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the matrix result without upgrading its evidence class."""

    admitted = bool(result.get("d1_optimization_admitted"))
    realtime = bool(result.get("system_realtime_gap_closed"))
    lines = [
        "# D1 协方差优化多 seed 与长时准入评估",
        "",
        "## 结论",
        "",
        (
            f"D1 优化准入为 **{'通过' if admitted else '不通过'}**。"
            "D6 只读取显式绑定的写盘证据，不参与在线控制。"
        ),
        (
            f"系统实时性缺口 **{'已关闭' if realtime else '未关闭'}**。"
            "该矩阵属于三维质点证据，不包含 AirSim 或目标硬件运行结果。"
        ),
        "",
        "## 矩阵",
        "",
        "| 组别 | seed | 世界时间 | 语义通过 |",
        "| --- | --- | ---: | ---: |",
    ]
    for group in (_SHORT_GROUP, _LONG_GROUP):
        group_result = result.get("groups", {}).get(group, {})
        seeds = ",".join(
            str(seed) for seed in group_result.get("seeds", [])
        )
        lines.append(
            f"| {group} | {seeds or '-'} | "
            f"{_fmt(group_result.get('duration_s'))} s | "
            f"{group_result.get('semantic_pass_count', 0)}/"
            f"{group_result.get('pair_count', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 分组性能",
            "",
            "| 组别 | 指标 | 参考均值 | 候选均值 | 均值改善 | 更快 seed | 配对变化 bootstrap 95% CI |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    labels = {
        "d1_fusion_wall_s": "D1 融合累计墙钟",
        "d1_fusion_p95_ms": "D1 融合单次 P95",
        "core_wall_s": "核心 episode 墙钟",
        "external_elapsed_s": "外部进程 elapsed",
        "maximum_rss_kib": "最大常驻内存",
        "real_time_factor": "实时因子",
    }
    for group in (_SHORT_GROUP, _LONG_GROUP):
        metrics = (
            result.get("groups", {})
            .get(group, {})
            .get("metrics", {})
        )
        for metric, label in labels.items():
            summary = metrics.get(metric, {})
            if summary.get("availability") != "available":
                lines.append(
                    f"| {group} | {label} | unavailable | unavailable | "
                    f"unavailable | - | {summary.get('reason') or '-'} |"
                )
                continue
            ci = summary["paired_relative_change_pct"][
                "bootstrap_95_ci"
            ]
            lines.append(
                f"| {group} | {label} | "
                f"{_fmt(summary['reference']['mean'])} | "
                f"{_fmt(summary['candidate']['mean'])} | "
                f"{_fmt(summary['mean_improvement_pct'])}% | "
                f"{summary['candidate_lower_count']}/"
                f"{summary['pair_count']} | "
                f"[{_fmt(ci['lower'])}, {_fmt(ci['upper'])}]% |"
            )
    lines.extend(
        [
            "",
            "核心 episode 墙钟与外部进程 elapsed 分层报告，二者没有相加。"
            "组内 P95 使用线性插值；bootstrap 以显式 seed pair 为重采样单位，随机种子和重采样次数固定。",
            "",
            "## 长短单位时间增长",
            "",
            "| 指标 | 同 seed 数 | reference 增长比均值 | candidate 增长比均值 | 最大相对恶化 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric, summary in result.get(
        "long_short_unit_cost_growth", {}
    ).get("metrics", {}).items():
        if summary.get("availability") != "available":
            lines.append(
                f"| {metric} | 0 | unavailable | unavailable | "
                f"{summary.get('reason') or '-'} |"
            )
            continue
        lines.append(
            f"| {metric} | {summary['seed_count']} | "
            f"{_fmt(summary['reference_growth_ratio']['mean'])} | "
            f"{_fmt(summary['candidate_growth_ratio']['mean'])} | "
            f"{_fmt(summary['maximum_candidate_relative_degradation_pct'])}% |"
        )
    lines.extend(
        [
            "",
            "增长比按同一 seed 的 `(long_cost/long_duration) / "
            "(short_cost/short_duration)` 计算。candidate 相对 reference 的增长恶化单独计算。",
            "",
            "## 准入门",
            "",
            "| 判据 | 结果 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    for name, gate in result.get("admission_gates", {}).items():
        lines.append(
            f"| `{name}` | {'通过' if gate.get('passed') else '失败'} | "
            f"{gate.get('reason') or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- short 与 long 均为三维质点 clean A/B，不代表 AirSim 或实机容量。",
            "- 系统实时性只有在目标运行环境证据和全部实时门同时满足时才能关闭。",
            "- 本报告不计算均方根误差、归一化估计误差平方或归一化创新平方。",
            "",
        ]
    )
    return "\n".join(lines)


def _evaluate_matrix_pair(
    pair: D1CovarianceLimitMatrixPairInput,
    *,
    registration: D1CovarianceLimitMatrixRegistration,
    expected_reference_commit: str,
    expected_candidate_commit: str,
) -> dict[str, Any]:
    base = evaluate_d1_covariance_limit_explicit_pair(
        pair.clean_pair_input(),
        expected_reference_commit=expected_reference_commit,
        expected_candidate_commit=expected_candidate_commit,
        expected_observation_count=None,
        expected_target_count=registration.target_count,
        expected_resource_count=registration.resource_count,
        expected_recon_count=registration.recon_count,
        expected_duration_s=pair.duration_s,
    )
    reference = base["reference"]
    candidate = base["candidate"]
    expected_duration = registration.duration_for(pair.group)
    checks = {
        "group_registered": _gate(
            bool(registration.seeds_for(pair.group)),
            "group_not_registered",
        ),
        "seed_registered_for_group": _gate(
            pair.seed in registration.seeds_for(pair.group),
            "seed_not_registered_for_group",
        ),
        "duration_registered_for_group": _gate(
            expected_duration is not None
            and math.isclose(
                pair.duration_s,
                expected_duration,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ),
            "duration_not_registered_for_group",
        ),
        "explicit_seed_matches_evidence": _gate(
            reference["provenance"].get("seed") == pair.seed
            and candidate["provenance"].get("seed") == pair.seed,
            "explicit_seed_does_not_match_episode",
        ),
        "explicit_duration_matches_evidence": _gate(
            _finite_close(
                reference["provenance"].get("simulated_duration_s"),
                pair.duration_s,
            )
            and _finite_close(
                candidate["provenance"].get("simulated_duration_s"),
                pair.duration_s,
            ),
            "explicit_duration_does_not_match_episode",
        ),
        "structural_ambiguity_hold_enabled": _gate(
            (
                reference["provenance"].get(
                    "d1_d2_structural_ambiguity_hold_enabled"
                )
                is True
            )
            and (
                candidate["provenance"].get(
                    "d1_d2_structural_ambiguity_hold_enabled"
                )
                is True
            ),
            "d1_d2_structural_ambiguity_hold_not_enabled",
        ),
        "runtime_profile_matches_preregistered_digest": _gate(
            (
                reference["provenance"].get("runtime_profile_sha256")
                == registration.runtime_profile_sha256
            )
            and (
                candidate["provenance"].get("runtime_profile_sha256")
                == registration.runtime_profile_sha256
            ),
            "runtime_profile_sha256_not_preregistered_value",
        ),
    }
    base.update(
        {
            "group": pair.group,
            "seed": pair.seed,
            "duration_s": pair.duration_s,
            "matrix_key": f"{pair.group}:{pair.seed}",
            "matrix_registration_checks": checks,
            "matrix_semantics_passed": (
                bool(base["business_semantics_passed"])
                and all(check["passed"] for check in checks.values())
            ),
        }
    )
    return base


def _registration_checks(
    pairs: Sequence[Mapping[str, Any]],
    *,
    registration: D1CovarianceLimitMatrixRegistration,
) -> dict[str, dict[str, Any]]:
    keys = [(str(pair["group"]), int(pair["seed"])) for pair in pairs]
    expected_keys = registration.expected_keys()
    normalized_configs = [
        arm["provenance"].get(
            "normalized_config_excluding_seed_duration_sha256"
        )
        for pair in pairs
        for arm in (pair["reference"], pair["candidate"])
    ]
    runtime_profiles = [
        arm["provenance"].get("runtime_profile_sha256")
        for pair in pairs
        for arm in (pair["reference"], pair["candidate"])
    ]
    return {
        "matrix_keys_unique": _gate(
            len(keys) == len(set(keys)),
            "duplicate_group_seed_pair",
        ),
        "matrix_exactly_preregistered": _gate(
            set(keys) == expected_keys and len(keys) == len(expected_keys),
            "matrix_missing_or_extra_preregistered_pair",
        ),
        "all_pair_semantics_passed": _gate(
            bool(pairs)
            and all(bool(pair["matrix_semantics_passed"]) for pair in pairs),
            "one_or_more_pair_semantic_checks_failed",
        ),
        "config_equal_excluding_seed_duration": _gate(
            bool(normalized_configs)
            and all(value is not None for value in normalized_configs)
            and len(set(normalized_configs)) == 1,
            "normalized_scenario_config_mismatch",
        ),
        "runtime_profile_common": _gate(
            bool(runtime_profiles)
            and all(value is not None for value in runtime_profiles)
            and len(set(runtime_profiles)) == 1,
            "runtime_profile_mismatch_across_matrix",
        ),
        "runtime_profile_preregistered": _gate(
            bool(runtime_profiles)
            and all(
                value == registration.runtime_profile_sha256
                for value in runtime_profiles
            ),
            "runtime_profile_not_preregistered_digest",
        ),
        "structural_ambiguity_hold_all_arms": _gate(
            bool(pairs)
            and all(
                arm["provenance"].get(
                    "d1_d2_structural_ambiguity_hold_enabled"
                )
                is True
                for pair in pairs
                for arm in (pair["reference"], pair["candidate"])
            ),
            "structural_ambiguity_hold_missing_or_false",
        ),
    }


def _summarize_group(
    pairs: Sequence[Mapping[str, Any]],
    *,
    group: str,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    ordered = sorted(pairs, key=lambda item: int(item["seed"]))
    durations = {float(pair["duration_s"]) for pair in ordered}
    return {
        "group": group,
        "pair_count": len(ordered),
        "seeds": [int(pair["seed"]) for pair in ordered],
        "duration_s": next(iter(durations)) if len(durations) == 1 else None,
        "semantic_pass_count": sum(
            bool(pair["matrix_semantics_passed"]) for pair in ordered
        ),
        "metrics": {
            metric: _summarize_group_metric(
                ordered,
                metric=metric,
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=_derived_bootstrap_seed(
                    bootstrap_rng_seed, group, metric
                ),
            )
            for metric in _METRICS
        },
    }


def _summarize_group_metric(
    pairs: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    comparisons = [pair["performance"][metric] for pair in pairs]
    if not comparisons:
        return _unavailable_summary("group_has_no_pairs")
    unavailable = [
        str(item.get("reason") or "pair_metric_unavailable")
        for item in comparisons
        if item.get("availability") != "available"
    ]
    if unavailable:
        return _unavailable_summary(";".join(unavailable))
    reference = [float(item["reference"]) for item in comparisons]
    candidate = [float(item["candidate"]) for item in comparisons]
    paired_changes = [
        float(item["relative_change_pct"])
        for item in comparisons
        if item.get("relative_change_pct") is not None
    ]
    if len(paired_changes) != len(comparisons):
        return _unavailable_summary("paired_relative_change_unavailable")
    reference_mean = fmean(reference)
    candidate_mean = fmean(candidate)
    mean_relative_change = (
        (candidate_mean - reference_mean) / reference_mean * 100.0
        if reference_mean != 0.0
        else None
    )
    if mean_relative_change is None:
        return _unavailable_summary("reference_mean_is_zero")
    ci_lower, ci_upper = _bootstrap_mean_ci(
        paired_changes,
        resamples=bootstrap_resamples,
        rng_seed=bootstrap_rng_seed,
    )
    return {
        "availability": "available",
        "reason": None,
        "pair_count": len(comparisons),
        "reference": _distribution(reference),
        "candidate": _distribution(candidate),
        "candidate_lower_count": sum(
            candidate_value < reference_value
            for reference_value, candidate_value in zip(
                reference, candidate, strict=True
            )
        ),
        "mean_relative_change_pct": mean_relative_change,
        "mean_improvement_pct": -mean_relative_change,
        "paired_relative_change_pct": {
            **_distribution(paired_changes),
            "values": paired_changes,
            "bootstrap_95_ci": {
                "lower": ci_lower,
                "upper": ci_upper,
                "resamples": bootstrap_resamples,
                "rng_seed": bootstrap_rng_seed,
            },
        },
    }


def _summarize_long_short_growth(
    pairs: Sequence[Mapping[str, Any]],
    *,
    registration: D1CovarianceLimitMatrixRegistration,
) -> dict[str, Any]:
    pair_map: dict[tuple[str, int], Mapping[str, Any]] = {}
    duplicate_keys: set[tuple[str, int]] = set()
    for pair in pairs:
        key = (str(pair["group"]), int(pair["seed"]))
        if key in pair_map:
            duplicate_keys.add(key)
        else:
            pair_map[key] = pair
    common_seeds = sorted(
        set(registration.short_seeds) & set(registration.long_seeds)
    )
    return {
        "same_seed_required": True,
        "common_seeds": common_seeds,
        "core_wall_and_external_elapsed_summed": False,
        "metrics": {
            metric: _growth_metric(
                pair_map,
                duplicate_keys=duplicate_keys,
                common_seeds=common_seeds,
                metric=metric,
            )
            for metric in _GROWTH_METRICS
        },
    }


def _growth_metric(
    pair_map: Mapping[tuple[str, int], Mapping[str, Any]],
    *,
    duplicate_keys: set[tuple[str, int]],
    common_seeds: Sequence[int],
    metric: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for seed in common_seeds:
        short_key = (_SHORT_GROUP, seed)
        long_key = (_LONG_GROUP, seed)
        if (
            short_key in duplicate_keys
            or long_key in duplicate_keys
            or short_key not in pair_map
            or long_key not in pair_map
        ):
            return _unavailable_growth(
                f"missing_or_duplicate_same_seed_pair:{seed}"
            )
        short = pair_map[short_key]
        long = pair_map[long_key]
        short_comparison = short["performance"][metric]
        long_comparison = long["performance"][metric]
        if (
            short_comparison.get("availability") != "available"
            or long_comparison.get("availability") != "available"
        ):
            return _unavailable_growth(
                f"growth_metric_unavailable:{metric}:seed:{seed}"
            )
        short_duration = float(short["duration_s"])
        long_duration = float(long["duration_s"])
        reference_short = float(short_comparison["reference"])
        candidate_short = float(short_comparison["candidate"])
        reference_long = float(long_comparison["reference"])
        candidate_long = float(long_comparison["candidate"])
        values = (
            short_duration,
            long_duration,
            reference_short,
            candidate_short,
            reference_long,
            candidate_long,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            return _unavailable_growth(
                f"growth_metric_nonpositive_or_nonfinite:{metric}:seed:{seed}"
            )
        reference_growth = (
            reference_long / long_duration
        ) / (reference_short / short_duration)
        candidate_growth = (
            candidate_long / long_duration
        ) / (candidate_short / short_duration)
        relative_degradation = (
            (candidate_growth / reference_growth) - 1.0
        ) * 100.0
        records.append(
            {
                "seed": seed,
                "reference_short_cost_per_sim_second": (
                    reference_short / short_duration
                ),
                "reference_long_cost_per_sim_second": (
                    reference_long / long_duration
                ),
                "candidate_short_cost_per_sim_second": (
                    candidate_short / short_duration
                ),
                "candidate_long_cost_per_sim_second": (
                    candidate_long / long_duration
                ),
                "reference_growth_ratio": reference_growth,
                "candidate_growth_ratio": candidate_growth,
                "candidate_relative_degradation_pct": (
                    relative_degradation
                ),
            }
        )
    reference_growth_values = [
        float(record["reference_growth_ratio"]) for record in records
    ]
    candidate_growth_values = [
        float(record["candidate_growth_ratio"]) for record in records
    ]
    degradation_values = [
        float(record["candidate_relative_degradation_pct"])
        for record in records
    ]
    return {
        "availability": "available",
        "reason": None,
        "seed_count": len(records),
        "records": records,
        "reference_growth_ratio": _distribution(reference_growth_values),
        "candidate_growth_ratio": _distribution(candidate_growth_values),
        "candidate_relative_degradation_pct": _distribution(
            degradation_values
        ),
        "maximum_candidate_relative_degradation_pct": max(
            degradation_values
        ),
    }


def _admission_gates(
    pairs: Sequence[Mapping[str, Any]],
    *,
    groups: Mapping[str, Mapping[str, Any]],
    growth: Mapping[str, Any],
    registration_checks: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    short_fusion = groups[_SHORT_GROUP]["metrics"][
        "d1_fusion_wall_s"
    ]
    short_fusion_p95 = groups[_SHORT_GROUP]["metrics"][
        "d1_fusion_p95_ms"
    ]
    long_fusion = groups[_LONG_GROUP]["metrics"]["d1_fusion_wall_s"]
    fusion_growth = growth["metrics"]["d1_fusion_wall_s"]
    arm_checks = [
        arm["checks"]
        for pair in pairs
        for arm in (pair["reference"], pair["candidate"])
    ]
    rss_pair_changes = [
        float(pair["performance"]["maximum_rss_kib"]["relative_change_pct"])
        for pair in pairs
        if pair["performance"]["maximum_rss_kib"].get("availability")
        == "available"
        and pair["performance"]["maximum_rss_kib"].get(
            "relative_change_pct"
        )
        is not None
    ]
    registration_passed = all(
        check["passed"] for check in registration_checks.values()
    )
    return {
        "preregistered_matrix_complete": _gate(
            registration_passed,
            "one_or_more_matrix_registration_checks_failed",
        ),
        "semantic_truth_exit_all_passed": _gate(
            bool(pairs)
            and all(bool(pair["matrix_semantics_passed"]) for pair in pairs)
            and all(
                checks["summary_numeric_values_finite"]["passed"]
                and checks["finite_state_true"]["passed"]
                and checks["online_truth_use_zero"]["passed"]
                and checks["process_exit_zero"]["passed"]
                for checks in arm_checks
            ),
            "semantic_finite_truth_or_exit_check_failed",
        ),
        "short_fusion_at_least_eight_of_ten_faster": _gate(
            _summary_available(short_fusion)
            and short_fusion["candidate_lower_count"]
            >= D1_COVARIANCE_LIMIT_MINIMUM_SHORT_FASTER_COUNT,
            "short_d1_fusion_faster_count_below_eight",
        ),
        "short_fusion_mean_improvement_at_least_five_percent": _gate(
            _summary_available(short_fusion)
            and short_fusion["mean_improvement_pct"]
            >= D1_COVARIANCE_LIMIT_MINIMUM_MEAN_IMPROVEMENT_PCT,
            "short_d1_fusion_mean_improvement_below_five_percent",
        ),
        "short_fusion_paired_bootstrap_ci_upper_below_zero": _gate(
            _summary_available(short_fusion)
            and short_fusion["paired_relative_change_pct"][
                "bootstrap_95_ci"
            ]["upper"]
            < 0.0,
            "short_d1_fusion_bootstrap_ci_upper_not_below_zero",
        ),
        "short_fusion_p95_aggregate_improved": _gate(
            _summary_available(short_fusion_p95)
            and short_fusion_p95["candidate"]["p95"]
            < short_fusion_p95["reference"]["p95"],
            "short_d1_fusion_p95_aggregate_not_improved",
        ),
        "long_fusion_at_least_two_of_three_faster": _gate(
            _summary_available(long_fusion)
            and long_fusion["candidate_lower_count"]
            >= D1_COVARIANCE_LIMIT_MINIMUM_LONG_FASTER_COUNT,
            "long_d1_fusion_faster_count_below_two",
        ),
        "long_fusion_mean_improvement_at_least_five_percent": _gate(
            _summary_available(long_fusion)
            and long_fusion["mean_improvement_pct"]
            >= D1_COVARIANCE_LIMIT_MINIMUM_MEAN_IMPROVEMENT_PCT,
            "long_d1_fusion_mean_improvement_below_five_percent",
        ),
        "candidate_long_short_unit_cost_growth_not_over_five_percent": _gate(
            fusion_growth.get("availability") == "available"
            and fusion_growth[
                "maximum_candidate_relative_degradation_pct"
            ]
            <= D1_COVARIANCE_LIMIT_MAXIMUM_DEGRADATION_PCT,
            "candidate_d1_unit_cost_growth_degraded_over_five_percent",
        ),
        "core_wall_group_means_not_degraded_over_five_percent": _gate(
            all(
                _group_mean_change_within_limit(
                    groups[group]["metrics"]["core_wall_s"]
                )
                for group in (_SHORT_GROUP, _LONG_GROUP)
            ),
            "core_wall_group_mean_degraded_over_five_percent",
        ),
        "rss_group_means_not_degraded_over_five_percent": _gate(
            all(
                _group_mean_change_within_limit(
                    groups[group]["metrics"]["maximum_rss_kib"]
                )
                for group in (_SHORT_GROUP, _LONG_GROUP)
            ),
            "rss_group_mean_degraded_over_five_percent",
        ),
        "every_rss_pair_not_degraded_over_five_percent": _gate(
            len(rss_pair_changes) == len(pairs)
            and all(
                change <= D1_COVARIANCE_LIMIT_MAXIMUM_DEGRADATION_PCT
                for change in rss_pair_changes
            ),
            "one_or_more_rss_pairs_degraded_over_five_percent",
        ),
    }


def _point_mass_realtime_conditions(
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_rtfs = [
        pair["candidate"]["metrics"]["real_time_factor"]
        for pair in pairs
    ]
    available = bool(candidate_rtfs) and all(
        metric.get("availability") == "available"
        for metric in candidate_rtfs
    )
    minimum = (
        min(float(metric["value"]) for metric in candidate_rtfs)
        if available
        else None
    )
    return {
        "passed": bool(available and minimum is not None and minimum >= 1.0),
        "all_candidate_real_time_factors_available": available,
        "minimum_candidate_real_time_factor": minimum,
        "threshold": 1.0,
        "reason": (
            None
            if available and minimum is not None and minimum >= 1.0
            else "one_or_more_candidate_real_time_factors_below_one_or_unavailable"
        ),
    }


def _group_mean_change_within_limit(summary: Mapping[str, Any]) -> bool:
    return (
        _summary_available(summary)
        and float(summary["mean_relative_change_pct"])
        <= D1_COVARIANCE_LIMIT_MAXIMUM_DEGRADATION_PCT
    )


def _write_pair_csv(result: Mapping[str, Any], path: Path) -> None:
    fieldnames = [
        "group",
        "seed",
        "duration_s",
        "matrix_semantics_passed",
        "reference_episode_dir",
        "candidate_episode_dir",
        "reference_git_commit",
        "candidate_git_commit",
    ]
    for metric in _METRICS:
        fieldnames.extend(
            (
                f"{metric}__reference",
                f"{metric}__candidate",
                f"{metric}__paired_relative_change_pct",
                f"{metric}__availability",
                f"{metric}__reason",
            )
        )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for pair in result.get("pairs", []):
            row: dict[str, Any] = {
                "group": pair["group"],
                "seed": pair["seed"],
                "duration_s": pair["duration_s"],
                "matrix_semantics_passed": pair[
                    "matrix_semantics_passed"
                ],
                "reference_episode_dir": pair["reference"]["episode_dir"],
                "candidate_episode_dir": pair["candidate"]["episode_dir"],
                "reference_git_commit": pair["reference"][
                    "provenance"
                ].get("git_commit"),
                "candidate_git_commit": pair["candidate"][
                    "provenance"
                ].get("git_commit"),
            }
            for metric in _METRICS:
                comparison = pair["performance"][metric]
                row.update(
                    {
                        f"{metric}__reference": comparison.get("reference"),
                        f"{metric}__candidate": comparison.get("candidate"),
                        f"{metric}__paired_relative_change_pct": (
                            comparison.get("relative_change_pct")
                        ),
                        f"{metric}__availability": comparison.get(
                            "availability"
                        ),
                        f"{metric}__reason": comparison.get("reason"),
                    }
                )
            writer.writerow(row)


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("distribution requires at least one value")
    return {
        "mean": fmean(values),
        "median": float(median(values)),
        "p95": _percentile(values, 0.95),
        "minimum": min(values),
        "maximum": max(values),
    }


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    resamples: int,
    rng_seed: int,
) -> tuple[float, float]:
    if not values:
        raise ValueError("bootstrap requires at least one paired value")
    rng = random.Random(rng_seed)
    sample_count = len(values)
    means = [
        fmean(values[rng.randrange(sample_count)] for _ in range(sample_count))
        for _ in range(resamples)
    ]
    return (_percentile(means, 0.025), _percentile(means, 0.975))


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if quantile < 0.0 or quantile > 1.0:
        raise ValueError("quantile must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return (
        ordered[lower_index] * (1.0 - weight)
        + ordered[upper_index] * weight
    )


def _derived_bootstrap_seed(base: int, group: str, metric: str) -> int:
    digest = hashlib.sha256(
        f"{base}:{group}:{metric}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _unavailable_summary(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "reason": str(reason),
        "pair_count": 0,
        "reference": None,
        "candidate": None,
        "candidate_lower_count": None,
        "mean_relative_change_pct": None,
        "mean_improvement_pct": None,
        "paired_relative_change_pct": None,
    }


def _unavailable_growth(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "reason": str(reason),
        "seed_count": 0,
        "records": [],
        "reference_growth_ratio": None,
        "candidate_growth_ratio": None,
        "candidate_relative_degradation_pct": None,
        "maximum_candidate_relative_degradation_pct": None,
    }


def _summary_available(summary: Mapping[str, Any]) -> bool:
    return summary.get("availability") == "available"


def _gate(passed: bool, reason: str) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "reason": None if passed else str(reason),
    }


def _known_matrix_registration(
    experiment_id: str,
) -> D1CovarianceLimitKnownMatrixRegistration:
    registration = _KNOWN_MATRIX_REGISTRATIONS.get(experiment_id)
    if registration is None:
        raise D1CovarianceLimitEvidenceManifestError(
            f"unsupported evidence manifest experiment_id: {experiment_id!r}"
        )
    return registration


def _validate_embedded_matrix(
    matrix: Mapping[str, Any],
    *,
    known_registration: D1CovarianceLimitKnownMatrixRegistration,
) -> None:
    _manifest_equal(
        matrix.get("schema_version"),
        D1_COVARIANCE_LIMIT_MATRIX_SCHEMA_VERSION,
        "embedded matrix schema_version",
    )
    _manifest_equal(
        matrix.get("experiment_id"),
        known_registration.experiment_id,
        "embedded matrix experiment_id",
    )
    _manifest_equal(
        matrix.get("reference_commit"),
        known_registration.reference_commit,
        "embedded matrix reference_commit",
    )
    _manifest_equal(
        matrix.get("candidate_commit"),
        known_registration.candidate_commit,
        "embedded matrix candidate_commit",
    )
    for field in (
        "reference_base_commit",
        "candidate_base_commit",
        "common_d2_fix_source_commit",
        "common_d2_fix_subject",
        "common_d1_psd_fix_source_commit",
        "common_d1_psd_fix_subject",
        "reference_treatment_commit",
        "reference_treatment_subject",
    ):
        expected = getattr(known_registration, field)
        if expected is None:
            if field in matrix:
                raise D1CovarianceLimitEvidenceManifestError(
                    f"embedded matrix {field} must be absent for "
                    f"{known_registration.experiment_id}"
                )
            continue
        _manifest_equal(
            matrix.get(field),
            expected,
            f"embedded matrix {field}",
        )
    for field, expected in (
        ("target_count", 200),
        ("resource_count", 200),
        ("recon_count", 2),
    ):
        _manifest_equal(
            _manifest_integer(matrix.get(field), f"embedded matrix {field}"),
            expected,
            f"embedded matrix {field}",
        )
    run_flags = _manifest_sequence(
        matrix.get("run_flags"),
        "embedded matrix run_flags",
    )
    _manifest_equal(
        tuple(run_flags),
        D1_COVARIANCE_LIMIT_RUN_FLAGS,
        "embedded matrix run_flags",
    )
    _manifest_equal(
        matrix.get("runtime_profile_sha256"),
        D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256,
        "embedded matrix runtime_profile_sha256",
    )
    _manifest_equal(
        _manifest_number(
            matrix.get("cooldown_s"),
            "embedded matrix cooldown_s",
        ),
        2.0,
        "embedded matrix cooldown_s",
    )
    _manifest_equal(
        _manifest_integer(
            matrix.get("bootstrap_seed"),
            "embedded matrix bootstrap_seed",
        ),
        D1_COVARIANCE_LIMIT_BOOTSTRAP_RNG_SEED,
        "embedded matrix bootstrap_seed",
    )
    _manifest_equal(
        _manifest_integer(
            matrix.get("bootstrap_resamples"),
            "embedded matrix bootstrap_resamples",
        ),
        D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES,
        "embedded matrix bootstrap_resamples",
    )
    admission_gates = _manifest_mapping(
        matrix.get("admission_gates"),
        "embedded matrix admission_gates",
    )
    _manifest_equal(
        dict(admission_gates),
        _EXPECTED_ADMISSION_GATES,
        "embedded matrix admission_gates",
    )
    evidence_boundary = _manifest_mapping(
        matrix.get("evidence_boundary"),
        "embedded matrix evidence_boundary",
    )
    expected_evidence_boundary = dict(_EXPECTED_EVIDENCE_BOUNDARY)
    if known_registration.v1_outputs_reused is not None:
        expected_evidence_boundary["v1_outputs_reused"] = (
            known_registration.v1_outputs_reused
        )
    if known_registration.v2_outputs_reused is not None:
        expected_evidence_boundary.update(
            {
                "v2_outputs_reused": (
                    known_registration.v2_outputs_reused
                ),
                "reference_vectorized_covariance_limit": (
                    known_registration.reference_vectorized_covariance_limit
                ),
                "candidate_vectorized_covariance_limit": (
                    known_registration.candidate_vectorized_covariance_limit
                ),
            }
        )
    _manifest_equal(
        dict(evidence_boundary),
        expected_evidence_boundary,
        "embedded matrix evidence_boundary",
    )
    cases = _manifest_sequence(
        matrix.get("cases"),
        "embedded matrix cases",
    )
    normalized = tuple(
        _normalized_manifest_case(
            _manifest_mapping(case, "embedded matrix case")
        )
        for case in cases
    )
    _manifest_equal(
        normalized,
        _EXPECTED_CASES,
        "embedded matrix cases",
    )


def _normalized_manifest_case(
    case: Mapping[str, Any],
) -> tuple[str, str, int, float, tuple[str, ...]]:
    case_id = _manifest_text(case.get("case_id"), "case_id")
    group = _manifest_text(case.get("group"), f"{case_id} group")
    seed = _manifest_integer(case.get("seed"), f"{case_id} seed")
    duration_s = _manifest_number(
        case.get("duration_s"),
        f"{case_id} duration_s",
    )
    arm_order = _manifest_sequence(
        case.get("arm_order"),
        f"{case_id} arm_order",
    )
    if any(
        not isinstance(arm, str) or not arm.strip()
        for arm in arm_order
    ):
        raise D1CovarianceLimitEvidenceManifestError(
            f"{case_id} arm_order must contain string labels"
        )
    return (
        case_id,
        group,
        seed,
        duration_s,
        tuple(arm_order),
    )


def _manifest_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} must be a JSON object"
        )
    return value


def _manifest_sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes),
    ):
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} must be a JSON array"
        )
    return value


def _manifest_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} must be a non-empty string"
        )
    return value.strip()


def _manifest_integer(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} must be an integer"
        )
    return value


def _manifest_number(value: Any, context: str) -> float:
    if not _is_finite_number(value):
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} must be finite"
        )
    return float(value)


def _manifest_equal(actual: Any, expected: Any, context: str) -> None:
    if actual != expected:
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} mismatch: expected {expected!r}, got {actual!r}"
        )


def _manifest_explicit_path(
    value: Any,
    context: str,
    *,
    base: Path,
    require: str,
) -> Path:
    raw = _manifest_text(value, context)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    path = candidate.resolve()
    if require == "file" and not path.is_file():
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} is not an existing file: {path}"
        )
    if require == "directory" and not path.is_dir():
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} is not an existing directory: {path}"
        )
    return path


def _require_under_output_root(
    path: Path,
    output_root: Path,
    context: str,
) -> None:
    try:
        path.relative_to(output_root)
    except ValueError as exc:
        raise D1CovarianceLimitEvidenceManifestError(
            f"{context} is outside output_root"
        ) from exc


def _validated_commit(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if not _GIT_COMMIT_RE.fullmatch(normalized):
        raise ValueError(f"{field} must be a 40-character hexadecimal commit")
    return normalized


def _finite_close(value: Any, expected: float) -> bool:
    return (
        _is_finite_number(value)
        and math.isclose(
            float(value),
            float(expected),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    )


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _fmt(value: Any) -> str:
    if not _is_finite_number(value):
        return "unavailable"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _parse_pair_argument(
    values: Sequence[str],
) -> D1CovarianceLimitMatrixPairInput:
    if len(values) != 8:
        raise ValueError("--pair requires exactly 8 values")
    return D1CovarianceLimitMatrixPairInput(
        group=values[0],
        seed=int(values[1]),
        duration_s=float(values[2]),
        reference_episode_dir=Path(values[3]),
        candidate_episode_dir=Path(values[4]),
        reference_resource_path=Path(values[5]),
        candidate_resource_path=Path(values[6]),
        cross_build_path=Path(values[7]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI for the explicitly registered short/long matrix."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the preregistered D1 covariance-limit short/long matrix"
        )
    )
    parser.add_argument(
        "--reference-commit",
        default=None,
    )
    parser.add_argument(
        "--candidate-commit",
        default=None,
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--evidence-manifest",
        type=Path,
        help=(
            "Completed main-produced evidence_manifest.json with all 13 "
            "explicit cases"
        ),
    )
    input_group.add_argument(
        "--pair",
        action="append",
        nargs=8,
        metavar=(
            "GROUP",
            "SEED",
            "DURATION",
            "REF_EPISODE",
            "CAND_EPISODE",
            "REF_RESOURCE",
            "CAND_RESOURCE",
            "CROSS_JSON",
        ),
        help="Explicit matrix cell; repeat for all 13 preregistered pairs",
    )
    args = parser.parse_args(argv)
    if args.evidence_manifest is not None:
        if (
            args.reference_commit is not None
            or args.candidate_commit is not None
        ):
            parser.error(
                "--evidence-manifest selects commits from its known "
                "experiment registration"
            )
        result = evaluate_d1_covariance_limit_evidence_manifest(
            args.evidence_manifest
        )
    else:
        pairs = [
            _parse_pair_argument(values) for values in (args.pair or [])
        ]
        result = evaluate_d1_covariance_limit_multiseed_long(
            pairs,
            expected_reference_commit=(
                args.reference_commit
                or D1_COVARIANCE_LIMIT_REFERENCE_COMMIT
            ),
            expected_candidate_commit=(
                args.candidate_commit
                or D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT
            ),
        )
        result["input_contract"] = {
            "mode": "explicit_pairs",
            "arm_seed_duration_inferred_from_path": False,
        }
    paths = write_d1_covariance_limit_multiseed_long_report(
        result, args.output_dir
    )
    print(
        json.dumps(
            {
                "d1_optimization_admitted": result[
                    "d1_optimization_admitted"
                ],
                "system_realtime_gap_closed": result[
                    "system_realtime_gap_closed"
                ],
                "outputs": {key: str(path) for key, path in paths.items()},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["d1_optimization_admitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_D1_COVARIANCE_LIMIT_MATRIX_REGISTRATION",
    "D1_COVARIANCE_LIMIT_EVIDENCE_MANIFEST_SCHEMA_VERSION",
    "D1_COVARIANCE_LIMIT_EXPERIMENT_ID",
    "D1_COVARIANCE_LIMIT_MATRIX_SCHEMA_VERSION",
    "D1_COVARIANCE_LIMIT_BOOTSTRAP_RESAMPLES",
    "D1_COVARIANCE_LIMIT_BOOTSTRAP_RNG_SEED",
    "D1_COVARIANCE_LIMIT_CANDIDATE_COMMIT",
    "D1_COVARIANCE_LIMIT_LONG_DURATION_S",
    "D1_COVARIANCE_LIMIT_LONG_SEEDS",
    "D1_COVARIANCE_LIMIT_MULTISEED_LONG_EVALUATION_DATE",
    "D1_COVARIANCE_LIMIT_MULTISEED_LONG_SCHEMA_VERSION",
    "D1_COVARIANCE_LIMIT_REFERENCE_COMMIT",
    "D1_COVARIANCE_LIMIT_RUNTIME_PROFILE_SHA256",
    "D1_COVARIANCE_LIMIT_RUN_FLAGS",
    "D1_COVARIANCE_LIMIT_SHORT_DURATION_S",
    "D1_COVARIANCE_LIMIT_SHORT_SEEDS",
    "D1_COVARIANCE_LIMIT_V1_EXPERIMENT_ID",
    "D1_COVARIANCE_LIMIT_V1_KNOWN_MATRIX_REGISTRATION",
    "D1_COVARIANCE_LIMIT_V2_CANDIDATE_COMMIT",
    "D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SOURCE_COMMIT",
    "D1_COVARIANCE_LIMIT_V2_COMMON_D2_FIX_SUBJECT",
    "D1_COVARIANCE_LIMIT_V2_EXPERIMENT_ID",
    "D1_COVARIANCE_LIMIT_V2_KNOWN_MATRIX_REGISTRATION",
    "D1_COVARIANCE_LIMIT_V2_REFERENCE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_CANDIDATE_BASE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_CANDIDATE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SOURCE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_COMMON_D1_PSD_FIX_SUBJECT",
    "D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SOURCE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_COMMON_D2_FIX_SUBJECT",
    "D1_COVARIANCE_LIMIT_V3_EXPERIMENT_ID",
    "D1_COVARIANCE_LIMIT_V3_KNOWN_MATRIX_REGISTRATION",
    "D1_COVARIANCE_LIMIT_V3_REFERENCE_BASE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_REFERENCE_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_COMMIT",
    "D1_COVARIANCE_LIMIT_V3_REFERENCE_TREATMENT_SUBJECT",
    "D1CovarianceLimitEvidenceManifest",
    "D1CovarianceLimitEvidenceManifestError",
    "D1CovarianceLimitKnownMatrixRegistration",
    "D1CovarianceLimitMatrixPairInput",
    "D1CovarianceLimitMatrixRegistration",
    "evaluate_d1_covariance_limit_evidence_manifest",
    "evaluate_d1_covariance_limit_multiseed_long",
    "load_d1_covariance_limit_evidence_manifest",
    "render_d1_covariance_limit_multiseed_long_markdown",
    "write_d1_covariance_limit_multiseed_long_report",
]
