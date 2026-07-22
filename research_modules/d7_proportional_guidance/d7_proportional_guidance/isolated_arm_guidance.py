"""Versioned D7 command lineage for isolated paired 3D rollouts.

The deterministic guidance laws remain in :mod:`scalable_3d_guidance`.  This
module is a safety and evidence boundary around those laws: it binds every
generated command to one experiment arm and one immutable source plan, keeps
controller state isolated by arm, and creates an explicit simulation-only
confirmation after main writes a command into a cloned point-mass world.

An application confirmation is not a production runtime ACK.  D7 never mutates
the world in this module and cannot independently prove that main performed the
write; main remains responsible for issuing the confirmation only after the
corresponding isolated world step consumed the proposed acceleration.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Any

import numpy as np

from .scalable_3d_guidance import (
    AssignmentPairGuidanceInput3D,
    GuidanceCommand3D,
    GuidanceMode3D,
    PairGuidanceStateSnapshot3D,
    ScalableGuidanceConfig3D,
    ScalableGuidanceController3D,
)
from .terminal_gate import (
    ALLOWED_D4_ACTIONS,
    AssignmentGuidanceBinding,
    coerce_assignment_guidance_binding,
    coerce_d4_guidance_permission,
)


D7_ISOLATED_GUIDANCE_CONTEXT_SCHEMA_V1 = "d7.isolated-guidance-context.v1"
D7_ISOLATED_GUIDANCE_COMMAND_SCHEMA_V1 = "d7.isolated-guidance-command.v1"
D7_ISOLATED_GUIDANCE_VALIDATION_SCHEMA_V1 = (
    "d7.isolated-guidance-command-validation.v1"
)
D7_ISOLATED_GUIDANCE_APPLICATION_SCHEMA_V1 = (
    "d7.isolated-guidance-world-application.v1"
)
D7_ISOLATED_GUIDANCE_SUMMARY_SCHEMA_V1 = "d7.isolated-guidance-summary.v1"
D7_ISOLATED_GUIDANCE_BATCH_SCHEMA_V1 = "d7.isolated-guidance-batch.v1"
D7_ISOLATED_COMMAND_LINEAGE_SCHEMA_V1 = "d7.isolated-command-lineage.v1"

ISOLATED_SIMULATION_ONLY = True
PRODUCTION_RUNTIME_ACK = False

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EPS = 1.0e-9
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)


class IsolatedGuidanceArmKind(str, Enum):
    """Allowed paired-rollout arm kinds."""

    CONTROL = "control"
    TREATMENT = "treatment"


class IsolatedGuidanceCommandState(str, Enum):
    """Evidence state of one isolated command."""

    COMMAND_GENERATED = "command_generated"
    HELD = "held"
    CONTROL_APPLIED_TO_WORLD = "control_applied_to_world"
    INVALID = "invalid"


class IsolatedGuidanceContractError(ValueError):
    """Stable fail-closed error raised before a world command is exposed."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(message or self.code)


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceExecutionContextV1:
    """Immutable experiment, arm, episode and source-plan lineage."""

    experiment_id: str
    seed: int
    arm_id: str
    arm_kind: str
    episode_id: str
    isolation_id: str
    source_plan_id: str
    source_plan_version: int
    source_plan_payload_sha256: str
    generated_at_s: float
    isolated_simulation_only: bool = ISOLATED_SIMULATION_ONLY
    production_runtime_ack: bool = PRODUCTION_RUNTIME_ACK
    schema_version: str = D7_ISOLATED_GUIDANCE_CONTEXT_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != D7_ISOLATED_GUIDANCE_CONTEXT_SCHEMA_V1:
            _fail("context_schema_unsupported")
        for name in (
            "experiment_id",
            "arm_id",
            "episode_id",
            "isolation_id",
            "source_plan_id",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if isinstance(self.seed, bool) or int(self.seed) < 0:
            _fail("seed_invalid")
        object.__setattr__(self, "seed", int(self.seed))
        arm_kind = (
            self.arm_kind.value
            if isinstance(self.arm_kind, IsolatedGuidanceArmKind)
            else str(self.arm_kind).strip()
        )
        if arm_kind not in {item.value for item in IsolatedGuidanceArmKind}:
            _fail("arm_kind_invalid")
        object.__setattr__(self, "arm_kind", arm_kind)
        if isinstance(self.source_plan_version, bool) or int(self.source_plan_version) < 0:
            _fail("source_plan_version_invalid")
        object.__setattr__(self, "source_plan_version", int(self.source_plan_version))
        object.__setattr__(
            self,
            "source_plan_payload_sha256",
            _required_sha256(
                self.source_plan_payload_sha256,
                "source_plan_payload_sha256",
            ),
        )
        object.__setattr__(
            self,
            "generated_at_s",
            _finite_nonnegative(self.generated_at_s, "generated_at_s"),
        )
        if self.isolated_simulation_only is not True:
            _fail("isolated_simulation_scope_required")
        if self.production_runtime_ack is not False:
            _fail("production_runtime_ack_forbidden")

    @property
    def arm_identity(self) -> tuple[str, int, str, str, str, str]:
        return (
            self.experiment_id,
            int(self.seed),
            self.arm_id,
            self.arm_kind,
            self.episode_id,
            self.isolation_id,
        )

    @property
    def fingerprint(self) -> str:
        return canonical_guidance_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_plan_payload(
        cls,
        *,
        experiment_id: str,
        seed: int,
        arm_id: str,
        arm_kind: str,
        episode_id: str,
        isolation_id: str,
        source_plan_id: str,
        source_plan_version: int,
        source_plan_payload: Mapping[str, Any] | Any,
        generated_at_s: float,
    ) -> "IsolatedGuidanceExecutionContextV1":
        payload = _jsonable(source_plan_payload)
        _assert_truth_free(payload)
        return cls(
            experiment_id=experiment_id,
            seed=seed,
            arm_id=arm_id,
            arm_kind=arm_kind,
            episode_id=episode_id,
            isolation_id=isolation_id,
            source_plan_id=source_plan_id,
            source_plan_version=source_plan_version,
            source_plan_payload_sha256=canonical_guidance_sha256(payload),
            generated_at_s=generated_at_s,
        )


@dataclass(frozen=True, slots=True)
class IsolatedAssignmentBindingLineageV1:
    """Canonical resource-to-center-track binding copied from D3."""

    resource_index: int
    resource_id: str
    assigned_global_track_id: str
    assignment_id: str | None
    plan_id: str
    plan_version: int
    track_version: int
    owner_node_id: str | None
    coalition_id: str | None
    coalition_version: int | None
    member_role: str
    binding_payload_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.resource_index, bool) or int(self.resource_index) < 0:
            _fail("resource_index_invalid")
        for name in ("resource_id", "assigned_global_track_id", "plan_id", "member_role"):
            _required_text(getattr(self, name), name)
        for name in ("plan_version", "track_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) < 0:
                _fail(f"{name}_invalid")
        _required_sha256(self.binding_payload_sha256, "binding_payload_sha256")

    @property
    def canonical_payload(self) -> dict[str, Any]:
        return {
            "resource_index": int(self.resource_index),
            "resource_id": self.resource_id,
            "assigned_global_track_id": self.assigned_global_track_id,
            "assignment_id": self.assignment_id,
            "plan_id": self.plan_id,
            "plan_version": int(self.plan_version),
            "track_version": int(self.track_version),
            "owner_node_id": self.owner_node_id,
            "coalition_id": self.coalition_id,
            "coalition_version": self.coalition_version,
            "member_role": self.member_role,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload, "binding_payload_sha256": self.binding_payload_sha256}


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceCommandV1:
    """One generated command plus immutable arm and assignment lineage."""

    context: IsolatedGuidanceExecutionContextV1
    assignment_binding: IsolatedAssignmentBindingLineageV1
    command: GuidanceCommand3D
    generated_at_s: float
    control_mode: str
    command_generated: bool
    held: bool
    control_applied_to_world: bool
    binding_gate_passed: bool
    d4_gate_passed: bool
    d5_gate_required: bool
    d5_gate_passed: bool | None
    hold_reason: str
    command_payload_sha256: str
    record_sha256: str
    isolated_simulation_only: bool = ISOLATED_SIMULATION_ONLY
    production_runtime_ack: bool = PRODUCTION_RUNTIME_ACK
    schema_version: str = D7_ISOLATED_GUIDANCE_COMMAND_SCHEMA_V1

    @property
    def experiment_id(self) -> str:
        return self.context.experiment_id

    @property
    def seed(self) -> int:
        return self.context.seed

    @property
    def arm_id(self) -> str:
        return self.context.arm_id

    @property
    def arm_kind(self) -> str:
        return self.context.arm_kind

    @property
    def episode_id(self) -> str:
        return self.context.episode_id

    @property
    def source_plan_id(self) -> str:
        return self.context.source_plan_id

    @property
    def source_plan_version(self) -> int:
        return self.context.source_plan_version

    @property
    def source_plan_payload_sha256(self) -> str:
        return self.context.source_plan_payload_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            **_command_record_payload(self),
            "record_sha256": self.record_sha256,
        }


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceWorldApplicationV1:
    """Main-issued confirmation that one isolated world consumed a command."""

    command_record_sha256: str
    experiment_id: str
    seed: int
    arm_id: str
    arm_kind: str
    episode_id: str
    isolation_id: str
    source_plan_id: str
    source_plan_version: int
    source_plan_payload_sha256: str
    resource_id: str
    assigned_global_track_id: str
    control_mode: str
    world_id: str
    applied_at_s: float
    applied_acceleration_ned_mps2: tuple[float, float, float]
    command_generated: bool = True
    held: bool = False
    control_applied_to_world: bool = True
    isolated_simulation_only: bool = ISOLATED_SIMULATION_ONLY
    production_runtime_ack: bool = PRODUCTION_RUNTIME_ACK
    receipt_sha256: str = ""
    schema_version: str = D7_ISOLATED_GUIDANCE_APPLICATION_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return {**_application_payload(self), "receipt_sha256": self.receipt_sha256}


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceCommandValidationV1:
    """Versioned fail-closed verdict for one command and optional write receipt."""

    valid: bool
    code: str
    reason: str
    state: str
    command_generated: bool
    held: bool
    control_applied_to_world: bool
    isolated_simulation_only: bool
    production_runtime_ack: bool
    record_sha256: str | None
    application_receipt_sha256: str | None = None
    schema_version: str = D7_ISOLATED_GUIDANCE_VALIDATION_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceBatchV1:
    """Zero-filled resource matrix and auditable records for one isolated arm."""

    context: IsolatedGuidanceExecutionContextV1
    acceleration_ned_mps2: np.ndarray
    command_records: tuple[IsolatedGuidanceCommandV1, ...]
    isolated_simulation_only: bool = ISOLATED_SIMULATION_ONLY
    production_runtime_ack: bool = PRODUCTION_RUNTIME_ACK
    schema_version: str = D7_ISOLATED_GUIDANCE_BATCH_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != D7_ISOLATED_GUIDANCE_BATCH_SCHEMA_V1:
            _fail("batch_schema_unsupported")
        acceleration = np.asarray(self.acceleration_ned_mps2, dtype=float)
        if acceleration.ndim != 2 or acceleration.shape[1] != 3:
            _fail("batch_acceleration_shape_invalid")
        if not np.all(np.isfinite(acceleration)):
            _fail("batch_acceleration_nonfinite")
        if self.isolated_simulation_only is not True or self.production_runtime_ack is not False:
            _fail("batch_scope_invalid")
        for record in self.command_records:
            if record.context.fingerprint != self.context.fingerprint:
                _fail("batch_context_mismatch")
            index = record.assignment_binding.resource_index
            expected = np.asarray(record.command.acceleration_ned_mps2, dtype=float)
            if not np.allclose(acceleration[index], expected, rtol=0.0, atol=1.0e-12):
                _fail("batch_command_matrix_mismatch")
        acceleration = acceleration.copy()
        acceleration.setflags(write=False)
        object.__setattr__(self, "acceleration_ned_mps2", acceleration)

    def to_world_acceleration(self) -> np.ndarray:
        """Return the proposal; this method does not assert world application."""

        return self.acceleration_ned_mps2.copy()


