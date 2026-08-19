# MSM Experiment Reproducibility Contract

Use this contract to audit existing outputs and to design future experiment folders.

## Evidence Levels

### A - Exact rerun package

Require all of the following:

- experiment ID, date, formal/diagnostic/offline status, and owning entry point;
- source commit plus whether the worktree was dirty;
- exact command, working directory, arguments, and environment variables;
- Python/package lock or environment export and simulator/AirSim/Blocks version;
- scenario, settings, protocol, camera profile, seed list, and timing parameters;
- immutable input and frozen model/tracker paths with SHA-256 hashes;
- reset/episode order and hardware-dependent settings;
- machine-readable metrics, metric definitions, acceptance thresholds, and logs;
- known nondeterminism and numeric comparison tolerance.

### B - Deterministic offline replay

Require anonymous raw observations or frozen snapshots, their manifest and hashes, frozen algorithms/models, replay command, offline truth labels, scoring code/version, and machine-readable expected metrics. This can reproduce association or evaluation results without reproducing the original simulator imagery.

### C - Partial rerun

Configuration, seeds, metrics, and a plausible entry point exist, but source revision, environment, exact command, input hashes, or simulator provenance is missing. A new run is possible, but equality with the original result cannot be claimed.

### D - Evidence only

Only a report, figure, or aggregate metric remains. The result can be cited with its stated boundary but cannot be reproduced from preserved evidence.

## Recommended Manifest

Future experiments should write one `reproduction_manifest.json` at the experiment root with these fields:

```json
{
  "schema_version": "msm-experiment-reproduction-v1",
  "experiment_id": "unique-run-id",
  "status": "formal|validation|diagnostic|offline_replay|failed_closed",
  "created_at": "ISO-8601 timestamp",
  "question": "scientific question tested",
  "source": {
    "git_commit": "40 hex characters",
    "worktree_dirty": false,
    "entry_point": "python module or script",
    "cwd": "repository-relative path",
    "command": ["python3", "..."],
    "environment": {"PYTHONPATH": "..."}
  },
  "runtime": {
    "python_version": "...",
    "dependency_lock": "relative path and sha256",
    "simulator": "AirSim Blocks|point_mass|offline_replay",
    "simulator_version": "...",
    "hardware_summary": "CPU/GPU only when relevant"
  },
  "scenario": {
    "config_path": "relative path",
    "config_sha256": "...",
    "settings_path": "relative path or null",
    "settings_sha256": "...",
    "seeds": [],
    "target_count": null,
    "resource_count": null,
    "duration_s": null,
    "clock_speed": null
  },
  "inputs": [
    {"role": "anonymous_observation|offline_truth|model|tracker", "path": "...", "sha256": "..."}
  ],
  "outputs": {
    "metrics": ["relative paths"],
    "reports": ["relative paths"],
    "logs": ["relative paths"],
    "figures": ["relative paths"]
  },
  "metrics_contract": {
    "definitions_path": "relative path",
    "denominators": {},
    "acceptance": {},
    "availability_policy": "timeouts and unavailable rows"
  },
  "reproduction": {
    "offline_replay_command": null,
    "full_rerun_command": null,
    "expected_metrics_sha256": "...",
    "comparison_tolerance": "exact or numeric tolerance",
    "known_nondeterminism": []
  }
}
```

## Audit Questions

1. Is the report tied to one unambiguous run directory?
2. Are every seed and corruption condition represented in the manifest?
3. Is the configuration that was executed preserved, rather than regenerated from current defaults?
4. Are raw online inputs separated from offline truth?
5. Are model/tracker versions and hashes fixed before held-out scoring?
6. Can the metric denominator and unavailable/timeout policy be reconstructed?
7. Does the output preserve per-seed/per-round rows instead of only an average?
8. Can an offline replay be run without AirSim?
9. Can a full simulator rerun be launched without guessing arguments?
10. Is the original source revision known, including uncommitted changes?
