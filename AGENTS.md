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

- Strict execution flow for module work: main dispatches the task, the owning subagent edits its own files and runs its own tests, and main only integrates, verifies, and summarizes the result.
- Main must not directly implement or document D1-D7 module-owned logic, GAP updates, PLAN updates, or review updates unless the user explicitly authorizes an emergency main-owned hotfix.
- If main performs an emergency cross-module hotfix, main must mark that fact in the final answer and then ask the owning subagent to review and align its README/PLAN/GAP before the work is considered complete.
- For any module capability change, the owning subagent must check whether its README, PLAN, GAP audit, and review file need updates; if they do, the owning subagent updates them in the same task.
- Do not keep all D1-D7 open. The concurrent subagent limit is 6.
- Close completed subagents immediately.
- Do not store ephemeral agent IDs as long-term truth.
- Every subagent task must define owned paths and tests.
- Subagents must not modify files outside their ownership boundary unless main explicitly coordinates it.
- Main owns AirSim launch/reset/episode order/log collection and final reports.

### Mandatory Documentation Sync After GAP Work

Documentation synchronization is part of GAP completion and does not require a separate user reminder.

- Whenever a task closes, partially closes, reclassifies, or adds evidence for a P0/P1/P2/P3 GAP, the owning D1-D7 subagent must update the affected module documentation in the same task.
- The same rule applies when a task changes an algorithm, interface, data contract, state machine, threshold, default/optional capability status, AirSim adapter, validation result, or implementation plan.
- Before reporting completion, the owning subagent must inspect all of the following within its ownership boundary and update every affected file:
  - module `README.md`;
  - module `PLAN.md`;
  - module GAP audit and review files under `subagent_reviews/Dx_*`;
  - `docs/MODULE_PRINCIPLES_CN.md`;
  - `docs/ALGORITHM_AND_IMPLEMENTATION.md`;
  - `docs/AIRSIM_INTEGRATION_PLAN.md` and `docs/EXPERIMENT_REPORT.md` when the change affects AirSim integration or experimental evidence.
- Do not create unrelated documentation churn. If an inspected file does not need modification, the subagent must explicitly report that it was checked and why no update was required.
- Documentation must distinguish implemented and tested behavior from interface-only, optional/offline, unavailable, planned, or unimplemented behavior. It must include the actual validation date, scenario, seed/sample count, result, acceptance threshold, and remaining limitation when evidence changes.
- A GAP implementation task is not complete until the owning subagent has synchronized the affected documentation and run its requested code tests plus documentation format checks.
- After module owners finish, main must update affected main-level GAP/status documents and root system reports for cross-module changes, verify terminology and contract consistency, and state the documentation synchronization result in the final summary.

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