@dataclass(frozen=True, slots=True)
class IsolatedGuidanceSummaryV1:
    """Per-arm command-generation, hold and isolated-write counts."""

    experiment_id: str
    seed: int
    arm_id: str
    arm_kind: str
    episode_id: str
    command_count: int
    command_generated_count: int
    held_count: int
    control_applied_to_world_count: int
    generated_not_applied_count: int
    invalid_count: int
    mode_counts: Mapping[str, int]
    hold_reason_counts: Mapping[str, int]
    validation_code_counts: Mapping[str, int]
    isolated_simulation_only: bool = ISOLATED_SIMULATION_ONLY
    production_runtime_ack: bool = PRODUCTION_RUNTIME_ACK
    schema_version: str = D7_ISOLATED_GUIDANCE_SUMMARY_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IsolatedArmGuidanceExecutor3D:
    """Arm-bound wrapper around an independent scalable 3D controller."""

    def __init__(
        self,
        initial_context: IsolatedGuidanceExecutionContextV1,
        config: ScalableGuidanceConfig3D | None = None,
    ) -> None:
        self._arm_identity = initial_context.arm_identity
        self._controller = ScalableGuidanceController3D(config)
        self._highest_plan_version = -1
        self._plan_hash_by_version: dict[int, str] = {}

    @property
    def config(self) -> ScalableGuidanceConfig3D:
        return self._controller.config

    @property
    def arm_identity(self) -> tuple[str, int, str, str, str, str]:
        return self._arm_identity

    def reset(self) -> None:
        self._controller.reset()
        self._highest_plan_version = -1
        self._plan_hash_by_version.clear()

    def pair_state(
        self,
        resource_id: str,
        assigned_global_track_id: str,
    ) -> PairGuidanceStateSnapshot3D | None:
        return self._controller.pair_state(resource_id, assigned_global_track_id)

    def command_batch(
        self,
        pair_inputs: Iterable[AssignmentPairGuidanceInput3D],
        *,
        resource_count: int,
        context: IsolatedGuidanceExecutionContextV1,
        source_plan_payload: Mapping[str, Any] | Any,
        d5_gate_required_bindings: Iterable[tuple[str, str]] = (),
    ) -> IsolatedGuidanceBatchV1:
        """Generate a strict arm-local batch or raise before exposing commands."""

        inputs = tuple(pair_inputs)
        self._validate_context(context, source_plan_payload, inputs)
        required_d5 = {
            (str(resource_id), str(global_track_id))
            for resource_id, global_track_id in d5_gate_required_bindings
        }
        sorted_inputs = tuple(
            sorted(
                inputs,
                key=lambda item: (
                    int(item.resource_index),
                    str(_value(item.binding, "resource_id", "")),
                ),
            )
        )
        available_pair_keys: set[tuple[str, str]] = set()
        for item in sorted_inputs:
            binding = _strict_binding(item.binding)
            available_pair_keys.add(
                (binding.resource_id, binding.assigned_global_track_id)
            )
        if required_d5 - available_pair_keys:
            _fail("d5_gate_binding_not_present")
        base_batch = self._controller.command_batch(
            sorted_inputs,
            resource_count=resource_count,
        )
        matrix = base_batch.to_world_acceleration()
        records: list[IsolatedGuidanceCommandV1] = []
        for pair_input, base_command in zip(
            sorted_inputs,
            base_batch.pair_commands,
            strict=True,
        ):
            binding = _strict_binding(pair_input.binding)
            lineage = _binding_lineage(pair_input.resource_index, binding)
            binding_ok, binding_reason = _binding_gate(pair_input, binding, context)
            d4_ok, d4_reason = _d4_gate(pair_input, binding)
            pair_key = (binding.resource_id, binding.assigned_global_track_id)
            d5_required = pair_key in required_d5
            d5_passed = None
            d5_reason = ""
            if d5_required:
                d5_passed = bool(
                    base_command.terminal_contract_allowed
                    and base_command.mode
                    in {
                        GuidanceMode3D.TERMINAL_VISUAL_PNG,
                        GuidanceMode3D.TERMINAL_VISUAL_COAST,
                    }
                )
                if not d5_passed:
                    d5_reason = base_command.gate_reason or "d5_terminal_gate_not_satisfied"

            reason = binding_reason or d4_reason or d5_reason
            command = base_command
            if reason:
                command = _masked_hold_command(base_command, reason)
                matrix[int(pair_input.resource_index)] = 0.0
            record = _build_command_record(
                context=context,
                assignment_binding=lineage,
                command=command,
                binding_gate_passed=binding_ok,
                d4_gate_passed=d4_ok,
                d5_gate_required=d5_required,
                d5_gate_passed=d5_passed,
                hold_reason=reason or (command.gate_reason if command.mode is GuidanceMode3D.HOLD else ""),
            )
            verdict = validate_isolated_guidance_command(
                record,
                expected_context=context,
                expected_binding=lineage,
            )
            if not verdict.valid:
                _fail(verdict.code, verdict.reason)
            records.append(record)

        version = int(context.source_plan_version)
        self._highest_plan_version = max(self._highest_plan_version, version)
        self._plan_hash_by_version[version] = context.source_plan_payload_sha256
        return IsolatedGuidanceBatchV1(
            context=context,
            acceleration_ned_mps2=matrix,
            command_records=tuple(records),
        )

    def confirm_world_application(
        self,
        record: IsolatedGuidanceCommandV1,
        *,
        context: IsolatedGuidanceExecutionContextV1,
        world_id: str,
        applied_at_s: float,
        applied_acceleration_ned_mps2: Sequence[float],
    ) -> IsolatedGuidanceWorldApplicationV1:
        """Build a simulation-only receipt after main applies the command."""

        if context.arm_identity != self._arm_identity:
            _fail("wrong_arm")
        verdict = validate_isolated_guidance_command(
            record,
            expected_context=context,
        )
        if not verdict.valid:
            _fail(verdict.code, verdict.reason)
        if record.held:
            _fail("held_command_cannot_be_applied")
        _required_text(world_id, "world_id")
        if str(world_id) != context.isolation_id:
            _fail("wrong_isolated_world")
        applied_at = _finite_nonnegative(applied_at_s, "applied_at_s")
        if applied_at + _EPS < record.generated_at_s:
            _fail("application_timestamp_precedes_generation")
        applied = np.asarray(applied_acceleration_ned_mps2, dtype=float).reshape(-1)
        if applied.shape != (3,) or not np.all(np.isfinite(applied)):
            _fail("applied_acceleration_invalid")
        expected = np.asarray(record.command.acceleration_ned_mps2, dtype=float)
        if not np.allclose(applied, expected, rtol=0.0, atol=1.0e-12):
            _fail("applied_acceleration_mismatch")
        receipt = IsolatedGuidanceWorldApplicationV1(
            command_record_sha256=record.record_sha256,
            experiment_id=context.experiment_id,
            seed=context.seed,
            arm_id=context.arm_id,
            arm_kind=context.arm_kind,
            episode_id=context.episode_id,
            isolation_id=context.isolation_id,
            source_plan_id=context.source_plan_id,
            source_plan_version=context.source_plan_version,
            source_plan_payload_sha256=context.source_plan_payload_sha256,
            resource_id=record.assignment_binding.resource_id,
            assigned_global_track_id=record.assignment_binding.assigned_global_track_id,
            control_mode=record.control_mode,
            world_id=world_id,
            applied_at_s=applied_at,
            applied_acceleration_ned_mps2=tuple(float(value) for value in applied),
        )
        receipt = replace(
            receipt,
            receipt_sha256=canonical_guidance_sha256(_application_payload(receipt)),
        )
        final_verdict = validate_isolated_guidance_command(
            record,
            expected_context=context,
            application=receipt,
        )
        if not final_verdict.valid:
            _fail(final_verdict.code, final_verdict.reason)
        return receipt

    def _validate_context(
        self,
        context: IsolatedGuidanceExecutionContextV1,
        source_plan_payload: Mapping[str, Any] | Any,
        inputs: Sequence[AssignmentPairGuidanceInput3D],
    ) -> None:
        if context.arm_identity != self._arm_identity:
            _fail("wrong_arm")
        payload = _jsonable(source_plan_payload)
        _assert_truth_free(payload)
        if canonical_guidance_sha256(payload) != context.source_plan_payload_sha256:
            _fail("source_plan_hash_mismatch")
        plan_id = str(_value(source_plan_payload, "plan_id", "")).strip()
        plan_version = _value(
            source_plan_payload,
            "plan_version",
            _value(source_plan_payload, "version", None),
        )
        if plan_id != context.source_plan_id:
            _fail("source_plan_id_mismatch")
        if plan_version is None or int(plan_version) != context.source_plan_version:
            _fail("source_plan_version_mismatch")
        source_bindings = _source_plan_bindings(payload)
        for pair_input in inputs:
            binding = _strict_binding(pair_input.binding)
            if (binding.resource_id, binding.assigned_global_track_id) not in source_bindings:
                _fail("assignment_binding_not_in_source_plan")
        if context.source_plan_version < self._highest_plan_version:
            _fail("stale_plan_version")
        known_hash = self._plan_hash_by_version.get(context.source_plan_version)
        if known_hash is not None and known_hash != context.source_plan_payload_sha256:
            _fail("source_plan_hash_conflict")
        for pair_input in inputs:
            if abs(float(pair_input.timestamp_s) - context.generated_at_s) > _EPS:
                _fail("command_generation_timestamp_mismatch")
            _assert_truth_free(_value(pair_input.binding, "metadata", {}) or {})
            _assert_truth_free(_value(pair_input.global_track, "metadata", {}) or {})
            _assert_truth_free(_value(pair_input.terminal_association, "metadata", {}) or {})


