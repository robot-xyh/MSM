"""Anonymous target-hypothesis to local-track experiment package.

Exports are loaded lazily so deterministic geometry users do not import the
optional learned-model stack.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "AsynchronousPairFitQuality": (".geometry", "AsynchronousPairFitQuality"),
    "BearingObservation": (".contracts", "BearingObservation"),
    "CausalityError": (".geometry", "CausalityError"),
    "ConfirmedTrackPair": (".contracts", "ConfirmedTrackPair"),
    "FeatureNormalizer": (".model", "FeatureNormalizer"),
    "FiveInitializationConfig": (".training", "FiveInitializationConfig"),
    "GeometryFitError": (".geometry", "GeometryFitError"),
    "PAIR_PUBLICATION_ROUTE": (".contracts", "PAIR_PUBLICATION_ROUTE"),
    "PAIR_PUBLICATION_SCHEMA_VERSION": (
        ".contracts",
        "PAIR_PUBLICATION_SCHEMA_VERSION",
    ),
    "TargetHypothesis": (".contracts", "TargetHypothesis"),
    "TargetTrackAssignment": (".deterministic", "TargetTrackAssignment"),
    "TargetTrackCostGNN": (".model", "TargetTrackCostGNN"),
    "TargetTrackGate": (".graph", "TargetTrackGate"),
    "TargetTrackGraph": (".contracts", "TargetTrackGraph"),
    "TargetTrackPublication": (".contracts", "TargetTrackPublication"),
    "TargetTrackTrainingExample": (".training", "TargetTrackTrainingExample"),
    "WeightedFitConfig": (".geometry", "WeightedFitConfig"),
    "balanced_multiscale_samples": (".training", "balanced_multiscale_samples"),
    "build_camera_graphs": (".graph", "build_camera_graphs"),
    "build_target_track_graph": (".graph", "build_target_track_graph"),
    "evaluate_asynchronous_track_pair": (
        ".geometry",
        "evaluate_asynchronous_track_pair",
    ),
    "form_target_hypothesis": (".geometry", "form_target_hypothesis"),
    "freeze_model": (".model", "freeze_model"),
    "load_frozen_model": (".model", "load_frozen_model"),
    "online_pair_publication_fingerprint": (
        ".contracts",
        "online_pair_publication_fingerprint",
    ),
    "publish_with_confirmation": (".deterministic", "publish_with_confirmation"),
    "route_costs": (".assignment", "route_costs"),
    "solve_camera_graphs": (".assignment", "solve_camera_graphs"),
    "solve_deterministic_assignment": (
        ".deterministic",
        "solve_deterministic_assignment",
    ),
    "solve_target_track_assignment": (
        ".assignment",
        "solve_target_track_assignment",
    ),
    "train_and_freeze_five_initializations": (
        ".training",
        "train_and_freeze_five_initializations",
    ),
    "validate_online_pair_publication": (
        ".contracts",
        "validate_online_pair_publication",
    ),
    "weighted_line_of_sight_fit": (".geometry", "weighted_line_of_sight_fit"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

__all__ = [
    "AsynchronousPairFitQuality",
    "BearingObservation",
    "CausalityError",
    "ConfirmedTrackPair",
    "FeatureNormalizer",
    "FiveInitializationConfig",
    "GeometryFitError",
    "PAIR_PUBLICATION_ROUTE",
    "PAIR_PUBLICATION_SCHEMA_VERSION",
    "TargetHypothesis",
    "TargetTrackAssignment",
    "TargetTrackCostGNN",
    "TargetTrackGate",
    "TargetTrackGraph",
    "TargetTrackPublication",
    "TargetTrackTrainingExample",
    "WeightedFitConfig",
    "balanced_multiscale_samples",
    "build_camera_graphs",
    "build_target_track_graph",
    "evaluate_asynchronous_track_pair",
    "form_target_hypothesis",
    "freeze_model",
    "load_frozen_model",
    "online_pair_publication_fingerprint",
    "publish_with_confirmation",
    "route_costs",
    "solve_camera_graphs",
    "solve_deterministic_assignment",
    "solve_target_track_assignment",
    "train_and_freeze_five_initializations",
    "validate_online_pair_publication",
    "weighted_line_of_sight_fit",
]
