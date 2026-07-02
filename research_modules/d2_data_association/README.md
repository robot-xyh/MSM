# D2 Data Association Research Module

Offline research module for reducing ID switches in synthetic multi-target tracking scenarios. The runnable path uses only NumPy, SciPy, and pytest.

Safety boundary: this module is limited to simulation and offline evaluation. It does not contain real fire-control parameters, damage logic, hardware drivers, live flight control, automatic disposition, or authorization bypass.

## Contents

- `d2_data_association/models.py`: `Detection`, `GlobalTrack`, `AssociationResult`, and lifecycle data classes.
- `d2_data_association/gating.py`: Mahalanobis `d^2` gating and optional feature cost.
- `d2_data_association/associators.py`: `DataAssociator`, `GNNHungarianAssociator`, `JPDAAssociator`, and `MHTAssociator`.
- `d2_data_association/tracker.py`: constant-velocity Kalman fallback and track state machine.
- `d2_data_association/metrics.py`: ID switch, continuity, duplicate assignment, RMSE, and confusion matrix.
- `d2_data_association/simulation.py`: crossing, formation, occlusion, missed-detection, and false-alarm scenarios.
- `scripts/run_simulation.py`: CLI benchmark runner.
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`: detailed Chinese algorithm and implementation guide.
- `docs/EXPERIMENT_REPORT.md`: baseline results and interpretation.
- `docs/AIRSIM_INTEGRATION_PLAN.md`: offline log ingestion plan.

## Run Tests

From this module directory:

```bash
pytest -q
```

From the repository root:

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

## Run Simulations

```bash
python3 scripts/run_simulation.py --steps 24 --seed 7
```

Optional outputs:

```bash
python3 scripts/run_simulation.py \
  --steps 36 \
  --seed 7 \
  --json-out artifacts/d2_results.json \
  --markdown-out artifacts/d2_results.md
```

## Documentation

Read `docs/ALGORITHM_AND_IMPLEMENTATION.md` first for the Chinese design guide covering GNN/Hungarian, JPDA, MHT, gating, lifecycle management, proactive degradation risk signals, metrics, and D1/D3/D4/D5/D6 interfaces. `docs/EXPERIMENT_REPORT.md` keeps the benchmark interpretation and figure references.

## Optional Integrations

`filterpy` and `stonesoup` are not runtime dependencies. `d2_data_association/compat.py` exposes availability checks and explicit placeholder adapters for future research environments.
