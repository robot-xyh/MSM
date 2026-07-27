"""Human-approved, fail-closed authorization for G1 shadow scoring.

The D5 v5 bundle proves evidence eligibility but deliberately grants no
runtime authority.  This main-owned contract permits a narrower experiment:
the model may score already-built anonymous candidate edges while the
deterministic D5 association remains authoritative.  The authorization never
permits identity ownership, assignment, failover, camera commands, or control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


G1_SHADOW_REQUEST_ENVELOPE_SCHEMA = (
    "scalable3d-g1-shadow-authorization-request-envelope-v1"
)
G1_SHADOW_REQUEST_SCHEMA = "scalable3d-g1-shadow-authorization-request-v1"
G1_SHADOW_AUTHORIZATION_SCHEMA = "scalable3d-g1-shadow-authorization-v1"
G1_SHADOW_AUTHORIZATION_BINDING_SCHEMA = (
    "scalable3d-g1-shadow-authorization-binding-v1"
)
G1_SHADOW_REVOCATION_REGISTRY_SCHEMA = (
    "scalable3d-g1-shadow-authorization-revocations-v1"
)
G1_SHADOW_APPROVAL_CONFIRMATION = "APPROVE G1 SHADOW SCORING ONLY"
G1_SHADOW_PERMISSION_FIELDS = (
    "g1_shadow_edge_scoring_granted",
    "model_output_may_change_online_association",
    "model_promotion_granted",
    "global_track_id_authority_granted",
    "default_path_change_granted",
    "assignment_authority_granted",
    "failover_authority_granted",
    "active_vision_command_authority_granted",
    "control_authority_granted",
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
_AUTHORIZATION_LOADER_TOKEN = object()


class ExperimentAuthorizationError(RuntimeError):
    """Stable fail-closed authorization contract error."""


@dataclass(frozen=True)
class G1ShadowExperimentAuthorization:
    """Validated local authorization for one immutable G1 shadow scope."""

    authorization_id: str
    authorization_file_sha256: str
    request_sha256: str
    source_git_commit: str
    scope: Mapping[str, Any]
    scope_sha256: str
    d5_bundle: Mapping[str, Any]
    device: str
    not_before_utc: str
    expires_at_utc: str
    revocation_registry_id: str
    permissions: Mapping[str, bool]
    approver_id: str
    approved_at_utc: str
    approval_reason: str
    _loader_token: object = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self._loader_token is not _AUTHORIZATION_LOADER_TOKEN:
            raise ExperimentAuthorizationError(
                "experiment authorization must be created by the strict loader"
            )
        _required_identifier(self.authorization_id, "authorization_id")
        _required_sha256(
            self.authorization_file_sha256,
            "authorization_file_sha256",
        )
        _required_sha256(self.request_sha256, "request_sha256")
        _required_git_commit(self.source_git_commit)
        _required_sha256(self.scope_sha256, "scope_sha256")
        scope = _required_mapping(self.scope, "scope")
        canonical_scope = _build_scope(
            scenarios=scope.get("scenarios", ()),
            scales=scope.get("scales", ()),
            seeds=scope.get("seeds", ()),
            duration_s=scope.get("duration_s", 0.0),
        )
        if scope != canonical_scope:
            raise ExperimentAuthorizationError(
                "experiment authorization scope is not canonical"
            )
        if self.scope_sha256 != canonical_scope["scope_sha256"]:
            raise ExperimentAuthorizationError(
                "experiment authorization scope digest mismatch"
            )
        _validate_bundle(self.d5_bundle)
        if not isinstance(self.device, str) or not self.device.strip():
            raise ExperimentAuthorizationError(
                "experiment authorization device is invalid"
            )
        _required_identifier(
            self.revocation_registry_id,
            "revocation_registry_id",
        )
        _validate_permissions(self.permissions)
        if not isinstance(self.approver_id, str) or not self.approver_id.strip():
            raise ExperimentAuthorizationError("approver_id is empty")
        if (
            not isinstance(self.approval_reason, str)
            or not self.approval_reason.strip()
        ):
            raise ExperimentAuthorizationError("approval_reason is empty")
        not_before = _parse_timestamp(
            self.not_before_utc,
            "not_before_utc",
        )
        expires = _parse_timestamp(
            self.expires_at_utc,
            "expires_at_utc",
        )
        approved = _parse_timestamp(
            self.approved_at_utc,
            "approved_at_utc",
        )
        if expires <= not_before:
            raise ExperimentAuthorizationError(
                "experiment authorization validity window is invalid"
            )
        if approved >= expires:
            raise ExperimentAuthorizationError(
                "experiment authorization approval is not before expiry"
            )
        object.__setattr__(
            self,
            "scope",
            MappingProxyType(dict(self.scope)),
        )
        object.__setattr__(
            self,
            "d5_bundle",
            MappingProxyType(dict(self.d5_bundle)),
        )
        object.__setattr__(
            self,
            "permissions",
            MappingProxyType(dict(self.permissions)),
        )

    def binding_payload(self) -> dict[str, Any]:
        """Return the immutable subset embedded in an execution plan."""

        return {
            "schema_version": G1_SHADOW_AUTHORIZATION_BINDING_SCHEMA,
            "authorization_id": self.authorization_id,
            "authorization_file_sha256": self.authorization_file_sha256,
            "request_sha256": self.request_sha256,
            "source_git_commit": self.source_git_commit,
            "scope_sha256": self.scope_sha256,
            "d5_bundle": dict(self.d5_bundle),
            "device": self.device,
            "not_before_utc": self.not_before_utc,
            "expires_at_utc": self.expires_at_utc,
            "revocation_registry_id": self.revocation_registry_id,
            "permissions": dict(self.permissions),
            "approver_id": self.approver_id,
            "approved_at_utc": self.approved_at_utc,
            "approval_reason": self.approval_reason,
        }

    def assert_active(self, *, now_utc: datetime | str | None = None) -> None:
        now = _coerce_now(now_utc)
        not_before = _parse_timestamp(self.not_before_utc, "not_before_utc")
        expires = _parse_timestamp(self.expires_at_utc, "expires_at_utc")
        if now < not_before:
            raise ExperimentAuthorizationError(
                "experiment authorization is not active yet"
            )
        if now >= expires:
            raise ExperimentAuthorizationError(
                "experiment authorization has expired"
            )

    def assert_cell(
        self,
        *,
        variant: str,
        scenario: str,
        scale: int,
        seed: int,
        duration_s: float,
        now_utc: datetime | str | None = None,
    ) -> None:
        """Verify one cell is inside the exact approved shadow scope."""

        self.assert_active(now_utc=now_utc)
        if str(variant).strip().upper() != "G1":
            raise ExperimentAuthorizationError(
                "authorization permits only the G1 shadow variant"
            )
        if scenario not in self.scope["scenarios"]:
            raise ExperimentAuthorizationError(
                "scenario is outside the authorized scope"
            )
        if int(scale) not in self.scope["scales"]:
            raise ExperimentAuthorizationError(
                "scale is outside the authorized scope"
            )
        if int(seed) not in self.scope["seeds"]:
            raise ExperimentAuthorizationError(
                "seed is outside the authorized scope"
            )
        if not math.isclose(
            float(duration_s),
            float(self.scope["duration_s"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ExperimentAuthorizationError(
                "duration differs from the authorized scope"
            )


def shadow_only_permissions() -> dict[str, bool]:
    """Return the only permission map accepted by this contract."""

    return {
        "g1_shadow_edge_scoring_granted": True,
        "model_output_may_change_online_association": False,
        "model_promotion_granted": False,
        "global_track_id_authority_granted": False,
        "default_path_change_granted": False,
        "assignment_authority_granted": False,
        "failover_authority_granted": False,
        "active_vision_command_authority_granted": False,
        "control_authority_granted": False,
    }


def g1_shadow_scope_payload(
    *,
    scenarios: Sequence[str],
    scales: Sequence[int],
    seeds: Sequence[int],
    duration_s: float,
) -> dict[str, Any]:
    """Return the canonical scope representation shared by plans and approvals."""

    return _build_scope(
        scenarios=scenarios,
        scales=scales,
        seeds=seeds,
        duration_s=duration_s,
    )


def build_g1_shadow_authorization_request(
    *,
    authorization_id: str,
    purpose: str,
    source_git_commit: str,
    scenarios: Sequence[str],
    scales: Sequence[int],
    seeds: Sequence[int],
    duration_s: float,
    d5_bundle_manifest_sha256: str,
    d5_bundle_tree_sha256: str,
    d5_weights_sha256: str,
    device: str,
    not_before_utc: datetime | str,
    expires_at_utc: datetime | str,
    revocation_registry_id: str,
) -> dict[str, Any]:
    """Build a pending request; this function does not grant authorization."""

    auth_id = _required_identifier(authorization_id, "authorization_id")
    registry_id = _required_identifier(
        revocation_registry_id,
        "revocation_registry_id",
    )
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be non-empty")
    commit = _required_git_commit(source_git_commit)
    manifest_sha256 = _required_sha256(
        d5_bundle_manifest_sha256,
        "d5_bundle_manifest_sha256",
    )
    tree_sha256 = _required_sha256(
        d5_bundle_tree_sha256,
        "d5_bundle_tree_sha256",
    )
    weights_sha256 = _required_sha256(
        d5_weights_sha256,
        "d5_weights_sha256",
    )
    selected_device = str(device).strip()
    if not selected_device:
        raise ValueError("device must be non-empty")
    not_before = _format_timestamp(not_before_utc, "not_before_utc")
    expires = _format_timestamp(expires_at_utc, "expires_at_utc")
    if _parse_timestamp(expires, "expires_at_utc") <= _parse_timestamp(
        not_before,
        "not_before_utc",
    ):
        raise ValueError("expires_at_utc must be later than not_before_utc")
    scope = _build_scope(
        scenarios=scenarios,
        scales=scales,
        seeds=seeds,
        duration_s=duration_s,
    )
    request = {
        "schema_version": G1_SHADOW_REQUEST_SCHEMA,
        "authorization_id": auth_id,
        "purpose": purpose.strip(),
        "source": {
            "git_commit": commit,
            "repository_dirty": False,
        },
        "scope": scope,
        "d5_bundle": {
            "component": "d5_graph",
            "manifest_sha256": manifest_sha256,
            "tree_sha256": tree_sha256,
            "weights_sha256": weights_sha256,
        },
        "device": selected_device,
        "validity": {
            "not_before_utc": not_before,
            "expires_at_utc": expires,
        },
        "revocation_registry_id": registry_id,
        "requested_permissions": shadow_only_permissions(),
    }
    request_sha256 = canonical_json_sha256(request)
    return {
        "schema_version": G1_SHADOW_REQUEST_ENVELOPE_SCHEMA,
        "request": request,
        "request_sha256": request_sha256,
    }


def write_g1_shadow_authorization_request(
    path: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    """Write a validated pending request without overwriting prior evidence."""

    _validate_request_envelope(payload)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"authorization request already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, payload)
    return destination


def load_g1_shadow_authorization_request(
    path: str | Path,
) -> dict[str, Any]:
    """Load and validate a pending request without granting authority."""

    envelope = _read_json_object(Path(path))
    request = _validate_request_envelope(envelope)
    return {
        "schema_version": G1_SHADOW_REQUEST_ENVELOPE_SCHEMA,
        "request": request,
        "request_sha256": envelope["request_sha256"],
    }


def approve_g1_shadow_authorization_request(
    request_path: str | Path,
    output_path: str | Path,
    *,
    expected_request_sha256: str,
    approver_id: str,
    approval_reason: str,
    confirmation: str,
    approved_at_utc: datetime | str | None = None,
) -> tuple[Path, str]:
    """Create an approval only after explicit digest and phrase confirmation."""

    envelope = _read_json_object(Path(request_path))
    request = _validate_request_envelope(envelope)
    request_sha256 = _required_sha256(
        expected_request_sha256,
        "expected_request_sha256",
    )
    if request_sha256 != envelope["request_sha256"]:
        raise ExperimentAuthorizationError(
            "explicit request digest confirmation does not match"
        )
    if confirmation != G1_SHADOW_APPROVAL_CONFIRMATION:
        raise ExperimentAuthorizationError(
            "G1 shadow approval confirmation phrase mismatch"
        )
    approver = str(approver_id).strip()
    reason = str(approval_reason).strip()
    if not approver:
        raise ValueError("approver_id must be non-empty")
    if not reason:
        raise ValueError("approval_reason must be non-empty")
    approved = _format_timestamp(
        approved_at_utc or datetime.now(timezone.utc),
        "approved_at_utc",
    )
    approved_time = _parse_timestamp(approved, "approved_at_utc")
    expires = _parse_timestamp(
        request["validity"]["expires_at_utc"],
        "expires_at_utc",
    )
    if approved_time >= expires:
        raise ExperimentAuthorizationError(
            "approval timestamp is not earlier than authorization expiry"
        )
    authorization = {
        "schema_version": G1_SHADOW_AUTHORIZATION_SCHEMA,
        "request": request,
        "request_sha256": request_sha256,
        "approval": {
            "state": "approved",
            "approver_id": approver,
            "approved_at_utc": approved,
            "approval_reason": reason,
            "confirmation": G1_SHADOW_APPROVAL_CONFIRMATION,
            "request_sha256": request_sha256,
        },
    }
    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"authorization already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, authorization)
    return destination, sha256_file(destination)


def write_g1_shadow_revocation_registry(
    path: str | Path,
    *,
    registry_id: str,
    updated_at_utc: datetime | str | None = None,
) -> Path:
    """Create an empty mutable revocation registry for one approval domain."""

    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"revocation registry already exists: {destination}")
    payload = {
        "schema_version": G1_SHADOW_REVOCATION_REGISTRY_SCHEMA,
        "registry_id": _required_identifier(registry_id, "registry_id"),
        "updated_at_utc": _format_timestamp(
            updated_at_utc or datetime.now(timezone.utc),
            "updated_at_utc",
        ),
        "revocations": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, payload)
    return destination


def load_g1_shadow_revocation_registry(
    path: str | Path,
) -> dict[str, Any]:
    """Load a revocation registry through the strict canonical validator."""

    payload = _read_json_object(Path(path))
    registry_id, revocations = _validate_revocation_registry(payload)
    return {
        "schema_version": G1_SHADOW_REVOCATION_REGISTRY_SCHEMA,
        "registry_id": registry_id,
        "updated_at_utc": _format_timestamp(
            payload["updated_at_utc"],
            "updated_at_utc",
        ),
        "revocations": revocations,
    }


def revoke_g1_shadow_authorization(
    registry_path: str | Path,
    *,
    authorization_id: str,
    reason: str,
    revoked_at_utc: datetime | str | None = None,
) -> Path:
    """Append one revocation; duplicate or conflicting updates fail closed."""

    path = Path(registry_path)
    payload = _read_json_object(path)
    registry_id, revocations = _validate_revocation_registry(payload)
    auth_id = _required_identifier(authorization_id, "authorization_id")
    if any(item["authorization_id"] == auth_id for item in revocations):
        raise ExperimentAuthorizationError(
            "authorization is already present in the revocation registry"
        )
    reason_value = str(reason).strip()
    if not reason_value:
        raise ValueError("revocation reason must be non-empty")
    revoked = _format_timestamp(
        revoked_at_utc or datetime.now(timezone.utc),
        "revoked_at_utc",
    )
    updated = {
        "schema_version": G1_SHADOW_REVOCATION_REGISTRY_SCHEMA,
        "registry_id": registry_id,
        "updated_at_utc": revoked,
        "revocations": [
            *revocations,
            {
                "authorization_id": auth_id,
                "revoked_at_utc": revoked,
                "reason": reason_value,
            },
        ],
    }
    _write_json_atomic(path, updated)
    return path


def load_g1_shadow_experiment_authorization(
    path: str | Path,
    *,
    expected_authorization_sha256: str,
    revocation_registry_path: str | Path,
    now_utc: datetime | str | None = None,
) -> G1ShadowExperimentAuthorization:
    """Load one approved file, verify its explicit digest, and check revocation."""

    authorization_path = Path(path)
    expected_sha256 = _required_sha256(
        expected_authorization_sha256,
        "expected_authorization_sha256",
    )
    actual_sha256 = sha256_file(authorization_path)
    if actual_sha256 != expected_sha256:
        raise ExperimentAuthorizationError(
            "authorization file digest does not match explicit confirmation"
        )
    payload = _read_json_object(authorization_path)
    if set(payload) != {
        "schema_version",
        "request",
        "request_sha256",
        "approval",
    }:
        raise ExperimentAuthorizationError(
            "authorization file fields are invalid"
        )
    if payload["schema_version"] != G1_SHADOW_AUTHORIZATION_SCHEMA:
        raise ExperimentAuthorizationError(
            "authorization schema is unsupported"
        )
    request = _validate_request(payload.get("request"))
    request_sha256 = _required_sha256(
        payload.get("request_sha256"),
        "request_sha256",
    )
    if canonical_json_sha256(request) != request_sha256:
        raise ExperimentAuthorizationError(
            "authorization request digest mismatch"
        )
    approval = _required_mapping(payload.get("approval"), "approval")
    if set(approval) != {
        "state",
        "approver_id",
        "approved_at_utc",
        "approval_reason",
        "confirmation",
        "request_sha256",
    }:
        raise ExperimentAuthorizationError("approval fields are invalid")
    if approval.get("state") != "approved":
        raise ExperimentAuthorizationError("authorization is not approved")
    if approval.get("confirmation") != G1_SHADOW_APPROVAL_CONFIRMATION:
        raise ExperimentAuthorizationError(
            "authorization confirmation phrase mismatch"
        )
    if approval.get("request_sha256") != request_sha256:
        raise ExperimentAuthorizationError(
            "approval is bound to a different request"
        )
    approver = str(approval.get("approver_id", "")).strip()
    reason = str(approval.get("approval_reason", "")).strip()
    if not approver or not reason:
        raise ExperimentAuthorizationError(
            "approval identity and reason must be non-empty"
        )
    approved_at = _format_timestamp(
        approval.get("approved_at_utc"),
        "approved_at_utc",
    )
    registry_payload = _read_json_object(Path(revocation_registry_path))
    registry_id, revocations = _validate_revocation_registry(
        registry_payload
    )
    if registry_id != request["revocation_registry_id"]:
        raise ExperimentAuthorizationError(
            "revocation registry identity mismatch"
        )
    authorization_id = request["authorization_id"]
    if any(
        item["authorization_id"] == authorization_id
        for item in revocations
    ):
        raise ExperimentAuthorizationError(
            "experiment authorization has been revoked"
        )
    scope = request["scope"]
    grant = G1ShadowExperimentAuthorization(
        authorization_id=authorization_id,
        authorization_file_sha256=actual_sha256,
        request_sha256=request_sha256,
        source_git_commit=request["source"]["git_commit"],
        scope=scope,
        scope_sha256=scope["scope_sha256"],
        d5_bundle=request["d5_bundle"],
        device=request["device"],
        not_before_utc=request["validity"]["not_before_utc"],
        expires_at_utc=request["validity"]["expires_at_utc"],
        revocation_registry_id=registry_id,
        permissions=request["requested_permissions"],
        approver_id=approver,
        approved_at_utc=approved_at,
        approval_reason=reason,
        _loader_token=_AUTHORIZATION_LOADER_TOKEN,
    )
    grant.assert_active(now_utc=now_utc)
    return grant


def validate_authorization_scope_binding(
    authorization: G1ShadowExperimentAuthorization,
    *,
    source_git_commit: str,
    scenarios: Sequence[str],
    scales: Sequence[int],
    seeds: Sequence[int],
    duration_s: float,
    d5_bundle_manifest_sha256: str,
    d5_bundle_tree_sha256: str,
    d5_weights_sha256: str,
    device: str,
    now_utc: datetime | str | None = None,
) -> None:
    """Bind an approval to one exact source, bundle, and experiment scope."""

    authorization.assert_active(now_utc=now_utc)
    if authorization.source_git_commit != _required_git_commit(
        source_git_commit
    ):
        raise ExperimentAuthorizationError(
            "authorization source Git commit mismatch"
        )
    expected_scope = _build_scope(
        scenarios=scenarios,
        scales=scales,
        seeds=seeds,
        duration_s=duration_s,
    )
    if dict(authorization.scope) != expected_scope:
        raise ExperimentAuthorizationError(
            "authorization experiment scope mismatch"
        )
    expected_bundle = {
        "component": "d5_graph",
        "manifest_sha256": _required_sha256(
            d5_bundle_manifest_sha256,
            "d5_bundle_manifest_sha256",
        ),
        "tree_sha256": _required_sha256(
            d5_bundle_tree_sha256,
            "d5_bundle_tree_sha256",
        ),
        "weights_sha256": _required_sha256(
            d5_weights_sha256,
            "d5_weights_sha256",
        ),
    }
    if dict(authorization.d5_bundle) != expected_bundle:
        raise ExperimentAuthorizationError(
            "authorization D5 bundle binding mismatch"
        )
    if authorization.device != str(device).strip():
        raise ExperimentAuthorizationError(
            "authorization learning device mismatch"
        )
    _validate_permissions(authorization.permissions)


def validate_authorization_binding_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly validate an execution-plan authorization binding."""

    value = _required_mapping(payload, "experiment_authorization")
    expected_fields = {
        "schema_version",
        "authorization_id",
        "authorization_file_sha256",
        "request_sha256",
        "source_git_commit",
        "scope_sha256",
        "d5_bundle",
        "device",
        "not_before_utc",
        "expires_at_utc",
        "revocation_registry_id",
        "permissions",
        "approver_id",
        "approved_at_utc",
        "approval_reason",
    }
    if set(value) != expected_fields:
        raise ExperimentAuthorizationError(
            "authorization binding fields are invalid"
        )
    if value["schema_version"] != G1_SHADOW_AUTHORIZATION_BINDING_SCHEMA:
        raise ExperimentAuthorizationError(
            "authorization binding schema is unsupported"
        )
    _required_identifier(value["authorization_id"], "authorization_id")
    _required_sha256(
        value["authorization_file_sha256"],
        "authorization_file_sha256",
    )
    _required_sha256(value["request_sha256"], "request_sha256")
    _required_git_commit(value["source_git_commit"])
    _required_sha256(value["scope_sha256"], "scope_sha256")
    _validate_bundle(value["d5_bundle"])
    if not isinstance(value["device"], str) or not value["device"].strip():
        raise ExperimentAuthorizationError(
            "authorization binding device is invalid"
        )
    not_before = _parse_timestamp(
        value["not_before_utc"],
        "not_before_utc",
    )
    expires = _parse_timestamp(value["expires_at_utc"], "expires_at_utc")
    if expires <= not_before:
        raise ExperimentAuthorizationError(
            "authorization binding validity window is invalid"
        )
    _required_identifier(
        value["revocation_registry_id"],
        "revocation_registry_id",
    )
    _validate_permissions(value["permissions"])
    for name in ("approver_id", "approval_reason"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ExperimentAuthorizationError(
                f"authorization binding {name} is invalid"
            )
    approved = _parse_timestamp(
        value["approved_at_utc"],
        "approved_at_utc",
    )
    if approved >= expires:
        raise ExperimentAuthorizationError(
            "authorization binding approval is not before expiry"
        )
    return dict(value)


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_scope(
    *,
    scenarios: Sequence[str],
    scales: Sequence[int],
    seeds: Sequence[int],
    duration_s: float,
) -> dict[str, Any]:
    scenario_values = tuple(
        dict.fromkeys(str(value).strip().lower() for value in scenarios)
    )
    scale_values = tuple(dict.fromkeys(int(value) for value in scales))
    seed_values = tuple(dict.fromkeys(int(value) for value in seeds))
    duration = float(duration_s)
    if not scenario_values or any(not value for value in scenario_values):
        raise ValueError("authorization scenarios must be non-empty")
    if not scale_values or any(value <= 0 for value in scale_values):
        raise ValueError("authorization scales must be positive")
    if not seed_values or any(value < 0 for value in seed_values):
        raise ValueError("authorization seeds must be non-negative")
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError("authorization duration_s must be finite and positive")
    content = {
        "variants": ["G1"],
        "scenarios": list(scenario_values),
        "scales": list(scale_values),
        "seeds": list(seed_values),
        "duration_s": duration,
        "cell_count": (
            len(scenario_values) * len(scale_values) * len(seed_values)
        ),
    }
    return {
        **content,
        "scope_sha256": canonical_json_sha256(content),
    }


def _validate_request_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _required_mapping(payload, "request_envelope")
    if set(value) != {"schema_version", "request", "request_sha256"}:
        raise ExperimentAuthorizationError(
            "authorization request envelope fields are invalid"
        )
    if value["schema_version"] != G1_SHADOW_REQUEST_ENVELOPE_SCHEMA:
        raise ExperimentAuthorizationError(
            "authorization request envelope schema is unsupported"
        )
    request = _validate_request(value.get("request"))
    request_sha256 = _required_sha256(
        value.get("request_sha256"),
        "request_sha256",
    )
    if canonical_json_sha256(request) != request_sha256:
        raise ExperimentAuthorizationError(
            "authorization request digest mismatch"
        )
    return request


def _validate_request(payload: Any) -> dict[str, Any]:
    request = _required_mapping(payload, "request")
    expected_fields = {
        "schema_version",
        "authorization_id",
        "purpose",
        "source",
        "scope",
        "d5_bundle",
        "device",
        "validity",
        "revocation_registry_id",
        "requested_permissions",
    }
    if set(request) != expected_fields:
        raise ExperimentAuthorizationError(
            "authorization request fields are invalid"
        )
    if request["schema_version"] != G1_SHADOW_REQUEST_SCHEMA:
        raise ExperimentAuthorizationError(
            "authorization request schema is unsupported"
        )
    _required_identifier(request["authorization_id"], "authorization_id")
    if not isinstance(request["purpose"], str) or not request["purpose"].strip():
        raise ExperimentAuthorizationError(
            "authorization request purpose is empty"
        )
    source = _required_mapping(request["source"], "request.source")
    if set(source) != {"git_commit", "repository_dirty"}:
        raise ExperimentAuthorizationError(
            "authorization request source fields are invalid"
        )
    _required_git_commit(source["git_commit"])
    if source["repository_dirty"] is not False:
        raise ExperimentAuthorizationError(
            "authorization request requires repository_dirty=false"
        )
    scope = _required_mapping(request["scope"], "request.scope")
    expected_scope = _build_scope(
        scenarios=scope.get("scenarios", ()),
        scales=scope.get("scales", ()),
        seeds=scope.get("seeds", ()),
        duration_s=scope.get("duration_s", 0.0),
    )
    if scope != expected_scope:
        raise ExperimentAuthorizationError(
            "authorization request scope is not canonical"
        )
    if scope.get("variants") != ["G1"]:
        raise ExperimentAuthorizationError(
            "authorization request permits only G1"
        )
    _validate_bundle(request["d5_bundle"])
    if not isinstance(request["device"], str) or not request["device"].strip():
        raise ExperimentAuthorizationError(
            "authorization request device is invalid"
        )
    validity = _required_mapping(request["validity"], "request.validity")
    if set(validity) != {"not_before_utc", "expires_at_utc"}:
        raise ExperimentAuthorizationError(
            "authorization request validity fields are invalid"
        )
    not_before = _parse_timestamp(
        validity["not_before_utc"],
        "not_before_utc",
    )
    expires = _parse_timestamp(
        validity["expires_at_utc"],
        "expires_at_utc",
    )
    if expires <= not_before:
        raise ExperimentAuthorizationError(
            "authorization request validity window is invalid"
        )
    _required_identifier(
        request["revocation_registry_id"],
        "revocation_registry_id",
    )
    _validate_permissions(request["requested_permissions"])
    return dict(request)


def _validate_bundle(payload: Any) -> dict[str, Any]:
    bundle = _required_mapping(payload, "d5_bundle")
    if set(bundle) != {
        "component",
        "manifest_sha256",
        "tree_sha256",
        "weights_sha256",
    }:
        raise ExperimentAuthorizationError(
            "authorization D5 bundle fields are invalid"
        )
    if bundle["component"] != "d5_graph":
        raise ExperimentAuthorizationError(
            "authorization supports only the D5 graph component"
        )
    for name in ("manifest_sha256", "tree_sha256", "weights_sha256"):
        _required_sha256(bundle[name], f"d5_bundle.{name}")
    return dict(bundle)


def _validate_permissions(payload: Any) -> dict[str, bool]:
    permissions = _required_mapping(payload, "permissions")
    if set(permissions) != set(G1_SHADOW_PERMISSION_FIELDS):
        raise ExperimentAuthorizationError(
            "authorization permission fields are invalid"
        )
    for name in G1_SHADOW_PERMISSION_FIELDS:
        if type(permissions[name]) is not bool:
            raise ExperimentAuthorizationError(
                f"authorization permission {name} must be bool"
            )
    if dict(permissions) != shadow_only_permissions():
        raise ExperimentAuthorizationError(
            "authorization permissions exceed shadow-only scoring"
        )
    return dict(permissions)


def _validate_revocation_registry(
    payload: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    value = _required_mapping(payload, "revocation_registry")
    if set(value) != {
        "schema_version",
        "registry_id",
        "updated_at_utc",
        "revocations",
    }:
        raise ExperimentAuthorizationError(
            "revocation registry fields are invalid"
        )
    if value["schema_version"] != G1_SHADOW_REVOCATION_REGISTRY_SCHEMA:
        raise ExperimentAuthorizationError(
            "revocation registry schema is unsupported"
        )
    registry_id = _required_identifier(value["registry_id"], "registry_id")
    _parse_timestamp(value["updated_at_utc"], "updated_at_utc")
    raw_revocations = value["revocations"]
    if not isinstance(raw_revocations, list):
        raise ExperimentAuthorizationError(
            "revocation registry entries must be a list"
        )
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_revocations:
        item = _required_mapping(raw, "revocation")
        if set(item) != {
            "authorization_id",
            "revoked_at_utc",
            "reason",
        }:
            raise ExperimentAuthorizationError(
                "revocation entry fields are invalid"
            )
        auth_id = _required_identifier(
            item["authorization_id"],
            "revocation.authorization_id",
        )
        if auth_id in seen:
            raise ExperimentAuthorizationError(
                "revocation registry contains a duplicate authorization"
            )
        seen.add(auth_id)
        revoked_at = _format_timestamp(
            item["revoked_at_utc"],
            "revoked_at_utc",
        )
        reason = str(item["reason"]).strip()
        if not reason:
            raise ExperimentAuthorizationError(
                "revocation reason is empty"
            )
        records.append(
            {
                "authorization_id": auth_id,
                "revoked_at_utc": revoked_at,
                "reason": reason,
            }
        )
    return registry_id, records


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentAuthorizationError(f"{name} must be a JSON object")
    return dict(value)


def _required_identifier(value: Any, name: str) -> str:
    text = str(value)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise ExperimentAuthorizationError(f"{name} is invalid")
    return text


def _required_sha256(value: Any, name: str) -> str:
    text = str(value)
    if not _HEX64_RE.fullmatch(text):
        raise ExperimentAuthorizationError(f"{name} is not a SHA-256 digest")
    return text


def _required_git_commit(value: Any) -> str:
    text = str(value)
    if not _GIT_COMMIT_RE.fullmatch(text):
        raise ExperimentAuthorizationError("source_git_commit is invalid")
    return text


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentAuthorizationError(f"{name} must be an ISO timestamp")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ExperimentAuthorizationError(
            f"{name} must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExperimentAuthorizationError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime | str, name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ExperimentAuthorizationError(
                f"{name} must include a timezone"
            )
        parsed = parsed.astimezone(timezone.utc)
    else:
        parsed = _parse_timestamp(value, name)
    return parsed.replace(microsecond=0).isoformat()


def _coerce_now(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExperimentAuthorizationError(
                "now_utc must include a timezone"
            )
        return value.astimezone(timezone.utc)
    return _parse_timestamp(value, "now_utc")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentAuthorizationError(
            f"cannot read authorization JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExperimentAuthorizationError(
            f"authorization JSON must contain an object: {path}"
        )
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    text = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "ExperimentAuthorizationError",
    "G1_SHADOW_APPROVAL_CONFIRMATION",
    "G1_SHADOW_AUTHORIZATION_BINDING_SCHEMA",
    "G1_SHADOW_AUTHORIZATION_SCHEMA",
    "G1_SHADOW_PERMISSION_FIELDS",
    "G1_SHADOW_REQUEST_ENVELOPE_SCHEMA",
    "G1_SHADOW_REQUEST_SCHEMA",
    "G1_SHADOW_REVOCATION_REGISTRY_SCHEMA",
    "G1ShadowExperimentAuthorization",
    "approve_g1_shadow_authorization_request",
    "build_g1_shadow_authorization_request",
    "canonical_json_sha256",
    "g1_shadow_scope_payload",
    "load_g1_shadow_experiment_authorization",
    "revoke_g1_shadow_authorization",
    "sha256_file",
    "shadow_only_permissions",
    "validate_authorization_binding_payload",
    "validate_authorization_scope_binding",
    "write_g1_shadow_authorization_request",
    "write_g1_shadow_revocation_registry",
]
