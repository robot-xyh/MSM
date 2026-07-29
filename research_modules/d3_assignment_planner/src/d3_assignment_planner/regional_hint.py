"""D3-owned contracts for optional regional candidate-graph advice."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


REGIONAL_PLANNING_HINT_SCHEMA_V1 = "d3_regional_planning_hint_v1"
REGIONAL_PLANNING_HINT_SUCCESSOR_SCHEMA_V1 = (
    "d3_regional_planning_hint_successor_v1"
)
REGIONAL_HINT_OWNER_LAYERS = frozenset(
    {"center", "secondary", "distributed", "hold"}
)

_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "actor_truth_id",
        "global_track_id",
        "object_id",
        "object_name",
        "object_truth_id",
        "resource_id",
        "target_id",
        "target_truth_id",
        "truth_id",
    }
)
_HINT_FIELDS = frozenset(
    {
        "advisory_id",
        "advisory_version",
        "constraints",
        "created_at_s",
        "expires_at_s",
        "projected",
        "schema",
        "source_plan_id",
        "source_plan_version",
        "transfer_allowances",
    }
)
_CONSTRAINT_FIELDS = frozenset(
    {
        "hold",
        "lease_expires_at_s",
        "owner_epoch",
        "owner_id",
        "owner_layer",
        "region_id",
        "request_replan",
        "reserve_ratio",
        "resource_quota_delta",
        "source_plan_id",
        "source_plan_version",
    }
)
_TRANSFER_FIELDS = frozenset(
    {
        "edge_id",
        "expected_transfer_time_s",
        "resource_count",
        "source_region_id",
        "target_region_id",
    }
)


class RegionalPlanningHintError(ValueError):
    """Stable fail-closed reason for malformed or inapplicable advice."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = str(reason)