def validate_isolated_guidance_command(
    record: IsolatedGuidanceCommandV1,
    *,
    expected_context: IsolatedGuidanceExecutionContextV1 | None = None,
    expected_binding: IsolatedAssignmentBindingLineageV1 | None = None,
    application: IsolatedGuidanceWorldApplicationV1 | None = None,
) -> IsolatedGuidanceCommandValidationV1:
    """Validate command lineage and optional isolated-world confirmation."""

    try:
        _validate_command_record(record, expected_context, expected_binding)
        applied = False
        receipt_hash = None
        if application is not None:
            _validate_application(record, application)
            applied = True
            receipt_hash = application.receipt_sha256
        state = (
            IsolatedGuidanceCommandState.CONTROL_APPLIED_TO_WORLD
            if applied
            else IsolatedGuidanceCommandState.HELD
            if record.held
            else IsolatedGuidanceCommandState.COMMAND_GENERATED
        )
        return IsolatedGuidanceCommandValidationV1(
            valid=True,
            code="valid",
            reason="valid",
            state=state.value,
            command_generated=True,
            held=record.held,
            control_applied_to_world=applied,
            isolated_simulation_only=True,
            production_runtime_ack=False,
            record_sha256=record.record_sha256,
            application_receipt_sha256=receipt_hash,
        )
    except (IsolatedGuidanceContractError, TypeError, ValueError) as exc:
        code = getattr(exc, "code", "invalid_command_record")
        return IsolatedGuidanceCommandValidationV1(
            valid=False,
            code=str(code),
            reason=str(exc),
            state=IsolatedGuidanceCommandState.INVALID.value,
            command_generated=bool(getattr(record, "command_generated", False)),
            held=bool(getattr(record, "held", True)),
            control_applied_to_world=False,
            isolated_simulation_only=True,
            production_runtime_ack=False,
            record_sha256=getattr(record, "record_sha256", None),
        )


