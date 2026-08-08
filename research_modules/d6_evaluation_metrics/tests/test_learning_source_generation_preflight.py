from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from d6_evaluation_metrics.learning_source_generation_preflight import (
    EXPECTED_EPISODE_COUNTS,
    LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION,
    evaluate_learning_source_generation_preflight,
    load_learning_source_generation_preflight_inputs,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "research_modules/d6_evaluation_metrics/scripts/"
    "run_learning_source_generation_preflight.py"
)
SOURCE_COMMIT = "a" * 40
AUTHORIZATION_SHA = "b" * 64
_MANIFEST_RELATIVE_PATHS = {
    "D3": "dataset/dataset_manifest.json",
    "D4": "dataset/manifest.json",
    "D5": "source_manifest.json",
}
_MANIFEST_SCHEMA_FIELDS = {
    "D3": "schema_version",
    "D4": "schema",
    "D5": "schema_version",
}
_MANIFEST_SCHEMA_VERSIONS = {
    "D3": "synthetic.d3-source-manifest.v1",
    "D4": "d4-region-resource-v8-train-dataset-manifest-v1",
    "D5": "synthetic.d5-source-manifest.v1",
}
_EXPECTED_NO_AUTHORITY = {
    "training": False,
    "validation_consumption": False,
    "test_consumption": False,
    "future_held_out_consumption": False,
    "model_inference": False,
    "shadow": False,
    "assist": False,
    "promotion": False,
    "ppo": False,
    "assignment": False,
    "degradation": False,
    "camera_command": False,
    "runtime": False,
    "production": False,
    "control": False,
    "global_track_id_create": False,
    "global_track_id_write": False,
}


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _source_fixture(
    root: Path,
    module: str,
    *,
    mutate: Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], None]
    | None = None,
    manifest_mutate: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    count = EXPECTED_EPISODE_COUNTS[module]
    request_sha = {"D3": "3", "D4": "4", "D5": "5"}[module] * 64
    base_seed = {"D3": 23_000, "D4": 25_000, "D5": 24_000}[module]
    manifest_relative_path = _MANIFEST_RELATIVE_PATHS[module]
    session = {
        "schema_version": "scalable3d-learning-source-generation-session-v1",
        "module": module,
        "source_git_commit": SOURCE_COMMIT,
        "authorization_id": "synthetic-generation-only",
        "authorization_sha256": AUTHORIZATION_SHA,
        "module_request_sha256": request_sha,
        "planned_episode_count": count,
        "dataset_generation": True,
        "training": False,
        "future_held_out_model_consumption": False,
        "runtime": False,
        "control": False,
        "global_track_id_create": False,
        "global_track_id_write": False,
    }
    checkpoint = {
        "schema_version": "scalable3d-learning-source-generation-checkpoint-v1",
        "state": "finalized",
        "module": module,
        "source_git_commit": SOURCE_COMMIT,
        "authorization_id": "synthetic-generation-only",
        "authorization_sha256": AUTHORIZATION_SHA,
        "module_request_sha256": request_sha,
        "planned_episode_count": count,
        "completed_episode_count": count,
        "remaining_episode_count": 0,
        "next_sequence": count,
        "invocation_count": 1,
        "last_invocation_wall_s": 0.25,
        "dataset_generation": True,
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
        "formal_seed_payload_read_count": 0,
        "future_held_out_model_consumption_count": 0,
    }
    progress = [
        {
            "schema_version": "scalable3d-learning-source-generation-progress-v1",
            "module": module,
            "sequence": index,
            "episode_id": f"{module.lower()}-synthetic-{index:04d}",
            "seed": base_seed + index,
            "source_git_commit": SOURCE_COMMIT,
            "authorization_sha256": AUTHORIZATION_SHA,
            "module_request_sha256": request_sha,
            "finite_state": True,
            "online_truth_use_count": 0,
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "training_started": False,
            "runtime_authority_granted": False,
            "control_authority_granted": False,
        }
        for index in range(count)
    ]
    if mutate is not None:
        mutate(session, checkpoint, progress)

    manifest = {
        _MANIFEST_SCHEMA_FIELDS[module]: _MANIFEST_SCHEMA_VERSIONS[module],
        "module": module,
        "episode_count": count,
        "permissions": dict(_EXPECTED_NO_AUTHORITY),
    }
    if manifest_mutate is not None:
        manifest_mutate(manifest)
    _write_json(root / "generation_session.json", session)
    _write_json(root / "generation_checkpoint.json", checkpoint)
    (root / "episode_progress.jsonl").write_bytes(
        b"".join(_canonical_bytes(row) for row in progress)
    )
    manifest_path = root / manifest_relative_path
    _write_json(manifest_path, manifest)
    payload_path = root / "dataset/shards/episode_payload.bin"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(b"this-is-not-json-and-must-never-be-opened")

    inventory_paths = [
        payload_path,
        root / "episode_progress.jsonl",
        root / "generation_checkpoint.json",
        root / "generation_session.json",
        manifest_path,
    ]
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _digest(path),
        }
        for path in inventory_paths
    ]
    records.sort(key=lambda item: item["path"])
    inventory = {
        "file_count": len(records),
        "total_size_bytes": sum(item["size_bytes"] for item in records),
        "files": records,
        "tree_sha256": sha256(_canonical_bytes({"files": records})).hexdigest(),
    }
    result = {
        **checkpoint,
        "schema_version": "scalable3d-learning-source-generation-result-v1",
        "newly_completed_episode_count": count,
        "finalization_summary": {"manifest_sha256": _digest(manifest_path)},
        "artifact_inventory": inventory,
    }
    _write_json(root / "generation_result.json", result)
    files = {
        "session": "generation_session.json",
        "checkpoint": "generation_checkpoint.json",
        "result": "generation_result.json",
        "progress": "episode_progress.jsonl",
        "manifest": manifest_relative_path,
    }
    return {
        "module": module,
        "source_root": root.absolute().as_posix(),
        "expected_episode_count": count,
        "source_git_commit": SOURCE_COMMIT,
        "generation_authorization_sha256": AUTHORIZATION_SHA,
        "module_request_sha256": request_sha,
        "files": {
            role: {"relative_path": relative, "sha256": _digest(root / relative)}
            for role, relative in files.items()
        },
        "artifact_inventory_sha256": sha256(_canonical_bytes(inventory)).hexdigest(),
    }


