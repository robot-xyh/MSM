from __future__ import annotations

import json

import pytest

from d5_terminal_association.scalable_3d_performance import (
    SCALABLE_3D_D5_DURATION_COMPARISON_SCHEMA_VERSION,
    compare_terminal_replay_benchmarks,
    render_scalable_3d_d5_duration_comparison_markdown,
    write_scalable_3d_d5_duration_comparison,
)


def _terminal_result(*, duration: float, frames: int, scale: int) -> dict[str, object]:
    operation_counts = {
        "schema_version": "d5-scalable3d-operation-counts-v1",
        "process_frame_count": frames,
        "camera_batch_count": 2 * scale,
        "input_detection_count": 3 * scale,
        "emitted_tracklet_count": 3 * scale,
        "oosm_batch_count": 0,
        "camera_template_build_count": 2 * scale,
        "camera_template_reuse_count": scale,
        "active_camera_stream_current": 2 * scale,
        "active_camera_stream_peak": 2 * scale,
        "active_local_history_current": 3 * scale,
        "active_local_history_peak": 3 * scale,
        "received_timestamp_history_current": 2 * scale,
        "received_timestamp_history_peak": 2 * scale,
        "tracker_pair_evaluation_count": 4 * scale,
        "tracker_match_candidate_count": 3 * scale,
        "tracker_history_update_count": 4 * scale,
        "center_track_input_count": 6 * scale,
        "center_projection_cache_hit_count": max(0, frames - 1),
        "center_projection_cache_miss_count": 1,
        "graph_build_count": frames,
        "graph_node_count": 3 * scale,
        "camera_overlap_index_build_count": frames,
        "candidate_edge_generation_count": 2 * scale,
        "geometry_gate_rejection_count": scale,
        "retained_graph_edge_count": scale,
        "edge_scoring_count": frames,
        "scored_edge_count": scale,
        "cluster_build_count": frames,
        "cluster_output_count": 2 * scale,
        "projection_matrix_build_count": frames,
        "projection_matrix_cell_count": 18 * scale,
        "projection_matrix_binding_reuse_count": frames,
        "binding_matrix_build_count": frames,
        "binding_matrix_cell_count": 12 * scale,
        "hungarian_solve_count": frames,
        "binding_output_count": 2 * scale,
    }
    per_frame = {
        key: value / frames
        for key, value in operation_counts.items()
        if key != "schema_version"
    }
    return {
        "semantic_match": True,
        "final_core_semantic_match": True,
        "final_binding_semantic_match": True,
        "operation_diagnostics_are_fixed_size": True,
        "simulation_duration_s": duration,
        "frame_count": frames,
        "mean_call_ms": 4.0 * scale / frames,
        "median_call_ms": 3.0 * scale / frames,
        "operation_counts": operation_counts,
        "operation_counts_per_frame": per_frame,
        "operation_counts_sha256": f"operation-{scale}",
        "online_truth_use_count": 0,
        "global_track_id_mutation_count": 0,
        "replayed_core_sha256": f"core-{scale}",
        "replayed_final_binding_sha256": f"binding-{scale}",
    }


def test_duration_comparison_reports_fixed_size_operation_growth() -> None:
    short = _terminal_result(duration=2.0, frames=2, scale=1)
    long = _terminal_result(duration=10.0, frames=10, scale=10)

    comparison = compare_terminal_replay_benchmarks(short, long)

    assert comparison["call_density_per_simulation_second"]["growth"] == 1.0
    assert comparison["operation_per_frame_growth"]["input_detection_count"] == 2.0
    assert comparison["operation_per_frame_growth"]["graph_build_count"] == 1.0
    assert comparison["short_business_hash_equivalent"] is True
    assert comparison["long_business_hash_equivalent"] is True
    assert comparison["online_truth_use_count"] == 0
    assert comparison["global_track_id_mutation_count"] == 0


def test_duration_comparison_fails_closed_on_business_hash_mismatch() -> None:
    short = _terminal_result(duration=2.0, frames=2, scale=1)
    long = _terminal_result(duration=10.0, frames=10, scale=10)
    long["final_binding_semantic_match"] = False

    with pytest.raises(ValueError, match="long D5 replay"):
        compare_terminal_replay_benchmarks(short, long)


def test_duration_comparison_report_is_chinese_and_machine_readable(tmp_path) -> None:
    short = _terminal_result(duration=2.0, frames=2, scale=1)
    long = _terminal_result(duration=10.0, frames=10, scale=10)
    report = {
        "schema_version": SCALABLE_3D_D5_DURATION_COMPARISON_SCHEMA_VERSION,
        "sources": {"short": {}, "long": {}},
        "short_terminal_replay": short,
        "long_terminal_replay": long,
        "comparison": compare_terminal_replay_benchmarks(short, long),
        "truth_source_loaded": False,
    }
    json_path = tmp_path / "result.json"
    markdown_path = tmp_path / "report.md"

    write_scalable_3d_d5_duration_comparison(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert json.loads(json_path.read_text(encoding="utf-8"))["truth_source_loaded"] is False
    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown == render_scalable_3d_d5_duration_comparison_markdown(report)
    assert "操作数" in markdown
    assert "业务等价" in markdown
    assert "在线真值使用与 global_track_id 改写均为 0" in markdown