def summarize_isolated_guidance_commands(
    records: Iterable[IsolatedGuidanceCommandV1],
    *,
    applications: Iterable[IsolatedGuidanceWorldApplicationV1] = (),
    expected_context: IsolatedGuidanceExecutionContextV1 | None = None,
) -> IsolatedGuidanceSummaryV1:
    """Summarize one arm without upgrading confirmations to runtime ACKs."""

    record_items = tuple(records)
    application_by_record: dict[str, IsolatedGuidanceWorldApplicationV1] = {}
    for item in applications:
        if item.command_record_sha256 in application_by_record:
            _fail("duplicate_world_application_receipt")
        application_by_record[item.command_record_sha256] = item
    if not record_items:
        _fail("summary_requires_commands")
    context = expected_context or record_items[0].context
    verdicts = [
        validate_isolated_guidance_command(
            record,
            expected_context=context,
            application=application_by_record.get(record.record_sha256),
        )
        for record in record_items
    ]
    known_hashes = {record.record_sha256 for record in record_items}
    if set(application_by_record) - known_hashes:
        _fail("application_receipt_without_command")
    generated = sum(verdict.valid and verdict.command_generated for verdict in verdicts)
    held = sum(verdict.valid and verdict.held for verdict in verdicts)
    applied = sum(verdict.valid and verdict.control_applied_to_world for verdict in verdicts)
    invalid = sum(not verdict.valid for verdict in verdicts)
    mode_counts = Counter(record.control_mode for record in record_items)
    hold_reasons = Counter(record.hold_reason for record in record_items if record.held)
    validation_codes = Counter(verdict.code for verdict in verdicts)
    return IsolatedGuidanceSummaryV1(
        experiment_id=context.experiment_id,
        seed=context.seed,
        arm_id=context.arm_id,
        arm_kind=context.arm_kind,
        episode_id=context.episode_id,
        command_count=len(record_items),
        command_generated_count=generated,
        held_count=held,
        control_applied_to_world_count=applied,
        generated_not_applied_count=max(0, generated - held - applied),
        invalid_count=invalid,
        mode_counts=dict(sorted(mode_counts.items())),
        hold_reason_counts=dict(sorted(hold_reasons.items())),
        validation_code_counts=dict(sorted(validation_codes.items())),
    )


