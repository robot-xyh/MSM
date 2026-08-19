"""Independent lightweight baselines for dual-optical track association."""

from .ablation import promotion_decision, run_candidate_ablation
from .assignment import solve_probability_assignment
from .models import (
    GEOMETRY_COMPONENT_NAMES,
    LOGISTIC_C_GRID,
    PROBABILITY_THRESHOLD_GRID,
    LightweightModel,
    fit_all_models,
    geometry_components,
)
from .benchmark_adapter import (
    SharedSnapshotLightweightAdapter,
    read_shared_snapshot,
)
from .online import (
    FrozenRoute,
    OnlineAssociationPublication,
    OnlineLightweightAdapter,
    RevolutionSnapshot,
)
from .online_benchmark import (
    FrozenLightweightRoute,
    freeze_route,
    load_frozen_route,
)

__all__ = [
    "GEOMETRY_COMPONENT_NAMES",
    "LOGISTIC_C_GRID",
    "PROBABILITY_THRESHOLD_GRID",
    "LightweightModel",
    "FrozenRoute",
    "OnlineAssociationPublication",
    "OnlineLightweightAdapter",
    "RevolutionSnapshot",
    "SharedSnapshotLightweightAdapter",
    "FrozenLightweightRoute",
    "fit_all_models",
    "geometry_components",
    "freeze_route",
    "load_frozen_route",
    "read_shared_snapshot",
    "promotion_decision",
    "run_candidate_ablation",
    "solve_probability_assignment",
]
