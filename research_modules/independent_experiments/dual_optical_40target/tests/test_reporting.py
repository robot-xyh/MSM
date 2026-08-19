from __future__ import annotations

from types import SimpleNamespace

from dual_optical_40target.reporting import (
    _configure_matplotlib,
    _geometry_sensitivity_summary,
    _plot_geometry_sensitivity,
)


def test_geometry_sensitivity_summary_accepts_none_and_empty_records(tmp_path) -> None:
    metrics = {
        "geometry_sensitivity_p50_median_m": None,
        "geometry_sensitivity_p95_median_m": None,
        "intersection_angle_median_deg": None,
    }

    summary = _geometry_sensitivity_summary(metrics, ())
    _configure_matplotlib()
    figure = _plot_geometry_sensitivity(
        SimpleNamespace(geometry_sensitivity=()),
        tmp_path / "geometry_sensitivity.png",
    )

    assert summary == "本轮没有形成可用的几何敏感性样本，相关统计记为不可用。"
    assert figure.is_file()
    assert figure.stat().st_size > 0