def build_isolated_guidance_lineage_record_v1(
    record: IsolatedGuidanceCommandV1,
    *,
    command_id: str,
    cycle_index: int,
    consumption_id: str,
    application: IsolatedGuidanceWorldApplicationV1 | None = None,
    world_application_id: str | None = None,
) -> dict[str, Any]:
    """Flatten one D7 record for the main/D6 isolated-rollout JSONL contract.

    The full D7 arm, episode, plan, binding and gate lineage remains nested in
    ``command_payload``.  The outer shape intentionally matches D6's strict
    ``d7.isolated-command-lineage.v1`` consumer.  Main still owns the separate
    world-application record because D7 cannot observe the world mutation or
    its hard-constraint count.
    """

    _required_text(command_id, "command_id")
    _required_text(consumption_id, "consumption_id")
    if isinstance(cycle_index, bool) or int(cycle_index) < 0:
        _fail("cycle_index_invalid")
    verdict = validate_isolated_guidance_command(
        record,
        expected_context=record.context,
        application=application,
    )
    if not verdict.valid:
        _fail(verdict.code, verdict.reason)
    applied = application is not None
    if applied:
        _required_text(world_application_id, "world_application_id")
    elif world_application_id is not None:
        _fail("world_application_id_without_application")
    command_payload = record.to_dict()
    if application is not None:
        command_payload = {
            **command_payload,
            "isolated_world_application_receipt_sha256": application.receipt_sha256,
        }
    return {
        "schema_version": D7_ISOLATED_COMMAND_LINEAGE_SCHEMA_V1,
        "command_id": str(command_id),
        "cycle_index": int(cycle_index),
        "issued_at_s": float(record.generated_at_s),
        "consumption_id": str(consumption_id),
        "plan_id": record.source_plan_id,
        "plan_version": int(record.source_plan_version),
        "plan_payload_sha256": record.source_plan_payload_sha256,
        "resource_id": record.assignment_binding.resource_id,
        "global_track_id": record.assignment_binding.assigned_global_track_id,
        "command_payload_sha256": canonical_guidance_sha256(command_payload),
        "command_payload": command_payload,
        "control_applied_to_world": applied,
        "world_application_id": (
            str(world_application_id) if world_application_id is not None else None
        ),
    }