@dataclass(frozen=True)
class RegionalPlanningConstraint:
    """One region's authority fence and aggregate resource constraint."""

    region_id: str
    owner_id: str | None
    owner_layer: str
    owner_epoch: int
    lease_expires_at_s: float
    source_plan_id: str
    source_plan_version: int
    resource_quota_delta: int
    reserve_ratio: float
    hold: bool
    request_replan: bool

    def __post_init__(self) -> None:
        region_id = _required_text(self.region_id, "constraint region_id")
        owner_layer = _required_text(
            self.owner_layer, "constraint owner_layer"
        ).lower()
        if owner_layer not in REGIONAL_HINT_OWNER_LAYERS:
            raise RegionalPlanningHintError(
                "regional_hint_owner_layer_unsupported",
                f"unsupported regional hint owner layer: {owner_layer}",
            )
        owner_id = _optional_text(self.owner_id, "constraint owner_id")
        if owner_layer == "hold":
            if owner_id is not None:
                raise RegionalPlanningHintError(
                    "regional_hint_hold_owner_invalid",
                    "hold constraints cannot expose an active owner id",
                )
        elif owner_id is None:
            raise RegionalPlanningHintError(
                "regional_hint_owner_missing",
                "active regional constraints require an owner id",
            )
        owner_epoch = _strict_non_negative_int(
            self.owner_epoch, "constraint owner_epoch"
        )
        lease = _finite_non_negative(
            self.lease_expires_at_s, "constraint lease_expires_at_s"
        )
        source_plan_id = _required_text(
            self.source_plan_id, "constraint source_plan_id"
        )
        source_plan_version = _strict_non_negative_int(
            self.source_plan_version, "constraint source_plan_version"
        )
        quota_delta = _strict_int(
            self.resource_quota_delta, "constraint resource_quota_delta"
        )
        reserve_ratio = _unit_interval(
            self.reserve_ratio, "constraint reserve_ratio"
        )
        hold = _strict_bool(self.hold, "constraint hold")
        request_replan = _strict_bool(
            self.request_replan, "constraint request_replan"
        )
        object.__setattr__(self, "region_id", region_id)
        object.__setattr__(self, "owner_id", owner_id)
        object.__setattr__(self, "owner_layer", owner_layer)
        object.__setattr__(self, "owner_epoch", owner_epoch)
        object.__setattr__(self, "lease_expires_at_s", lease)
        object.__setattr__(self, "source_plan_id", source_plan_id)
        object.__setattr__(self, "source_plan_version", source_plan_version)
        object.__setattr__(self, "resource_quota_delta", quota_delta)
        object.__setattr__(self, "reserve_ratio", reserve_ratio)
        object.__setattr__(self, "hold", hold)
        object.__setattr__(self, "request_replan", request_replan)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionalPlanningConstraint":
        payload = _strict_mapping(
            value,
            allowed_fields=_CONSTRAINT_FIELDS,
            context="regional constraint",
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionalTransferAllowance:
    """A bounded incremental transfer beyond the bound source plan.

    Existing cross-region assignments in ``source_plan_id/version`` are
    inherited only on their exact target-resource edges.  They do not consume
    this allowance and this DTO never grants an assignment by itself.
    """

    source_region_id: str
    target_region_id: str
    resource_count: int
    edge_id: str
    expected_transfer_time_s: float

    def __post_init__(self) -> None:
        source = _required_text(
            self.source_region_id, "transfer source_region_id"
        )
        target = _required_text(
            self.target_region_id, "transfer target_region_id"
        )
        if source == target:
            raise RegionalPlanningHintError(
                "regional_hint_transfer_self_loop",
                "regional transfer allowances must cross regions",
            )
        count = _strict_positive_int(self.resource_count, "transfer resource_count")
        edge_id = _required_text(self.edge_id, "transfer edge_id")
        transfer_time = _finite_non_negative(
            self.expected_transfer_time_s,
            "transfer expected_transfer_time_s",
        )
        object.__setattr__(self, "source_region_id", source)
        object.__setattr__(self, "target_region_id", target)
        object.__setattr__(self, "resource_count", count)
        object.__setattr__(self, "edge_id", edge_id)
        object.__setattr__(self, "expected_transfer_time_s", transfer_time)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "RegionalTransferAllowance":
        payload = _strict_mapping(
            value,
            allowed_fields=_TRANSFER_FIELDS,
            context="regional transfer allowance",
        )
        return cls(**payload)


@dataclass(frozen=True)
class RegionalPlanningHint:
    """Versioned previous-plan advice consumed only by the next D3 solve."""

    advisory_id: str
    advisory_version: int
    created_at_s: float
    expires_at_s: float
    source_plan_id: str
    source_plan_version: int
    projected: bool
    constraints: tuple[RegionalPlanningConstraint, ...]
    transfer_allowances: tuple[RegionalTransferAllowance, ...]
    schema: str = REGIONAL_PLANNING_HINT_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema != REGIONAL_PLANNING_HINT_SCHEMA_V1:
            raise RegionalPlanningHintError(
                "regional_hint_schema_unsupported",
                f"unsupported regional planning hint schema: {self.schema}",
            )
        advisory_id = _required_text(self.advisory_id, "hint advisory_id")
        advisory_version = _strict_positive_int(
            self.advisory_version, "hint advisory_version"
        )
        created_at_s = _finite_non_negative(
            self.created_at_s, "hint created_at_s"
        )
        expires_at_s = _finite_non_negative(
            self.expires_at_s, "hint expires_at_s"
        )
        if expires_at_s <= created_at_s:
            raise RegionalPlanningHintError(
                "regional_hint_time_window_invalid",
                "regional hint expiry must be later than creation",
            )
        source_plan_id = _required_text(self.source_plan_id, "hint source_plan_id")
        source_plan_version = _strict_non_negative_int(
            self.source_plan_version, "hint source_plan_version"
        )
        projected = _strict_bool(self.projected, "hint projected")
        constraints = tuple(self.constraints)
        transfers = tuple(self.transfer_allowances)
        if not constraints:
            raise RegionalPlanningHintError(
                "regional_hint_constraints_empty",
                "regional planning hints require at least one region constraint",
            )
        if any(not isinstance(item, RegionalPlanningConstraint) for item in constraints):
            raise RegionalPlanningHintError(
                "regional_hint_constraint_type_invalid"
            )
        if any(not isinstance(item, RegionalTransferAllowance) for item in transfers):
            raise RegionalPlanningHintError(
                "regional_hint_transfer_type_invalid"
            )
        region_ids = tuple(item.region_id for item in constraints)
        if len(set(region_ids)) != len(region_ids):
            raise RegionalPlanningHintError(
                "regional_hint_duplicate_region_constraint"
            )
        routes = tuple(
            (item.source_region_id, item.target_region_id) for item in transfers
        )
        if len(set(routes)) != len(routes):
            raise RegionalPlanningHintError(
                "regional_hint_duplicate_transfer_route"
            )
        for constraint in constraints:
            if (
                constraint.source_plan_id != source_plan_id
                or constraint.source_plan_version != source_plan_version
            ):
                raise RegionalPlanningHintError(
                    "regional_hint_constraint_source_plan_mismatch"
                )
        object.__setattr__(self, "advisory_id", advisory_id)
        object.__setattr__(self, "advisory_version", advisory_version)
        object.__setattr__(self, "created_at_s", created_at_s)
        object.__setattr__(self, "expires_at_s", expires_at_s)
        object.__setattr__(self, "source_plan_id", source_plan_id)
        object.__setattr__(self, "source_plan_version", source_plan_version)
        object.__setattr__(self, "projected", projected)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "transfer_allowances", transfers)

    @property
    def constraint_by_region(self) -> dict[str, RegionalPlanningConstraint]:
        return {item.region_id: item for item in self.constraints}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RegionalPlanningHint":
        """Parse a neutral mapping without importing any D4 implementation type."""

        _reject_forbidden_identity_fields(value)
        payload = _strict_mapping(
            value,
            allowed_fields=_HINT_FIELDS,
            context="regional planning hint",
            reject_identity=False,
        )
        constraints = payload.get("constraints")
        transfers = payload.get("transfer_allowances")
        if not isinstance(constraints, (tuple, list)):
            raise RegionalPlanningHintError(
                "regional_hint_constraints_not_sequence"
            )
        if not isinstance(transfers, (tuple, list)):
            raise RegionalPlanningHintError(
                "regional_hint_transfers_not_sequence"
            )
        payload["constraints"] = tuple(
            RegionalPlanningConstraint.from_mapping(item) for item in constraints
        )
        payload["transfer_allowances"] = tuple(
            RegionalTransferAllowance.from_mapping(item) for item in transfers
        )
        return cls(**payload)


