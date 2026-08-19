---
name: locate-experiment-evidence
description: Locate, trace, and audit MSM experiment configurations, commands, seeds, manifests, logs, metrics, reports, raw observations, frozen models, and code provenance. Use when a user asks where an AirSim, point-mass, independent-experiment, D1-D7, multi-seed, association, guidance, or evaluation result came from; wants to compare experiment versions; cannot find a configuration or output; asks whether a result can be rerun or replayed; or requests a reproducibility checklist or exact evidence map.
---

# Locate Experiment Evidence

Find the machine-readable evidence before interpreting a report. Treat reports as navigation aids, metrics as measured results, manifests as lineage, and logs as execution evidence.

## Quick Start

Run the bundled read-only locator from the repository root:

```bash
python3 .codex/skills/locate-experiment-evidence/scripts/experiment_evidence.py find "QUERY"
python3 .codex/skills/locate-experiment-evidence/scripts/experiment_evidence.py audit PATH
```

Use `--json` for machine-readable output and `--kind report|metrics|config|manifest|log|input|model` to narrow a search. The script never launches AirSim and never writes into experiment directories.

## Workflow

1. Search with the user's exact report name, experiment ID, seed, scale, date, or distinctive metric.
2. Identify the experiment root. Do not mix a summary report with a similarly named older output directory.
3. Read evidence in this order:
   - scenario, settings, protocol, and command;
   - manifest, hashes, frozen tracker/model, and input lineage;
   - metrics JSON/CSV and per-seed records;
   - report and figures;
   - logs for failures, timeouts, and environment details.
4. Run `audit` on the narrowest experiment directory that contains the evidence. Treat its verdict as triage, then verify every claimed prerequisite by opening the cited files.
5. Build an evidence map with absolute file links and state which artifact is authoritative for each parameter and result.
6. Classify reproducibility separately:
   - exact simulator rerun;
   - deterministic offline replay;
   - metrics-only rescoring;
   - evidence inspection only.
7. List missing prerequisites instead of reconstructing them from memory or a prose report.

Read [reproducibility-contract.md](references/reproducibility-contract.md) when judging whether a result is reproducible or when defining a new experiment output contract.

## MSM Rules

- Keep formal, validation, diagnostic, offline replay, preflight, and failed-closed outputs separate.
- Never use AirSim Actor names or truth IDs as online association inputs. Truth files are offline scoring evidence.
- Record target/resource count, seed set, corruption level, scan count, camera profile, ClockSpeed, simulator mode, deadline, and metric denominator.
- Check whether a result uses all rounds, the last round, active confirmed relations, or cumulative-ever-confirmed relations.
- Check `measurement_timestamp` and `arrival_timestamp` when timing affects the conclusion.
- Do not infer the executed source revision from the current Git HEAD. Require a recorded commit or state that provenance is missing.
- A command alone does not prove reproducibility. Require its configuration, inputs, seeds, dependency/simulator versions, and output acceptance rule.
- Prefer offline replay before a real AirSim rerun when frozen anonymous observations exist.
- Do not overwrite an existing output directory. Use a new run ID and preserve the original evidence.
- Do not start AirSim, retrain a model, or open held-out truth merely to answer a location or audit request. Obtain explicit user intent first.

## Reproduction Procedure

When the user explicitly asks to reproduce an experiment:

1. Record current `git rev-parse HEAD` and `git status --short`; do not claim they match the original run unless the manifest proves it.
2. Verify input, settings, model, and manifest hashes before execution.
3. Reconstruct the command only from recorded arguments or the owning entry point's documented CLI. Mark any inferred argument.
4. Run an offline replay first when possible and compare per-seed metrics, not only the final Markdown report.
5. For AirSim, use the `airsim-runtime` skill, preserve launch/reset order, and write to a new output root.
6. Compare configuration fingerprints, row counts, metric definitions, availability, and tolerances. Separate deterministic equality from statistically consistent reruns.
7. Report changed environment, nondeterminism, and missing artifacts even if headline metrics are close.

## Required Answer Shape

Return these sections when useful:

- **Experiment identity:** run ID, status, date, seed/scale, source report.
- **Evidence map:** configuration, command, inputs, models, metrics, logs, figures.
- **Measured result:** exact metric source and denominator.
- **Reproducibility verdict:** exact rerun, offline replay, rescoring, and inspection status.
- **Missing conditions:** concrete absent files, versions, hashes, or commands.
- **Next action:** the safest command or evidence repair, without starting an expensive run unless requested.
