from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import subprocess

import pytest

from research_modules.scalable_3d_simulation.experiment_authorization import (
    ExperimentAuthorizationError,
    G1_SHADOW_APPROVAL_CONFIRMATION,
)
authorization_cli = importlib.import_module(
    "research_modules.scalable_3d_simulation.run_experiment_authorization"
)
shard_cli = importlib.import_module(
    "research_modules.scalable_3d_simulation.run_experiment_matrix_shard"
)


def test_authorization_manager_prepare_approve_inspect_and_revoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = _clean_repository(tmp_path / "repository")
    commit = _git(repository, "rev-parse", "HEAD").strip()
    bundle = _write_v5_bundle(tmp_path / "bundle")
    request_path = tmp_path / "control" / "request.json"
    registry_path = tmp_path / "control" / "revocations.json"
    authorization_path = tmp_path / "control" / "authorization.json"
    now = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(authorization_cli, "ROOT", repository)

    assert authorization_cli.main(
        [
            "prepare",
            "--authorization-id",
            "g1-shadow-cli-test",
            "--purpose",
            "bounded CLI shadow test",
            "--expected-git-commit",
            commit,
            "--scenarios",
            "nominal",
            "--scales",
            "5",
            "--seeds",
            "1000",
            "--duration",
            "2.0",
            "--d5-graph-model-bundle",
            str(bundle),
            "--device",
            "cpu",
            "--not-before-utc",
            (now - timedelta(minutes=1)).isoformat(),
            "--expires-at-utc",
            (now + timedelta(hours=1)).isoformat(),
            "--revocation-registry-id",
            "g1-shadow-cli-registry",
            "--request-output",
            str(request_path),
            "--revocation-registry-output",
            str(registry_path),
        ]
    ) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["state"] == "pending_human_approval"
    assert prepared["permissions"]["control_authority_granted"] is False

    assert authorization_cli.main(
        ["inspect", "--request", str(request_path)]
    ) == 0
    inspected_request = json.loads(capsys.readouterr().out)
    assert inspected_request["request_sha256"] == prepared["request_sha256"]

    assert authorization_cli.main(
        [
            "approve",
            "--request",
            str(request_path),
            "--output",
            str(authorization_path),
            "--expected-request-sha256",
            prepared["request_sha256"],
            "--approver-id",
            "local-test-operator",
            "--approval-reason",
            "test-only bounded scope",
            "--confirmation",
            G1_SHADOW_APPROVAL_CONFIRMATION,
            "--approved-at-utc",
            now.isoformat(),
        ]
    ) == 0
    approved = json.loads(capsys.readouterr().out)
    assert approved["state"] == "approved"

    assert authorization_cli.main(
        [
            "inspect",
            "--authorization",
            str(authorization_path),
            "--expected-authorization-sha256",
            approved["authorization_file_sha256"],
            "--revocation-registry",
            str(registry_path),
            "--now-utc",
            now.isoformat(),
        ]
    ) == 0
    active = json.loads(capsys.readouterr().out)
    assert active["state"] == "active"
    assert active["scope"]["variants"] == ["G1"]

    assert authorization_cli.main(
        [
            "revoke",
            "--revocation-registry",
            str(registry_path),
            "--authorization-id",
            "g1-shadow-cli-test",
            "--reason",
            "operator stop",
            "--revoked-at-utc",
            (now + timedelta(seconds=1)).isoformat(),
        ]
    ) == 0
    revoked = json.loads(capsys.readouterr().out)
    assert len(revoked["revocations"]) == 1

    with pytest.raises(ExperimentAuthorizationError, match="revoked"):
        authorization_cli.main(
            [
                "inspect",
                "--authorization",
                str(authorization_path),
                "--expected-authorization-sha256",
                approved["authorization_file_sha256"],
                "--revocation-registry",
                str(registry_path),
                "--now-utc",
                (now + timedelta(seconds=2)).isoformat(),
            ]
        )


def test_authorization_prepare_requires_clean_exact_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _clean_repository(tmp_path / "repository")
    commit = _git(repository, "rev-parse", "HEAD").strip()
    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    bundle = _write_v5_bundle(tmp_path / "bundle")
    monkeypatch.setattr(authorization_cli, "ROOT", repository)

    with pytest.raises(RuntimeError, match="repository_dirty=false"):
        authorization_cli.main(
            [
                "prepare",
                "--authorization-id",
                "g1-shadow-dirty-test",
                "--purpose",
                "must reject dirty source",
                "--expected-git-commit",
                commit,
                "--scenarios",
                "nominal",
                "--scales",
                "5",
                "--seeds",
                "1000",
                "--duration",
                "2.0",
                "--d5-graph-model-bundle",
                str(bundle),
                "--device",
                "cpu",
                "--not-before-utc",
                "2026-07-27T03:59:00+00:00",
                "--expires-at-utc",
                "2026-07-27T05:00:00+00:00",
                "--revocation-registry-id",
                "g1-shadow-dirty-registry",
                "--request-output",
                str(tmp_path / "dirty-request.json"),
                "--revocation-registry-output",
                str(tmp_path / "dirty-revocations.json"),
            ]
        )


def test_shard_cli_exposes_authorization_arguments() -> None:
    initialize = shard_cli.parse_args(
        [
            "init-scope",
            "--scope-variants",
            "G1",
            "--output",
            "/tmp/g1-scope",
            "--d5-graph-model-bundle",
            "/tmp/d5-bundle",
            "--experiment-authorization",
            "/tmp/authorization.json",
            "--experiment-authorization-sha256",
            "a" * 64,
            "--revocation-registry",
            "/tmp/revocations.json",
        ]
    )
    assert initialize.experiment_authorization_sha256 == "a" * 64
    assert initialize.revocation_registry == Path("/tmp/revocations.json")

    run = shard_cli.parse_args(
        [
            "run-shard",
            "--execution-plan",
            "/tmp/execution-plan.json",
            "--shard-index",
            "0",
            "--experiment-authorization",
            "/tmp/authorization.json",
            "--revocation-registry",
            "/tmp/revocations.json",
        ]
    )
    assert run.experiment_authorization == Path("/tmp/authorization.json")
    assert run.revocation_registry == Path("/tmp/revocations.json")


def _clean_repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test Operator")
    (path / "README.md").write_text("clean source\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "test source")
    return path


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _write_v5_bundle(path: Path) -> Path:
    path.mkdir()
    weights = path / "weights.pt"
    weights.write_bytes(b"test-v5-weights")
    weights_sha256 = _sha256_file(weights)
    manifest = {
        "schema_version": "d5.tracklet-model-bundle.v5",
        "model_semantic_version": "1.0.0",
        "admission": {
            "g1_assist_eligible": True,
            "authority_contract": {
                "runtime_authority": {
                    "model_promotion_granted": False,
                    "g1_assist_granted": False,
                    "default_path_change_granted": False,
                    "assignment_authority_granted": False,
                    "failover_authority_granted": False,
                    "control_authority_granted": False,
                }
            },
        },
        "weights": {
            "filename": "weights.pt",
            "sha256": weights_sha256,
        },
    }
    (path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
