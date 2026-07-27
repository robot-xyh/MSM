#!/usr/bin/env python3
"""Prepare, approve, inspect, and revoke G1 shadow experiment authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.experiment_authorization import (  # noqa: E402
    G1_SHADOW_APPROVAL_CONFIRMATION,
    approve_g1_shadow_authorization_request,
    build_g1_shadow_authorization_request,
    load_g1_shadow_authorization_request,
    load_g1_shadow_experiment_authorization,
    load_g1_shadow_revocation_registry,
    revoke_g1_shadow_authorization,
    write_g1_shadow_authorization_request,
    write_g1_shadow_revocation_registry,
)
from research_modules.scalable_3d_simulation.experiment_matrix import (  # noqa: E402
    repository_state,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (  # noqa: E402
    describe_g1_shadow_d5_bundle,
)
from research_modules.scalable_3d_simulation.scenarios import (  # noqa: E402
    AVAILABLE_SCENARIOS,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser(
        "prepare",
        help="create a pending request and empty revocation registry",
    )
    prepare.add_argument("--authorization-id", required=True)
    prepare.add_argument("--purpose", required=True)
    prepare.add_argument(
        "--expected-git-commit",
        required=True,
        help="explicit clean source commit to freeze into the request",
    )
    prepare.add_argument(
        "--scenarios",
        nargs="+",
        choices=AVAILABLE_SCENARIOS,
        required=True,
    )
    prepare.add_argument("--scales", nargs="+", type=int, required=True)
    prepare.add_argument("--seeds", nargs="+", type=int, required=True)
    prepare.add_argument("--duration", type=float, required=True)
    prepare.add_argument(
        "--d5-graph-model-bundle",
        type=Path,
        required=True,
    )
    prepare.add_argument("--device", required=True)
    prepare.add_argument("--not-before-utc", required=True)
    prepare.add_argument("--expires-at-utc", required=True)
    prepare.add_argument("--revocation-registry-id", required=True)
    prepare.add_argument("--request-output", type=Path, required=True)
    prepare.add_argument(
        "--revocation-registry-output",
        type=Path,
        required=True,
    )

    approve = commands.add_parser(
        "approve",
        help="approve one exact pending request after human confirmation",
    )
    approve.add_argument("--request", type=Path, required=True)
    approve.add_argument("--output", type=Path, required=True)
    approve.add_argument("--expected-request-sha256", required=True)
    approve.add_argument("--approver-id", required=True)
    approve.add_argument("--approval-reason", required=True)
    approve.add_argument(
        "--confirmation",
        required=True,
        help=(
            "must exactly equal "
            f"{G1_SHADOW_APPROVAL_CONFIRMATION!r}"
        ),
    )
    approve.add_argument("--approved-at-utc")

    inspect = commands.add_parser(
        "inspect",
        help="strictly validate a request, authorization, or registry",
    )
    inspected = inspect.add_mutually_exclusive_group(required=True)
    inspected.add_argument("--request", type=Path)
    inspected.add_argument("--authorization", type=Path)
    inspected.add_argument("--registry", type=Path)
    inspect.add_argument("--expected-authorization-sha256")
    inspect.add_argument("--revocation-registry", type=Path)
    inspect.add_argument("--now-utc")

    revoke = commands.add_parser(
        "revoke",
        help="append one authorization revocation",
    )
    revoke.add_argument("--revocation-registry", type=Path, required=True)
    revoke.add_argument("--authorization-id", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--revoked-at-utc")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "prepare":
        _prepare(args)
        return 0
    if args.command == "approve":
        _assert_external_control_path(args.request)
        _assert_external_control_path(args.output)
        path, digest = approve_g1_shadow_authorization_request(
            args.request,
            args.output,
            expected_request_sha256=args.expected_request_sha256,
            approver_id=args.approver_id,
            approval_reason=args.approval_reason,
            confirmation=args.confirmation,
            approved_at_utc=args.approved_at_utc,
        )
        _print_json(
            {
                "state": "approved",
                "authorization_path": str(path.resolve()),
                "authorization_file_sha256": digest,
            }
        )
        return 0
    if args.command == "inspect":
        _inspect(args)
        return 0

    _assert_external_control_path(args.revocation_registry)
    revoke_g1_shadow_authorization(
        args.revocation_registry,
        authorization_id=args.authorization_id,
        reason=args.reason,
        revoked_at_utc=args.revoked_at_utc,
    )
    _print_json(load_g1_shadow_revocation_registry(args.revocation_registry))
    return 0


def _prepare(args: argparse.Namespace) -> None:
    request_output = args.request_output.resolve()
    registry_output = args.revocation_registry_output.resolve()
    if request_output == registry_output:
        raise ValueError("request and revocation registry paths must differ")
    _assert_external_control_path(request_output)
    _assert_external_control_path(registry_output)
    if request_output.exists() or registry_output.exists():
        raise FileExistsError(
            "request and revocation outputs must both be new files"
        )

    commit, dirty = repository_state(ROOT)
    expected_commit = str(args.expected_git_commit).strip().lower()
    if dirty:
        raise RuntimeError(
            "authorization request preparation requires repository_dirty=false"
        )
    if commit != expected_commit:
        raise RuntimeError(
            "current Git commit differs from --expected-git-commit"
        )
    descriptor = describe_g1_shadow_d5_bundle(
        args.d5_graph_model_bundle
    )
    current_commit, current_dirty = repository_state(ROOT)
    if current_dirty or current_commit != commit:
        raise RuntimeError(
            "repository source changed while preparing authorization request"
        )

    request = build_g1_shadow_authorization_request(
        authorization_id=args.authorization_id,
        purpose=args.purpose,
        source_git_commit=commit,
        scenarios=tuple(args.scenarios),
        scales=tuple(args.scales),
        seeds=tuple(args.seeds),
        duration_s=args.duration,
        d5_bundle_manifest_sha256=descriptor["manifest_sha256"],
        d5_bundle_tree_sha256=descriptor["tree_sha256"],
        d5_weights_sha256=descriptor["weights_sha256"],
        device=args.device,
        not_before_utc=args.not_before_utc,
        expires_at_utc=args.expires_at_utc,
        revocation_registry_id=args.revocation_registry_id,
    )

    created: list[Path] = []
    try:
        write_g1_shadow_revocation_registry(
            registry_output,
            registry_id=args.revocation_registry_id,
        )
        created.append(registry_output)
        write_g1_shadow_authorization_request(
            request_output,
            request,
        )
        created.append(request_output)
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    _print_json(
        {
            "state": "pending_human_approval",
            "request_path": str(request_output),
            "request_sha256": request["request_sha256"],
            "revocation_registry_path": str(registry_output),
            "source_git_commit": commit,
            "scope_sha256": request["request"]["scope"][
                "scope_sha256"
            ],
            "permissions": request["request"]["requested_permissions"],
        }
    )


def _inspect(args: argparse.Namespace) -> None:
    if args.request is not None:
        _print_json(load_g1_shadow_authorization_request(args.request))
        return
    if args.registry is not None:
        _print_json(load_g1_shadow_revocation_registry(args.registry))
        return
    if (
        not args.expected_authorization_sha256
        or args.revocation_registry is None
    ):
        raise ValueError(
            "authorization inspection requires its explicit SHA-256 and "
            "revocation registry"
        )
    grant = load_g1_shadow_experiment_authorization(
        args.authorization,
        expected_authorization_sha256=(
            args.expected_authorization_sha256
        ),
        revocation_registry_path=args.revocation_registry,
        now_utc=args.now_utc,
    )
    _print_json(
        {
            "state": "active",
            "authorization": grant.binding_payload(),
            "scope": dict(grant.scope),
        }
    )


def _assert_external_control_path(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(
        "authorization control files must be stored outside the repository"
    )


def _print_json(payload: Any) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
