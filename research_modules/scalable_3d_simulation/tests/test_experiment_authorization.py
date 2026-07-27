from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.experiment_authorization import (
    ExperimentAuthorizationError,
    G1_SHADOW_APPROVAL_CONFIRMATION,
    G1ShadowExperimentAuthorization,
    approve_g1_shadow_authorization_request,
    build_g1_shadow_authorization_request,
    canonical_json_sha256,
    load_g1_shadow_experiment_authorization,
    revoke_g1_shadow_authorization,
    shadow_only_permissions,
    validate_authorization_binding_payload,
    validate_authorization_scope_binding,
    write_g1_shadow_authorization_request,
    write_g1_shadow_revocation_registry,
)


_COMMIT = "1" * 40
_MANIFEST_SHA = "2" * 64
_TREE_SHA = "3" * 64
_WEIGHTS_SHA = "4" * 64


def _request(now: datetime) -> dict[str, object]:
    return build_g1_shadow_authorization_request(
        authorization_id="g1-shadow-test-001",
        purpose="controlled anonymous edge scoring",
        source_git_commit=_COMMIT,
        scenarios=("nominal", "dense_crossing"),
        scales=(5, 20),
        seeds=(1000, 1001),
        duration_s=2.0,
        d5_bundle_manifest_sha256=_MANIFEST_SHA,
        d5_bundle_tree_sha256=_TREE_SHA,
        d5_weights_sha256=_WEIGHTS_SHA,
        device="cpu",
        not_before_utc=now - timedelta(minutes=1),
        expires_at_utc=now + timedelta(hours=2),
        revocation_registry_id="g1-shadow-registry-001",
    )


def _approved(
    tmp_path: Path,
    now: datetime,
) -> tuple[Path, str, Path, dict[str, object]]:
    request = _request(now)
    request_path = write_g1_shadow_authorization_request(
        tmp_path / "request.json",
        request,
    )
    registry_path = write_g1_shadow_revocation_registry(
        tmp_path / "revocations.json",
        registry_id="g1-shadow-registry-001",
        updated_at_utc=now,
    )
    authorization_path, authorization_sha256 = (
        approve_g1_shadow_authorization_request(
            request_path,
            tmp_path / "authorization.json",
            expected_request_sha256=str(request["request_sha256"]),
            approver_id="local-test-operator",
            approval_reason="bounded simulation shadow comparison",
            confirmation=G1_SHADOW_APPROVAL_CONFIRMATION,
            approved_at_utc=now,
        )
    )
    return (
        authorization_path,
        authorization_sha256,
        registry_path,
        request,
    )


