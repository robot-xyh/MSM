from dual_optical_online_benchmark.v5_reporting import _markdown


def _route(identity_rate: float, false_matches: int, latency_ms: float) -> dict:
    return {
        "available": True,
        "source": "aggregate",
        "metrics": {
            "current_track_identity_rate": identity_rate,
            "false_match_count": false_matches,
            "coverage": 0.03364583333333333,
            "confirmed_count": 0,
            "latency_p95_ms": latency_ms,
        },
    }


def test_v5_markdown_reports_actionable_metrics_and_chinese_failures() -> None:
    payload = {
        "scales": [
            {
                "target_count": 40,
                "tracker": {
                    "status": "diagnostic",
                    "acceptance_passed": False,
                    "failure_reasons": [
                        "false_reactivation_rate_absolute",
                        "fragmentation_not_above_baseline",
                        "sweep_runtime_p95_ms",
                    ],
                },
                "test": {"status": "diagnostic"},
                "routes": {
                    "rule_baseline": _route(0.8873626374, 41, 0.2762),
                    "gnn_assisted": _route(0.8947368421, 38, 2.0507),
                },
            }
        ]
    }

    report = _markdown(payload)

    assert "即时正确率=88.74%" in report
    assert "即时正确率=89.47%" in report
    assert "即时身份正确率变化+0.74个百分点" in report
    assert "错配数变化-3" in report
    assert "跨圈确认分别为0和0" in report
    assert "错误恢复率超过0.5%" in report
    assert "平均航迹碎片数高于基线" in report
    assert "单圈处理P95超过250毫秒" in report
