from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from center_terminal_cv_campaign.run_campaign import (
    _apply_and_audit_camera_fov,
    _validate_campaign_scale,
    build_experiment_command,
    parse_args,
)


def test_main_builds_disjoint_experiment_commands() -> None:
    fixture = Path("fixture")
    output = Path("output")
    search = build_experiment_command(
        experiment="search",
        fixture_dir=fixture,
        output_dir=output,
        mode="offline",
        target_count=5,
        seed=20260816,
        api_port=41451,
        resource_count=8,
        association_backend="geometry",
    )
    handover = build_experiment_command(
        experiment="center_handover",
        fixture_dir=fixture,
        output_dir=output,
        mode="offline",
        target_count=20,
        seed=20260817,
        api_port=41452,
        resource_count=8,
        association_backend="gnn",
    )
    crossview = build_experiment_command(
        experiment="crossview",
        fixture_dir=fixture,
        output_dir=output,
        mode="offline",
        target_count=20,
        seed=20260817,
        api_port=41452,
        resource_count=8,
        association_backend="geometry",
    )

    assert "--resource-count" in search
    assert "--association-backend" not in search
    assert "--association-backend" in handover
    assert "--resource-count" not in handover
    assert search[search.index("--target-count") + 1] == "5"
    assert "--target-count" not in handover
    assert "--api-port" not in handover
    assert crossview[crossview.index("--target-count") + 1] == "20"
    assert crossview[crossview.index("--scenario") + 1] == "dense_multicamera"
    assert "--api-port" not in crossview


def test_main_applies_and_audits_fov_after_reset(tmp_path) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.fov_by_vehicle: dict[str, float] = {}

        def simGetCameraInfo(self, camera_name: str, *, vehicle_name: str):
            assert camera_name == "0"
            return SimpleNamespace(fov=self.fov_by_vehicle[vehicle_name])

    class FakeRuntime:
        def __init__(self) -> None:
            self.client = FakeClient()

        def set_cv_camera_fov(
            self,
            *,
            vehicle_name: str,
            camera_name: str,
            horizontal_fov_deg: float,
        ):
            self.client.fov_by_vehicle[vehicle_name] = horizontal_fov_deg
            return {"ok": True, "vehicle_name": vehicle_name, "camera_name": camera_name}

    path = _apply_and_audit_camera_fov(
        FakeRuntime(),
        interceptor_capacity=2,
        output_path=tmp_path / "audit.json",
    )
    assert path.exists()


def test_main_accepts_requested_40_target_50_resource_scale() -> None:
    args = parse_args(
        [
            "--target-count",
            "40",
            "--resource-count",
            "50",
            "--interceptor-capacity",
            "50",
        ]
    )
    _validate_campaign_scale(args)
    assert args.target_count == 40
    assert args.resource_count == 50


def test_main_rejects_capacity_below_active_scale() -> None:
    args = parse_args(
        [
            "--target-count",
            "40",
            "--resource-count",
            "50",
            "--interceptor-capacity",
            "40",
        ]
    )
    try:
        _validate_campaign_scale(args)
    except ValueError as exc:
        assert "need 50" in str(exc)
    else:  # pragma: no cover - explicit assertion keeps the failure readable
        raise AssertionError("capacity below the active scale must be rejected")