def canonical_guidance_sha256(value: Any) -> str:
    """Return a stable SHA-256 for JSON-compatible command evidence."""

    encoded = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _build_command_record(
    *,
    context: IsolatedGuidanceExecutionContextV1,
    assignment_binding: IsolatedAssignmentBindingLineageV1,
    command: GuidanceCommand3D,
    binding_gate_passed: bool,
    d4_gate_passed: bool,
    d5_gate_required: bool,
    d5_gate_passed: bool | None,
    hold_reason: str,
) -> IsolatedGuidanceCommandV1:
    record = IsolatedGuidanceCommandV1(
        context=context,
        assignment_binding=assignment_binding,
        command=command,
        generated_at_s=float(command.timestamp_s),
        control_mode=command.mode.value,
        command_generated=True,
        held=command.mode is GuidanceMode3D.HOLD,
        control_applied_to_world=False,
        binding_gate_passed=bool(binding_gate_passed),
        d4_gate_passed=bool(d4_gate_passed),
        d5_gate_required=bool(d5_gate_required),
        d5_gate_passed=d5_gate_passed,
        hold_reason=str(hold_reason),
        command_payload_sha256=canonical_guidance_sha256(_command_payload(command)),
        record_sha256="0" * 64,
    )
    return replace(
        record,
        record_sha256=canonical_guidance_sha256(_command_record_payload(record)),
    )


def _validate_command_record(
    record: IsolatedGuidanceCommandV1,
    expected_context: IsolatedGuidanceExecutionContextV1 | None,
    expected_binding: IsolatedAssignmentBindingLineageV1 | None,
) -> None:
    if record.schema_version != D7_ISOLATED_GUIDANCE_COMMAND_SCHEMA_V1:
        _fail("command_schema_unsupported")
    if record.isolated_simulation_only is not True:
        _fail("isolated_simulation_scope_required")
    if record.production_runtime_ack is not False:
        _fail("production_runtime_ack_forbidden")
    if record.command_generated is not True:
        _fail("command_not_generated")
    if record.control_applied_to_world is not False:
        _fail("generated_command_cannot_claim_world_application")
    if expected_context is not None and record.context.fingerprint != expected_context.fingerprint:
        if record.context.arm_identity != expected_context.arm_identity:
            _fail("wrong_arm")
        _fail("command_context_mismatch")
    if expected_binding is not None and record.assignment_binding != expected_binding:
        _fail("assignment_binding_mismatch")
    binding = record.assignment_binding
    if canonical_guidance_sha256(binding.canonical_payload) != binding.binding_payload_sha256:
        _fail("assignment_binding_hash_mismatch")
    command = record.command
    if canonical_guidance_sha256(_command_payload(command)) != record.command_payload_sha256:
        _fail("command_payload_hash_mismatch")
    if canonical_guidance_sha256(_command_record_payload(record)) != record.record_sha256:
        _fail("command_record_hash_mismatch")
    if record.context.source_plan_id != command.plan_id:
        _fail("source_plan_id_mismatch")
    if record.context.source_plan_version != command.plan_version:
        _fail("source_plan_version_mismatch")
    if binding.plan_id != command.plan_id or binding.plan_version != command.plan_version:
        _fail("assignment_plan_mismatch")
    if binding.resource_id != command.resource_id:
        _fail("resource_binding_mismatch")
    if binding.assigned_global_track_id != command.assigned_global_track_id:
        _fail("resource_track_binding_mismatch")
    if record.generated_at_s != command.timestamp_s:
        _fail("command_generation_timestamp_mismatch")
    if record.control_mode != command.mode.value:
        _fail("control_mode_mismatch")
    if record.held != (command.mode is GuidanceMode3D.HOLD):
        _fail("held_state_mismatch")
    mandatory_gate_failed = (
        not record.binding_gate_passed
        or not record.d4_gate_passed
        or (record.d5_gate_required and record.d5_gate_passed is not True)
    )
    if mandatory_gate_failed and not record.held:
        _fail("failed_gate_exposed_executable_command")
    if record.d5_gate_required is False and record.d5_gate_passed is not None:
        _fail("d5_gate_state_contradiction")
    acceleration = np.asarray(command.acceleration_ned_mps2, dtype=float)
    if record.held and not np.allclose(acceleration, 0.0, rtol=0.0, atol=1.0e-12):
        _fail("held_command_nonzero")
    if record.held and not record.hold_reason:
        _fail("held_command_reason_missing")
    _assert_truth_free(record.to_dict())


