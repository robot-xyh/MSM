"""D7 cooperative-guidance binding topology contracts.

The helper expands already ordered D3 resource/target demand into passive D7
bindings. It is not an assignment optimizer and does not create AirSim pairs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .terminal_gate import (
    AssignmentGuidanceBinding,
    COORDINATION_MODES,
    TERMINAL_AUTHORIZATION_SCOPES,
)


COOPERATIVE_TOPOLOGY_BOUNDARY = (
    "d7_binding_topology_only_no_assignment_optimization_no_vehicle_control"
)


@dataclass(frozen=True)
class CooperativeGuidanceTargetTopology:
    target_id: str
    required_count: int
    primary_count: int
    reserve_count: int
    coordination_mode: str
    resource_ids: tuple[str, ...]
    terminal_authorization_scope: str = "coalition"
    arrival_coordination_required: bool = True


@dataclass(frozen=True)
class CooperativeGuidanceTopology:
    """Expanded D7 bindings and resources not consumed by demand slots."""

    plan_id: str
    plan_version: int
    bindings: tuple[AssignmentGuidanceBinding, ...]
    targets: tuple[CooperativeGuidanceTargetTopology, ...]
    unassigned_resource_ids: tuple[str, ...]
    boundary: str = COOPERATIVE_TOPOLOGY_BOUNDARY
    assignment_optimized: bool = False
    default_runtime_selector_changed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "bindings": [asdict(binding) for binding in self.bindings],
            "targets": [asdict(target) for target in self.targets],
            "unassigned_resource_ids": list(self.unassigned_resource_ids),
            "boundary": self.boundary,
            "assignment_optimized": self.assignment_optimized,
            "default_runtime_selector_changed": self.default_runtime_selector_changed,
        }


@dataclass(frozen=True)
class CooperativeGuidanceTopologyValidation:
    valid: bool
    errors: tuple[str, ...]
    binding_count: int
    resource_count: int
    target_count: int
    primary_binding_count: int
    reserve_binding_count: int
    standby_reserve_count: int
    per_target_counts: dict[str, dict[str, int]]


def build_cooperative_guidance_topology(
    *,
    resource_ids: Sequence[str],
    target_ids: Sequence[str],
    required_counts: Mapping[str, int] | Sequence[int],
    coordination_mode: str | Mapping[str, str] = "hybrid",
    primary_count: int | Mapping[str, int] = 2,
    plan_id: str = "d7-cooperative-topology",
    plan_version: int = 1,
    owner_node_id: str = "center",
    authorization_state: str = "approved",
    track_versions: int | Mapping[str, int] = 1,
    coalition_versions: int | Mapping[str, int] = 1,
    coalition_epochs: int | Mapping[str, int] | None = None,
    vehicle_names: Mapping[str, str] | None = None,
    arrival_windows: Mapping[str, tuple[float, float]] | None = None,
    terminal_authorization_scope: str | Mapping[str, str] = "coalition",
    arrival_coordination_required: bool | Mapping[str, bool] = True,
) -> CooperativeGuidanceTopology:
    """Expand ordered D3 resources into arbitrary N/M D7 coalition bindings.

    Resource ordering is authoritative: the helper fills target demand slots
    in target order. It does not solve assignment cost or mutate target IDs.
    Coordinated bindings without an explicit arrival window remain fail-closed
    in the terminal gate until main/D3 supplies one, except for active primaries
    explicitly configured as ``per_primary`` with arrival coordination disabled.
    """

    resources = _unique_nonempty_ids(resource_ids, "resource_ids")
    targets = _unique_nonempty_ids(target_ids, "target_ids")
    if not targets:
        raise ValueError("target_ids must not be empty")
    if plan_version <= 0:
        raise ValueError("plan_version must be positive")
    demand = _target_int_values(targets, required_counts, "required_counts")
    if any(value <= 0 for value in demand.values()):
        raise ValueError("required counts must be positive")
    total_required = sum(demand.values())
    if total_required > len(resources):
        raise ValueError(
            f"insufficient resources: required={total_required}, available={len(resources)}"
        )

    modes = _target_string_values(targets, coordination_mode, "coordination_mode")
    invalid_modes = sorted({mode for mode in modes.values() if mode not in COORDINATION_MODES})
    if invalid_modes:
        raise ValueError(f"unsupported coordination modes: {invalid_modes}")
    authorization_scopes = _target_string_values(
        targets,
        terminal_authorization_scope,
        "terminal_authorization_scope",
    )
    invalid_scopes = sorted(
        {
            scope
            for scope in authorization_scopes.values()
            if scope not in TERMINAL_AUTHORIZATION_SCOPES
        }
    )
    if invalid_scopes:
        raise ValueError(f"unsupported terminal authorization scopes: {invalid_scopes}")
    arrival_coordination_by_target = _target_bool_values(
        targets,
        arrival_coordination_required,
        "arrival_coordination_required",
    )
    requested_primary = _target_int_values(targets, primary_count, "primary_count")
    if any(value <= 0 for value in requested_primary.values()):
        raise ValueError("primary counts must be positive")
    track_version_by_target = _target_int_values(targets, track_versions, "track_versions")
    coalition_version_by_target = _target_int_values(
        targets,
        coalition_versions,
        "coalition_versions",
    )
    epoch_by_target = (
        _target_int_values(targets, coalition_epochs, "coalition_epochs")
        if coalition_epochs is not None
        else {target_id: plan_version for target_id in targets}
    )

    bindings: list[AssignmentGuidanceBinding] = []
    target_topologies: list[CooperativeGuidanceTargetTopology] = []
    resource_cursor = 0
    for target_index, target_id in enumerate(targets):
        required_count = demand[target_id]
        effective_primary_count = min(requested_primary[target_id], required_count)
        allocated_resources = resources[resource_cursor : resource_cursor + required_count]
        resource_cursor += required_count
        mode = modes[target_id] if required_count > 1 else "independent"
        authorization_scope = authorization_scopes[target_id]
        target_arrival_coordination_required = arrival_coordination_by_target[target_id]
        window = (arrival_windows or {}).get(target_id)
        if window is not None and (len(window) != 2 or window[1] < window[0]):
            raise ValueError(f"invalid arrival window for target {target_id}")
        cooperative_target = required_count > 1
        coalition_id = (
            f"{plan_id}:{target_id}:coalition" if cooperative_target else None
        )

        for member_index, resource_id in enumerate(allocated_resources):
            is_primary = member_index < effective_primary_count
            member_role = "primary" if is_primary else "reserve"
            wave_id = 0 if is_primary else 1
            activation_state = "active" if is_primary else "standby"
            bindings.append(
                AssignmentGuidanceBinding(
                    plan_id=plan_id,
                    plan_version=plan_version,
                    owner_node_id=owner_node_id,
                    assignment_id=(
                        f"{plan_id}:{resource_id}->{target_id}:slot-{member_index}"
                    ),
                    resource_id=resource_id,
                    vehicle_name=(vehicle_names or {}).get(resource_id, resource_id),
                    assigned_global_track_id=target_id,
                    track_version=track_version_by_target[target_id],
                    authorization_state=authorization_state,
                    coalition_id=coalition_id,
                    coalition_version=(
                        coalition_version_by_target[target_id]
                        if cooperative_target
                        else None
                    ),
                    coalition_epoch=(
                        epoch_by_target[target_id] if cooperative_target else None
                    ),
                    member_role=member_role,
                    wave_id=wave_id,
                    coordination_mode=mode,
                    arrival_window_start_s=window[0] if window is not None else None,
                    arrival_window_end_s=window[1] if window is not None else None,
                    activation_state=activation_state,
                    terminal_authorization_scope=authorization_scope,
                    arrival_coordination_required=target_arrival_coordination_required,
                    metadata={
                        "boundary": COOPERATIVE_TOPOLOGY_BOUNDARY,
                        "topology_contract_only": True,
                        "target_order_index": target_index,
                        "member_order_index": member_index,
                        "required_resource_count": required_count,
                        "primary_count": effective_primary_count,
                        "arrival_window_required_before_terminal_png": (
                            mode in {"simultaneous", "sequential", "hybrid"}
                            and window is None
                            and not (
                                is_primary
                                and authorization_scope == "per_primary"
                                and not target_arrival_coordination_required
                            )
                        ),
                    },
                )
            )
        target_topologies.append(
            CooperativeGuidanceTargetTopology(
                target_id=target_id,
                required_count=required_count,
                primary_count=effective_primary_count,
                reserve_count=required_count - effective_primary_count,
                coordination_mode=mode,
                resource_ids=tuple(allocated_resources),
                terminal_authorization_scope=authorization_scope,
                arrival_coordination_required=target_arrival_coordination_required,
            )
        )

    topology = CooperativeGuidanceTopology(
        plan_id=plan_id,
        plan_version=plan_version,
        bindings=tuple(bindings),
        targets=tuple(target_topologies),
        unassigned_resource_ids=tuple(resources[resource_cursor:]),
    )
    validation = validate_cooperative_guidance_topology(topology)
    if not validation.valid:
        raise ValueError("invalid generated topology: " + "; ".join(validation.errors))
    return topology


def validate_cooperative_guidance_topology(
    topology: CooperativeGuidanceTopology,
) -> CooperativeGuidanceTopologyValidation:
    """Validate D7 member roles/waves/activation without running guidance."""

    errors: list[str] = []
    resource_ids = [binding.resource_id for binding in topology.bindings]
    if len(resource_ids) != len(set(resource_ids)):
        errors.append("resource_assigned_more_than_once")
    per_target_counts: dict[str, dict[str, int]] = {}
    expected = {target.target_id: target for target in topology.targets}
    for target_id, target in expected.items():
        rows = [
            binding
            for binding in topology.bindings
            if binding.assigned_global_track_id == target_id
        ]
        primaries = [binding for binding in rows if binding.member_role == "primary"]
        reserves = [binding for binding in rows if binding.member_role == "reserve"]
        active_primaries = [
            binding for binding in primaries if binding.activation_state == "active"
        ]
        standby_reserves = [
            binding for binding in reserves if binding.activation_state == "standby"
        ]
        per_target_counts[target_id] = {
            "required": target.required_count,
            "bindings": len(rows),
            "primary": len(primaries),
            "reserve": len(reserves),
            "active_primary": len(active_primaries),
            "standby_reserve": len(standby_reserves),
        }
        if len(rows) != target.required_count:
            errors.append(f"{target_id}:required_count_mismatch")
        if len(primaries) != target.primary_count:
            errors.append(f"{target_id}:primary_count_mismatch")
        if len(reserves) != target.reserve_count:
            errors.append(f"{target_id}:reserve_count_mismatch")
        if len(active_primaries) != len(primaries):
            errors.append(f"{target_id}:primary_not_active")
        if len(standby_reserves) != len(reserves):
            errors.append(f"{target_id}:reserve_not_standby")
        if any(binding.wave_id != 0 for binding in primaries):
            errors.append(f"{target_id}:primary_wave_invalid")
        if any(binding.wave_id <= 0 for binding in reserves):
            errors.append(f"{target_id}:reserve_wave_invalid")
        if any(
            binding.terminal_authorization_scope
            != target.terminal_authorization_scope
            for binding in rows
        ):
            errors.append(f"{target_id}:terminal_authorization_scope_mismatch")
        if any(
            binding.arrival_coordination_required
            != target.arrival_coordination_required
            for binding in rows
        ):
            errors.append(f"{target_id}:arrival_coordination_policy_mismatch")

    unknown_targets = sorted(
        {
            binding.assigned_global_track_id
            for binding in topology.bindings
            if binding.assigned_global_track_id not in expected
        }
    )
    if unknown_targets:
        errors.append(f"unknown_targets:{','.join(unknown_targets)}")
    return CooperativeGuidanceTopologyValidation(
        valid=not errors,
        errors=tuple(errors),
        binding_count=len(topology.bindings),
        resource_count=len(set(resource_ids)),
        target_count=len(expected),
        primary_binding_count=sum(
            1 for binding in topology.bindings if binding.member_role == "primary"
        ),
        reserve_binding_count=sum(
            1 for binding in topology.bindings if binding.member_role == "reserve"
        ),
        standby_reserve_count=sum(
            1
            for binding in topology.bindings
            if binding.member_role == "reserve" and binding.activation_state == "standby"
        ),
        per_target_counts=per_target_counts,
    )


def _unique_nonempty_ids(values: Sequence[str], name: str) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{name} must contain nonempty IDs")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicate IDs")
    return normalized


def _target_int_values(
    target_ids: tuple[str, ...],
    values: int | Mapping[str, int] | Sequence[int] | None,
    name: str,
) -> dict[str, int]:
    if values is None:
        raise ValueError(f"{name} is required")
    if isinstance(values, int):
        return {target_id: int(values) for target_id in target_ids}
    if isinstance(values, Mapping):
        missing = [target_id for target_id in target_ids if target_id not in values]
        if missing:
            raise ValueError(f"{name} missing targets: {missing}")
        return {target_id: int(values[target_id]) for target_id in target_ids}
    sequence = tuple(int(value) for value in values)
    if len(sequence) != len(target_ids):
        raise ValueError(f"{name} length must match target_ids")
    return dict(zip(target_ids, sequence, strict=True))


def _target_string_values(
    target_ids: tuple[str, ...],
    values: str | Mapping[str, str],
    name: str,
) -> dict[str, str]:
    if isinstance(values, str):
        return {target_id: values.strip().lower() for target_id in target_ids}
    missing = [target_id for target_id in target_ids if target_id not in values]
    if missing:
        raise ValueError(f"{name} missing targets: {missing}")
    return {
        target_id: str(values[target_id]).strip().lower()
        for target_id in target_ids
    }


def _target_bool_values(
    target_ids: tuple[str, ...],
    values: bool | Mapping[str, bool],
    name: str,
) -> dict[str, bool]:
    if isinstance(values, bool):
        return {target_id: values for target_id in target_ids}
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be bool or a target mapping")
    missing = [target_id for target_id in target_ids if target_id not in values]
    if missing:
        raise ValueError(f"{name} missing targets: {missing}")
    invalid = [target_id for target_id in target_ids if not isinstance(values[target_id], bool)]
    if invalid:
        raise TypeError(f"{name} must contain bool values for targets: {invalid}")
    return {target_id: values[target_id] for target_id in target_ids}