def _strict_mapping(
    value: Mapping[str, Any],
    *,
    allowed_fields: frozenset[str],
    context: str,
    reject_identity: bool = True,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionalPlanningHintError(
            "regional_hint_mapping_required",
            f"{context} must be a mapping",
        )
    if reject_identity:
        _reject_forbidden_identity_fields(value)
    keys = {str(key) for key in value}
    unknown = tuple(sorted(keys - allowed_fields))
    missing = tuple(sorted(allowed_fields - keys))
    if unknown:
        raise RegionalPlanningHintError(
            "regional_hint_mapping_unknown_field",
            f"{context} contains unknown fields: {', '.join(unknown)}",
        )
    if missing:
        raise RegionalPlanningHintError(
            "regional_hint_mapping_missing_field",
            f"{context} is missing fields: {', '.join(missing)}",
        )
    return {str(key): item for key, item in value.items()}


def _reject_forbidden_identity_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            key_parts = tuple(part for part in key.split("_") if part)
            if (
                key in _FORBIDDEN_IDENTITY_KEYS
                or "truth" in key_parts
                or "actor" in key_parts
                or "object" in key_parts
            ):
                raise RegionalPlanningHintError(
                    "regional_hint_forbidden_identity_field",
                    f"regional planning hint contains forbidden identity field: {key}",
                )
            _reject_forbidden_identity_fields(item)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _reject_forbidden_identity_fields(item)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegionalPlanningHintError(
            "regional_hint_text_field_invalid", f"{name} must be non-empty text"
        )
    return value.strip()


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise RegionalPlanningHintError(
            "regional_hint_boolean_field_invalid", f"{name} must be boolean"
        )
    return value


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegionalPlanningHintError(
            "regional_hint_integer_field_invalid", f"{name} must be an integer"
        )
    return int(value)


def _strict_non_negative_int(value: Any, name: str) -> int:
    output = _strict_int(value, name)
    if output < 0:
        raise RegionalPlanningHintError(
            "regional_hint_integer_field_invalid", f"{name} must be non-negative"
        )
    return output


def _strict_positive_int(value: Any, name: str) -> int:
    output = _strict_int(value, name)
    if output <= 0:
        raise RegionalPlanningHintError(
            "regional_hint_integer_field_invalid", f"{name} must be positive"
        )
    return output


def _finite_non_negative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RegionalPlanningHintError(
            "regional_hint_numeric_field_invalid", f"{name} must be numeric"
        )
    output = float(value)
    if not isfinite(output) or output < 0.0:
        raise RegionalPlanningHintError(
            "regional_hint_numeric_field_invalid",
            f"{name} must be finite and non-negative",
        )
    return output


def _unit_interval(value: Any, name: str) -> float:
    output = _finite_non_negative(value, name)
    if output > 1.0:
        raise RegionalPlanningHintError(
            "regional_hint_numeric_field_invalid", f"{name} must be in [0, 1]"
        )
    return output