def test_approved_scope_loads_and_binds_without_runtime_authority(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    authorization_path, digest, registry_path, request = _approved(
        tmp_path,
        now,
    )

    grant = load_g1_shadow_experiment_authorization(
        authorization_path,
        expected_authorization_sha256=digest,
        revocation_registry_path=registry_path,
        now_utc=now,
    )

    assert grant.authorization_id == "g1-shadow-test-001"
    assert grant.permissions == shadow_only_permissions()
    assert grant.permissions["g1_shadow_edge_scoring_granted"] is True
    assert all(
        value is False
        for key, value in grant.permissions.items()
        if key != "g1_shadow_edge_scoring_granted"
    )
    grant.assert_cell(
        variant="G1",
        scenario="dense_crossing",
        scale=20,
        seed=1001,
        duration_s=2.0,
        now_utc=now,
    )
    validate_authorization_scope_binding(
        grant,
        source_git_commit=_COMMIT,
        scenarios=("nominal", "dense_crossing"),
        scales=(5, 20),
        seeds=(1000, 1001),
        duration_s=2.0,
        d5_bundle_manifest_sha256=_MANIFEST_SHA,
        d5_bundle_tree_sha256=_TREE_SHA,
        d5_weights_sha256=_WEIGHTS_SHA,
        device="cpu",
        now_utc=now,
    )
    binding = validate_authorization_binding_payload(
        grant.binding_payload()
    )
    assert binding["request_sha256"] == request["request_sha256"]
    assert binding["permissions"]["control_authority_granted"] is False


def test_digest_scope_and_confirmation_mismatches_fail_closed(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    request = _request(now)
    request_path = write_g1_shadow_authorization_request(
        tmp_path / "request.json",
        request,
    )
    with pytest.raises(
        ExperimentAuthorizationError,
        match="confirmation phrase",
    ):
        approve_g1_shadow_authorization_request(
            request_path,
            tmp_path / "authorization.json",
            expected_request_sha256=str(request["request_sha256"]),
            approver_id="local-test-operator",
            approval_reason="test",
            confirmation="APPROVE",
            approved_at_utc=now,
        )

    authorization_path, digest, registry_path, _ = _approved(
        tmp_path / "approved",
        now,
    )
    with pytest.raises(ExperimentAuthorizationError, match="digest"):
        load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256="f" * 64,
            revocation_registry_path=registry_path,
            now_utc=now,
        )
    grant = load_g1_shadow_experiment_authorization(
        authorization_path,
        expected_authorization_sha256=digest,
        revocation_registry_path=registry_path,
        now_utc=now,
    )
    with pytest.raises(ExperimentAuthorizationError, match="scenario"):
        grant.assert_cell(
            variant="G1",
            scenario="center_failure",
            scale=5,
            seed=1000,
            duration_s=2.0,
            now_utc=now,
        )
    with pytest.raises(ExperimentAuthorizationError, match="only the G1"):
        grant.assert_cell(
            variant="C1",
            scenario="nominal",
            scale=5,
            seed=1000,
            duration_s=2.0,
            now_utc=now,
        )


def test_expiry_and_revocation_stop_new_shadow_scoring(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    authorization_path, digest, registry_path, _ = _approved(
        tmp_path,
        now,
    )
    with pytest.raises(ExperimentAuthorizationError, match="expired"):
        load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256=digest,
            revocation_registry_path=registry_path,
            now_utc=now + timedelta(hours=3),
        )

    revoke_g1_shadow_authorization(
        registry_path,
        authorization_id="g1-shadow-test-001",
        reason="operator stop",
        revoked_at_utc=now + timedelta(minutes=1),
    )
    with pytest.raises(ExperimentAuthorizationError, match="revoked"):
        load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256=digest,
            revocation_registry_path=registry_path,
            now_utc=now + timedelta(minutes=2),
        )


def test_permission_or_request_tampering_is_rejected(tmp_path: Path) -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    request = _request(now)
    request["request"]["requested_permissions"][
        "control_authority_granted"
    ] = True
    request["request_sha256"] = canonical_json_sha256(request["request"])
    with pytest.raises(ExperimentAuthorizationError, match="shadow-only"):
        write_g1_shadow_authorization_request(
            tmp_path / "request.json",
            request,
        )

    clean = _request(now)
    clean["request"]["scope"]["cell_count"] = 999
    clean["request_sha256"] = canonical_json_sha256(clean["request"])
    with pytest.raises(ExperimentAuthorizationError, match="canonical"):
        write_g1_shadow_authorization_request(
            tmp_path / "bad-scope.json",
            clean,
        )


def test_authorization_file_content_cannot_change_after_explicit_digest(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    authorization_path, digest, registry_path, _ = _approved(
        tmp_path,
        now,
    )
    payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    payload["approval"]["approval_reason"] = "changed after approval"
    authorization_path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ExperimentAuthorizationError, match="digest"):
        load_g1_shadow_experiment_authorization(
            authorization_path,
            expected_authorization_sha256=digest,
            revocation_registry_path=registry_path,
            now_utc=now,
        )


def test_authorization_object_cannot_be_forged_by_direct_construction() -> None:
    now = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
    request = _request(now)["request"]
    with pytest.raises(
        ExperimentAuthorizationError,
        match="strict loader",
    ):
        G1ShadowExperimentAuthorization(
            authorization_id=request["authorization_id"],
            authorization_file_sha256="5" * 64,
            request_sha256="6" * 64,
            source_git_commit=request["source"]["git_commit"],
            scope=request["scope"],
            scope_sha256=request["scope"]["scope_sha256"],
            d5_bundle=request["d5_bundle"],
            device=request["device"],
            not_before_utc=request["validity"]["not_before_utc"],
            expires_at_utc=request["validity"]["expires_at_utc"],
            revocation_registry_id=request["revocation_registry_id"],
            permissions=request["requested_permissions"],
            approver_id="forged-operator",
            approved_at_utc=now.isoformat(),
            approval_reason="must not be accepted",
        )
