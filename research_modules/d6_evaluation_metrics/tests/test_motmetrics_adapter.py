from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import d6_evaluation_metrics.motmetrics_adapter as adapter_module

from d6_evaluation_metrics import (
    OFFLINE_MOT_SCHEMA_VERSION,
    OfflineMOTFrame,
    evaluate_with_py_motmetrics,
    load_offline_mot_frames,
)


class _FakeAccumulator:
    def __init__(self, *, auto_id: bool) -> None:
        assert auto_id is False
        self.updates: list[tuple[list[int], list[int], list[list[float]], int]] = []

    def update(self, truth, hypotheses, distances, *, frameid) -> None:
        self.updates.append((truth, hypotheses, distances, frameid))


class _FakeMetricsHost:
    def compute(self, accumulator, *, metrics, name):
        assert len(accumulator.updates) == 2
        assert metrics == ["idf1", "mota", "motp"]
        assert name == "episode"
        # Stable integer mapping is required for motmetrics 1.4.0.
        assert accumulator.updates[0][0] == [1]
        assert accumulator.updates[1][0] == [1]
        assert accumulator.updates[0][1] == [1]
        assert accumulator.updates[1][1] == [1]
        return {"episode": {"idf1": 1.0, "mota": 1.0, "motp": 0.15}}


def _fake_backend():
    return SimpleNamespace(
        __version__="1.4.0",
        MOTAccumulator=_FakeAccumulator,
        metrics=SimpleNamespace(create=lambda: _FakeMetricsHost()),
    )


def test_py_motmetrics_adapter_reports_available_metrics_and_hota_unavailable() -> None:
    frames = [
        OfflineMOTFrame(0, 0.0, ("T1",), ("G1",), ((0.1,),)),
        OfflineMOTFrame(1, 0.1, ("T1",), ("G1",), ((0.2,),)),
    ]

    result = evaluate_with_py_motmetrics(frames, motmetrics_module=_fake_backend())

    assert result.status == "available"
    assert result.backend_version == "1.4.0"
    assert result.idf1 == 1.0
    assert result.mota == 1.0
    assert result.motp == pytest.approx(0.15)
    assert result.hota is None
    assert result.metric_availability["hota"] == {
        "status": "unavailable",
        "reason": "py-motmetrics 1.4.0 does not implement HOTA",
    }
    assert result.metadata["online_use_forbidden"] is True


def test_py_motmetrics_adapter_marks_missing_evidence_unavailable() -> None:
    no_frames = evaluate_with_py_motmetrics([], motmetrics_module=_fake_backend())
    missing_frame = evaluate_with_py_motmetrics(
        [
            OfflineMOTFrame(
                0,
                0.0,
                ("T1",),
                ("G1",),
                ((0.1,),),
                evidence_available=False,
            )
        ],
        motmetrics_module=_fake_backend(),
    )

    assert no_frames.status == "unavailable"
    assert "absent" in no_frames.reason
    assert missing_frame.status == "unavailable"
    assert "frame 0" in missing_frame.reason
    assert missing_frame.idf1 is None
    assert missing_frame.metric_availability["idf1"]["status"] == "unavailable"


def test_py_motmetrics_adapter_marks_optional_dependency_unavailable(monkeypatch) -> None:
    def _missing(_name: str):
        raise ModuleNotFoundError("motmetrics")

    monkeypatch.setattr(adapter_module.importlib, "import_module", _missing)
    result = evaluate_with_py_motmetrics(
        [OfflineMOTFrame(0, 0.0, ("T1",), ("G1",), ((0.1,),))]
    )

    assert result.status == "unavailable"
    assert "optional dependency" in result.reason
    assert result.unavailable_reason == result.reason
    assert result.metric_availability["mota"]["status"] == "unavailable"


def test_offline_mot_schema_loader_requires_truth_isolation(tmp_path) -> None:
    path = tmp_path / "offline_mot.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": OFFLINE_MOT_SCHEMA_VERSION,
                "online_use_forbidden": True,
                "frames": [
                    {
                        "frame_id": 3,
                        "timestamp": 1.5,
                        "truth_ids": ["T1"],
                        "hypothesis_ids": ["G1", "G2"],
                        "distance_matrix": [[0.1, None]],
                        "metadata": {"distance_kind": "1-iou"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    frames = load_offline_mot_frames(path)

    assert len(frames) == 1
    assert frames[0].frame_id == 3
    assert frames[0].distance_matrix == ((0.1, None),)
    assert frames[0].metadata["distance_kind"] == "1-iou"

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["online_use_forbidden"] = False
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="online_use_forbidden"):
        load_offline_mot_frames(path)
