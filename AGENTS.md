# Repository Guidelines

## Project Structure

MSM is a Python research and simulation repository for a C-UAS multi-UAV interception workflow.

- `research_modules/` contains D1-D7 research modules, integration contracts, integrated point-mass simulation, AirSim dry-run adapters, and real AirSim runtime code.
- `research_modules/airsim_runtime/` owns real AirSim Blocks orchestration, settings generation, episode sequencing, SimpleFlight control tests, and AirSim output reports.
- `subagent_reviews/` contains module reviews, GAP audits, and main-level integration decisions.
- `agents/` contains stable project subagent definitions. Use these before spawning or resuming subagents.
- `legacy doc/` contains historical source reports.
- `research_modules/airsim_runtime/outputs/` contains generated experiment outputs. Do not treat these as source unless the user asks to preserve a specific report.

## Build And Test Commands

Run commands from the repository root.

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
python3 -m pytest -q research_modules/d3_assignment_planner/tests
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
pytest -q research_modules/d5_terminal_association/tests
pytest -q research_modules/d6_evaluation_metrics/tests
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
```

Use `python3 -m py_compile` for quick syntax checks on changed Python entry points.

## Agent Workflow

Main agent is the global orchestrator. D1-D7 are module owners.

Before creating subagents, read `agents/README.md` and the relevant role file:

- `agents/main-agent.md`
- `agents/d1_sensor_fusion.md`
- `agents/d2_data_association.md`
- `agents/d3_assignment_planner.md`
- `agents/d4_distributed_fallback.md`
- `agents/d5_terminal_association.md`
- `agents/d6_evaluation_metrics.md`
- `agents/d7_proportional_guidance.md`

Subagent rules:

- Do not keep all D1-D7 open. The concurrent subagent limit is 6.
- Close completed subagents immediately.
- Do not store ephemeral agent IDs as long-term truth.
- Every subagent task must define owned paths and tests.
- Subagents must not modify files outside their ownership boundary unless main explicitly coordinates it.
- Main owns AirSim launch/reset/episode order/log collection and final reports.

## Core System Rules

- Simulation scale is set by main through `--drone-count N`; algorithms must not hard-code 2v2 or 5v5.
- 2v2 and 5v5 are baseline scenario names, not algorithm limits.
- Keep `measurement_timestamp` and `arrival_timestamp` when handling observations.
- Carry covariance on observations and tracks.
- Use NED as the fusion working frame; WGS84 is only an external reference.
- `global_track_id` is center-owned. D5 and D7 must never rewrite or locally rebind it.
- Every assignment plan is versioned, and stale versions must be rejected.
- D2 and D6 must keep `id_switch_count` explicit.

## AirSim Runtime Rules

- Use one AirSim Blocks launch with reset-separated episodes when possible.
- Do not save PNG screenshots by default. Use `--save-images` only when debugging camera views.
- Intruder targets in current AirSim interception tests are moved actor targets, not SimpleFlight vehicles.
- Target detection currently uses AirSim `simGetDetections` metadata unless a specific YOLO path is requested.
- For ComputerVision tests, online D5 association must not use AirSim truth IDs; truth IDs are offline evaluation labels only.
- SimpleFlight control tests should report `control_commands.csv`, `intercept_summary.json`, D6 metrics, and a Markdown report.

## Coding Style

- Keep edits scoped to the requested module.
- Do not mix broad formatting churn with functional changes.
- Prefer dataclasses and typed interfaces already used in the repo.
- Use `rg` for search.
- Use `apply_patch` for manual file edits.

## Generated Outputs

Generated AirSim and experiment outputs may be large. Keep them in module output folders. Only cite or preserve outputs that are relevant to the current user request.

## Commit Guidance

Before commit/push requests, inspect `git status --short`. Do not revert unrelated user or generated changes. If committing in batches, group by subsystem: runtime, D1-D7 module, docs/reports.