def _contract_fixture(
    tmp_path: Path,
    *,
    module_mutations: dict[
        str,
        Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], None],
    ]
    | None = None,
    manifest_mutations: dict[str, Callable[[dict[str, Any]], None]] | None = None,
) -> tuple[Path, str, dict[str, Path]]:
    roots: dict[str, Path] = {}
    sources = []
    for module in ("D3", "D4", "D5"):
        root = tmp_path / module
        roots[module] = root
        sources.append(
            _source_fixture(
                root,
                module,
                mutate=(module_mutations or {}).get(module),
                manifest_mutate=(manifest_mutations or {}).get(module),
            )
        )
    contract = {
        "schema_version": LEARNING_SOURCE_GENERATION_PREFLIGHT_INPUT_SCHEMA_VERSION,
        "contract_id": "synthetic-d3-d4-d5-preflight-v1",
        "sources": sources,
    }
    path = tmp_path / "preflight_input.json"
    _write_json(path, contract)
    return path, _digest(path), roots


def _evaluate(path: Path, digest: str) -> dict[str, Any]:
    inputs = load_learning_source_generation_preflight_inputs(
        path,
        expected_sha256=digest,
    )
    return evaluate_learning_source_generation_preflight(inputs)


def _is_within_any(path: Path, roots: dict[str, Path]) -> bool:
    absolute = path.absolute()
    for root in roots.values():
        try:
            absolute.relative_to(root.absolute())
        except ValueError:
            continue
        return True
    return False