def _validate_application(
    record: IsolatedGuidanceCommandV1,
    application: IsolatedGuidanceWorldApplicationV1,
) -> None:
    if application.schema_version != D7_ISOLATED_GUIDANCE_APPLICATION_SCHEMA_V1:
        _fail("application_schema_unsupported")
    if application.command_record_sha256 != record.record_sha256:
        _fail("application_command_hash_mismatch")
    if record.held or application.held:
        _fail("held_command_cannot_be_applied")
    if application.command_generated is not True or application.control_applied_to_world is not True:
        _fail("application_state_invalid")
    if application.isolated_simulation_only is not True:
        _fail("isolated_simulation_scope_required")
    if application.production_runtime_ack is not False:
        _fail("production_runtime_ack_forbidden")
    context = record.context
    expected_identity = (
        context.experiment_id,
        context.seed,
        context.arm_id,
        context.arm_kind,
        context.episode_id,
        context.isolation_id,
        context.source_plan_id,
        context.source_plan_version,
        context.source_plan_payload_sha256,
    )
    observed_identity = (
        application.experiment_id,
        application.seed,
        application.arm_id,
        application.arm_kind,
        application.episode_id,
        application.isolation_id,
        application.source_plan_id,
        application.source_plan_version,
        application.source_plan_payload_sha256,
    )
    if observed_identity != expected_identity:
        _fail("application_lineage_mismatch")
    if application.resource_id != record.assignment_binding.resource_id:
        _fail("application_resource_mismatch")
    if application.assigned_global_track_id != record.assignment_binding.assigned_global_track_id:
        _fail("application_global_track_mismatch")
    if application.control_mode != record.control_mode:
        _fail("application_control_mode_mismatch")
    if application.world_id != context.isolation_id:
        _fail("wrong_isolated_world")
    expected_acceleration = np.asarray(record.command.acceleration_ned_mps2, dtype=float)
    applied_acceleration = np.asarray(application.applied_acceleration_ned_mps2, dtype=float)
    if not np.allclose(applied_acceleration, expected_acceleration, rtol=0.0, atol=1.0e-12):
        _fail("applied_acceleration_mismatch")
    if application.applied_at_s + _EPS < record.generated_at_s:
        _fail("application_timestamp_precedes_generation")
    _required_text(application.world_id, "world_id")
    if canonical_guidance_sha256(_application_payload(application)) != application.receipt_sha256:
        _fail("application_receipt_hash_mismatch")


def _binding_lineage(
    resource_index: int,
    binding: AssignmentGuidanceBinding,
) -> IsolatedAssignmentBindingLineageV1:
    if binding.target_actor_name or binding.target_object_id or binding.target_mesh_aliases:
        _fail("online_truth_identity_field_present")
    _assert_truth_free(binding.metadata)
    payload = {
        "resource_index": int(resource_index),
        "resource_id": binding.resource_id,
        "assigned_global_track_id": binding.assigned_global_track_id,
        "assignment_id": binding.assignment_id,
        "plan_id": binding.plan_id,
        "plan_version": int(binding.plan_version),
        "track_version": int(binding.track_version),
        "owner_node_id": binding.owner_node_id,
        "coalition_id": binding.coalition_id,
        "coalition_version": binding.coalition_version,
        "member_role": binding.member_role,
    }
    return IsolatedAssignmentBindingLineageV1(
        **payload,
        binding_payload_sha256=canonical_guidance_sha256(payload),
    )


def _source_plan_bindings(payload: Mapping[str, Any]) -> set[tuple[str, str]]:
    raw_assignments = payload.get("assignments")
    if not isinstance(raw_assignments, list):
        _fail("source_plan_assignments_missing")
    bindings: set[tuple[str, str]] = set()
    for item in raw_assignments:
        if not isinstance(item, Mapping):
            _fail("source_plan_assignment_invalid")
        resource_id = str(item.get("resource_id", "")).strip()
        global_track_id = str(
            item.get(
                "global_track_id",
                item.get(
                    "assigned_global_track_id",
                    item.get("target_id", ""),
                ),
            )
        ).strip()
        if not resource_id or not global_track_id:
            _fail("source_plan_assignment_binding_missing")
        key = (resource_id, global_track_id)
        if key in bindings:
            _fail("source_plan_assignment_binding_duplicate")
        bindings.add(key)
    return bindings


