"""End-to-end offline integration simulation for D1-D6 research modules.

The package is limited to synthetic point-mass simulation, record generation,
and offline evaluation. It does not provide hardware drivers, real vehicle
control, automatic disposition, or authorization bypasses.
"""

from .models import EpisodeResult, ScenarioConfig
from .runner import IntegratedEpisodeRunner, run_integrated_episode
from .scenario import make_standard_scenario

__all__ = [
    "EpisodeResult",
    "IntegratedEpisodeRunner",
    "ScenarioConfig",
    "make_standard_scenario",
    "run_integrated_episode",
]