def test_metadata_preflight_opens_only_bound_metadata_and_never_scans_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract, digest, roots = _contract_fixture(tmp_path)
    payload_relative_path = Path("dataset/shards/episode_payload.bin")
    for root in roots.values():
        # Break the producer-declared payload size and hash after metadata freezes.
        # A metadata-only preflight must still neither observe nor repair this drift.
        (root / payload_relative_path).write_bytes(b"changed-after-inventory-freeze")

    expected_opened_paths = {
        root / relative
        for module, root in roots.items()
        for relative in (
            "generation_session.json",
            "generation_checkpoint.json",
            "generation_result.json",
            "episode_progress.jsonl",
            _MANIFEST_RELATIVE_PATHS[module],
        )
    }
    opened_source_paths: list[Path] = []
    original_open = Path.open

    def guarded_open(path: Path, *args, **kwargs):
        absolute = path.absolute()
        if _is_within_any(absolute, roots):
            opened_source_paths.append(absolute)
            assert absolute in expected_opened_paths
            mode = args[0] if args else kwargs.get("mode", "r")
            assert mode == "rb"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    for method_name in ("iterdir", "glob", "rglob"):
        original_method = getattr(Path, method_name)

        def guarded_scan(
            path: Path,
            *args,
            _original=original_method,
            _method_name=method_name,
            **kwargs,
        ):
            if _is_within_any(path, roots):
                pytest.fail(f"source root scan is forbidden: {_method_name}:{path}")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(Path, method_name, guarded_scan)

    result = _evaluate(contract, digest)

    assert result["status"] == "ready_for_explicit_d6_source_audit_authorization"
    assert result["metadata_preflight_passed"] is True
    assert result["formal_source_data_read"] is False
    assert result["full_payload_audit_performed"] is False
    assert result["permissions"] == _EXPECTED_NO_AUTHORITY
    assert {item["progress_record_count"] for item in result["sources"].values()} == {
        300,
        324,
        104,
    }
    assert set(opened_source_paths) == expected_opened_paths
    assert len(opened_source_paths) == len(expected_opened_paths) == 15
    for item in result["sources"].values():
        assert item["payload_file_open_count"] == 0
        assert item["artifact_inventory_verification_scope"] == (
            "producer_metadata_self_consistency_only"
        )
        assert item["artifact_inventory_producer_metadata_self_consistent"] is True
        assert item["artifact_inventory_payload_content_verified"] is False
        assert item["permissions"] == _EXPECTED_NO_AUTHORITY


def test_manifest_bindings_support_d3_d4_d5_relative_path_shapes(
    tmp_path: Path,
) -> None:
    contract, digest, _ = _contract_fixture(tmp_path)
    inputs = load_learning_source_generation_preflight_inputs(
        contract,
        expected_sha256=digest,
    )

    assert {
        source.module: source.files["manifest"].relative_path for source in inputs.sources
    } == _MANIFEST_RELATIVE_PATHS
    result = evaluate_learning_source_generation_preflight(inputs)
    assert result["metadata_preflight_passed"] is True
    assert {
        module: item["manifest_schema_field"]
        for module, item in result["sources"].items()
    } == _MANIFEST_SCHEMA_FIELDS
    assert {
        module: item["manifest_schema_version"]
        for module, item in result["sources"].items()
    } == _MANIFEST_SCHEMA_VERSIONS