def _strict_binding(value: Any) -> AssignmentGuidanceBinding:
    try:
        return coerce_assignment_guidance_binding(value)
    except (TypeError, ValueError) as exc:
        _fail("assignment_binding_invalid", str(exc))


def _binding_gate(
    pair_input: AssignmentPairGuidanceInput3D,
    binding: AssignmentGuidanceBinding,
    context: IsolatedGuidanceExecutionContextV1,
) -> tuple[bool, str]:
    track_id = str(_value(pair_input.global_track, "global_track_id", "")).strip()
    if binding.assigned_global_track_id != track_id:
        return False, "global_track_id_mismatch"
    if binding.plan_id != context.source_plan_id:
        return False, "stale_plan_id"
    if binding.plan_version != context.source_plan_version:
        return False, "stale_plan_version"
    if str(pair_input.active_plan_id) != context.source_plan_id:
        return False, "active_plan_id_mismatch"
    if int(pair_input.active_plan_version) != context.source_plan_version:
        return False, "active_plan_version_mismatch"
    return True, ""


def _d4_gate(
    pair_input: AssignmentPairGuidanceInput3D,
    binding: AssignmentGuidanceBinding,
) -> tuple[bool, str]:
    if pair_input.d4_permission is None:
        return False, "d4_permission_missing"
    permission = coerce_d4_guidance_permission(pair_input.d4_permission)
    action = permission.action.lower()
    states = {action, permission.mode.lower(), permission.reason.lower()}
    if permission.requires_human_review:
        return False, "d4_hold_for_review"
    if states & {
        "hold",
        "hold_for_review",
        "revoke",
        "revoked",
        "request_center_replan",
        "degrade_to_secondary",
        "degrade_to_distributed",
        "reassign",
        "coalition_fallback_unsupported",
    }:
        return False, "d4_action_not_executable"
    if action not in ALLOWED_D4_ACTIONS:
        return False, "d4_action_not_executable"
    if permission.new_plan_id is not None and permission.new_plan_id != binding.plan_id:
        return False, "d4_plan_mismatch"
    if (
        permission.new_plan_version is not None
        and permission.new_plan_version != binding.plan_version
    ):
        return False, "d4_plan_mismatch"
    if action != "request_secondary_assist" and permission.target_node_id is not None:
        if binding.owner_node_id is None:
            return False, "d4_owner_missing"
        if permission.target_node_id != binding.owner_node_id:
            return False, "d4_owner_mismatch"
    return True, ""


def _masked_hold_command(command: GuidanceCommand3D, reason: str) -> GuidanceCommand3D:
    return replace(
        command,
        mode=GuidanceMode3D.HOLD,
        acceleration_ned_mps2=(0.0, 0.0, 0.0),
        command_norm_mps2=0.0,
        command_saturated=False,
        gate_reason=str(reason),
        terminal_contract_allowed=False,
        visual_switch_allowed=False,
        using_visual_coast=False,
        metadata={
            **dict(command.metadata),
            "isolated_safety_shell_held": True,
            "isolated_safety_shell_reason": str(reason),
        },
    )


def _command_payload(command: GuidanceCommand3D) -> dict[str, Any]:
    return _jsonable(command)


def _command_record_payload(record: IsolatedGuidanceCommandV1) -> dict[str, Any]:
    return {
        "schema_version": record.schema_version,
        "context": record.context.to_dict(),
        "assignment_binding": record.assignment_binding.to_dict(),
        "command": _command_payload(record.command),
        "generated_at_s": record.generated_at_s,
        "control_mode": record.control_mode,
        "command_generated": record.command_generated,
        "held": record.held,
        "control_applied_to_world": record.control_applied_to_world,
        "binding_gate_passed": record.binding_gate_passed,
        "d4_gate_passed": record.d4_gate_passed,
        "d5_gate_required": record.d5_gate_required,
        "d5_gate_passed": record.d5_gate_passed,
        "hold_reason": record.hold_reason,
        "command_payload_sha256": record.command_payload_sha256,
        "isolated_simulation_only": record.isolated_simulation_only,
        "production_runtime_ack": record.production_runtime_ack,
    }


def _application_payload(application: IsolatedGuidanceWorldApplicationV1) -> dict[str, Any]:
    return {
        field.name: _jsonable(getattr(application, field.name))
        for field in fields(application)
        if field.name != "receipt_sha256"
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("nonfinite_value")
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _assert_truth_free(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_ONLINE_KEYS:
                _fail("online_truth_field_forbidden", f"forbidden field at {path}.{key}")
            _assert_truth_free(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _assert_truth_free(item, f"{path}[{index}]")


def _value(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _required_text(value: Any, name: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        _fail(f"{name}_missing")
    return result


def _required_sha256(value: Any, name: str) -> str:
    result = str(value).strip().lower()
    if not _SHA256_RE.fullmatch(result):
        _fail(f"{name}_invalid")
    return result


def _finite_nonnegative(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        _fail(f"{name}_invalid")
    return result


def _fail(code: str, message: str | None = None) -> None:
    raise IsolatedGuidanceContractError(code, message)