@pytest.mark.parametrize(
    ("module", "mutation", "expected_code"),
    [
        (
            "D3",
            lambda manifest: manifest.__setitem__("schema", "unexpected-d3-schema"),
            "manifest_schema_fields_conflict",
        ),
        (
            "D4",
            lambda manifest: manifest.__setitem__("schema", 4),
            "manifest_schema_type_invalid",
        ),
        (
            "D5",
            lambda manifest: manifest.__setitem__("schema_version", "   "),
            "manifest_schema_empty",
        ),
        (
            "D4",
            lambda manifest: (
                manifest.pop("schema"),
                manifest.__setitem__("schema_version", "wrong-field-for-d4"),
            ),
            "manifest_schema_field_module_mismatch",
        ),
        (
            "D3",
            lambda manifest: manifest.__setitem__("module", "D4"),
            "manifest_module_mismatch",
        ),
        (
            "D5",
            lambda manifest: (
                manifest.pop("schema_version"),
                manifest.__setitem__("version", "must-not-be-accepted"),
            ),
            "manifest_schema_missing",
        ),
    ],
)
def test_manifest_schema_contract_fails_closed(
    tmp_path: Path,
    module: str,
    mutation: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    contract, digest, _ = _contract_fixture(
        tmp_path,
        manifest_mutations={module: mutation},
    )

    result = _evaluate(contract, digest)

    assert result["status"] == "failed_closed"
    assert expected_code in result["blocker_codes"]
    assert result["permissions"] == _EXPECTED_NO_AUTHORITY
    assert result["sources"][module]["permissions"] == _EXPECTED_NO_AUTHORITY


def test_missing_sequence_fails_closed(tmp_path: Path) -> None:
    def mutate(_session, _checkpoint, rows):
        rows[10]["sequence"] = 11

    contract, digest, _ = _contract_fixture(tmp_path, module_mutations={"D3": mutate})
    result = _evaluate(contract, digest)
    assert result["status"] == "failed_closed"
    assert "progress_sequence_mismatch" in result["blocker_codes"]
    assert result["permissions"] == _EXPECTED_NO_AUTHORITY
    assert result["sources"]["D3"]["permissions"] == _EXPECTED_NO_AUTHORITY


def test_duplicate_seed_fails_closed(tmp_path: Path) -> None:
    def mutate(_session, _checkpoint, rows):
        rows[1]["seed"] = rows[0]["seed"]

    contract, digest, _ = _contract_fixture(tmp_path, module_mutations={"D4": mutate})
    result = _evaluate(contract, digest)
    assert "progress_seed_duplicate" in result["blocker_codes"]


def test_metadata_hash_tampering_fails_closed(tmp_path: Path) -> None:
    contract, digest, roots = _contract_fixture(tmp_path)
    with (roots["D5"] / "source_manifest.json").open("ab") as stream:
        stream.write(b" ")
    result = _evaluate(contract, digest)
    assert "manifest_file_sha256_mismatch" in result["blocker_codes"]


def test_duplicate_json_key_in_input_contract_is_rejected(tmp_path: Path) -> None:
    contract = tmp_path / "duplicate.json"
    contract.write_text(
        '{"schema_version":"d6.learning-source-generation-preflight-input.v1",'
        '"contract_id":"first","contract_id":"second","sources":[]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="input_contract_json_invalid"):
        load_learning_source_generation_preflight_inputs(
            contract,
            expected_sha256=_digest(contract),
        )


def test_metadata_symlink_fails_closed(tmp_path: Path) -> None:
    contract, digest, roots = _contract_fixture(tmp_path)
    manifest = roots["D3"] / _MANIFEST_RELATIVE_PATHS["D3"]
    target = manifest.with_name("manifest-target.json")
    manifest.replace(target)
    manifest.symlink_to(target.name)
    result = _evaluate(contract, digest)
    assert "manifest_symlink_forbidden" in result["blocker_codes"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda _session, checkpoint, _rows: checkpoint.__setitem__(
                "runtime_authority_granted", True
            ),
            "checkpoint_runtime_authority_granted_invalid",
        ),
        (
            lambda _session, _checkpoint, rows: rows[0].__setitem__(
                "online_truth_use_count", 1
            ),
            "progress_online_truth_use_count_invalid",
        ),
        (
            lambda _session, _checkpoint, rows: rows[0].__setitem__(
                "global_track_id_rewritten_count", 1
            ),
            "progress_global_track_id_rewritten_count_invalid",
        ),
    ],
)
def test_authority_truth_and_id_write_fail_closed(
    tmp_path: Path,
    mutation,
    expected_code: str,
) -> None:
    contract, digest, _ = _contract_fixture(
        tmp_path,
        module_mutations={"D5": mutation},
    )
    result = _evaluate(contract, digest)
    assert expected_code in result["blocker_codes"]


def test_cli_writes_json_chinese_markdown_and_checksums(tmp_path: Path) -> None:
    contract, digest, _ = _contract_fixture(tmp_path / "fixture")
    spec = importlib.util.spec_from_file_location("d6_preflight_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "report"

    code = module.main(
        [
            "--input-contract",
            str(contract),
            "--input-contract-sha256",
            digest,
            "--output-dir",
            str(output),
        ]
    )

    assert code == 0
    assert (output / "preflight.json").is_file()
    assert (output / "PREFLIGHT_REPORT_CN.md").is_file()
    assert (output / "SHA256SUMS").is_file()
    report = json.loads((output / "preflight.json").read_text(encoding="utf-8"))
    assert report["formal_source_data_read"] is False
    assert "完整载荷审计：`未执行`" in (
        output / "PREFLIGHT_REPORT_CN.md"
    ).read_text(encoding="utf-8")
