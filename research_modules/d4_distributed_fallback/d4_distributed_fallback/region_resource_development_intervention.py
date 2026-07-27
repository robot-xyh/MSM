"""Constrained non-zero regional intervention for development pairing.

This adapter exists only to exercise the A2 projection and evidence chain when
an otherwise valid learned development candidate emits a no-op.  It derives a
bounded intervention from the deterministic rule policy, preserves the base
candidate's authority bindings, and still requires the normal projector and
safe-adoption gates.

The adapter has no admitted model manifest and therefore cannot become assist
eligible through :class:`RegionResourceAdvisor`.  Its output is development
test evidence, not model-admission or benefit evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import re
from typing import Any

from .region_resource import (
    AdvisorMode,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from .region_resource_safe_adoption import (
    _build_projected_intervention_evidence,
)
from .regional_failover import RegionalFailoverDecision


REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME = (
    "d4-a2-constrained-development-intervention"
)
REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_VERSION = "v1"
REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON = (
    "development_test_only_intervention"
)
REGION_RESOURCE_DEVELOPMENT_REQUEST_REPLAN_REASON = (
    "development_request_replan_only"
)
REGION_RESOURCE_DEVELOPMENT_TRANSFER_REASON = (
    "development_bounded_transfer"
)
REGION_RESOURCE_DEVELOPMENT_HOLD_REASON = (
    "development_uncommitted_region_hold"
)
REGION_RESOURCE_DEVELOPMENT_INTERVENTION_SCHEMA = (
    "d4-a2-constrained-development-intervention-v1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RegionResourceDevelopmentInterventionError(ValueError):
    """Fail-closed error at the development adapter boundary."""


@dataclass(frozen=True)
class RegionResourceDevelopmentInterventionConfig:
    """Explicit opt-in boundary for the deterministic development adapter."""

    enabled: bool = False
    run_label: str = ""
    allowed_scenario_ids: tuple[str, ...] = ()
    maximum_total_transfer_resources: int = 1
    allow_hold: bool = True
    allow_request_replan: bool = True
    force_request_replan_on_projected_noop: bool = False
    projection: RegionResourceProjectionConfig = field(
        default_factory=RegionResourceProjectionConfig
    )

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")
        if not isinstance(self.allow_hold, bool):
            raise TypeError("allow_hold must be a bool")
        if not isinstance(self.allow_request_replan, bool):
            raise TypeError("allow_request_replan must be a bool")
        if not isinstance(
            self.force_request_replan_on_projected_noop,
            bool,
        ):
            raise TypeError(
                "force_request_replan_on_projected_noop must be a bool"
            )
        if (
            isinstance(self.maximum_total_transfer_resources, bool)
            or int(self.maximum_total_transfer_resources)
            != self.maximum_total_transfer_resources
            or int(self.maximum_total_transfer_resources) <= 0
        ):
            raise ValueError(
                "maximum_total_transfer_resources must be a positive integer"
            )
        scenarios = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in self.allowed_scenario_ids
                    if str(value).strip()
                }
            )
        )
        object.__setattr__(self, "allowed_scenario_ids", scenarios)
        object.__setattr__(self, "run_label", str(self.run_label).strip())
        if self.enabled and not self.run_label:
            raise ValueError(
                "enabled development intervention requires run_label"
            )
        if self.enabled and not scenarios:
            raise ValueError(
                "enabled development intervention requires a scenario allowlist"
            )

    @property
    def content_sha256(self) -> str:
        payload = {
            "schema": REGION_RESOURCE_DEVELOPMENT_INTERVENTION_SCHEMA,
            "enabled": self.enabled,
            "run_label": self.run_label,
            "allowed_scenario_ids": self.allowed_scenario_ids,
            "maximum_total_transfer_resources": (
                self.maximum_total_transfer_resources
            ),
            "allow_hold": self.allow_hold,
            "allow_request_replan": self.allow_request_replan,
            "force_request_replan_on_projected_noop": (
                self.force_request_replan_on_projected_noop
            ),
            "projection": {
                "minimum_reserve_ratio": (
                    self.projection.minimum_reserve_ratio
                ),
                "minimum_reserve_resources": (
                    self.projection.minimum_reserve_resources
                ),
                "advisory_ttl_s": self.projection.advisory_ttl_s,
            },
        }
        return sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class ConstrainedDevelopmentRegionResourceAdapter:
    """Overlay one bounded, deterministic intervention on a learned no-op.

    The wrapped policy remains responsible for producing a finite, truth-free
    learned recommendation and model identity.  The adapter does not fabricate
    a model manifest and does not alter owner, plan, epoch, or lease fields.
    """

    policy_name = REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
    policy_version = REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_VERSION
    development_only = True
    maximum_advisor_mode = AdvisorMode.SHADOW
    assist_enabled = False
    authority_enabled = False
    control_enabled = False
    model_admitted = False
    actual_system_benefit_claimed = False
    manifest = None
    formal_decision_aware = True

    def __init__(
        self,
        learned_policy: Any,
        *,
        config: RegionResourceDevelopmentInterventionConfig,
    ) -> None:
        if learned_policy is None or not hasattr(
            learned_policy, "recommend_raw"
        ):
            raise TypeError("learned_policy must provide recommend_raw")
        self.learned_policy = learned_policy
        self.config = config
        self._projector = DeterministicResourceProjector(
            config.projection
        )
        self._rule = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(projection=config.projection),
            projector=self._projector,
        )

    @property
    def adapter_config_sha256(self) -> str:
        return self.config.content_sha256

    def is_ood(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        margin: float,
    ) -> bool:
        checker = getattr(self.learned_policy, "is_ood", None)
        if checker is None:
            return False
        return bool(checker(snapshot, margin=margin))

    def recommend_raw(
        self,
        snapshot: RegionResourceSnapshot,
        *,
        formal_decision: RegionalFailoverDecision | None = None,
    ) -> RegionResourceRecommendation:
        if not self.config.enabled:
            raise RegionResourceDevelopmentInterventionError(
                "development_intervention_disabled"
            )
        if snapshot.scenario_id not in self.config.allowed_scenario_ids:
            raise RegionResourceDevelopmentInterventionError(
                "development_intervention_scenario_not_allowlisted"
            )

        base = self.learned_policy.recommend_raw(snapshot)
        self._validate_base(snapshot, base)
        if self._has_consumable_intervention(
            snapshot,
            base,
            formal_decision=formal_decision,
        ):
            return base

        rule = self._rule.recommend(
            snapshot,
            formal_decision=formal_decision,
        )
        rule_actions = {
            action.region_id: action for action in rule.actions
        }
        request_region_id = self._request_replan_region(
            snapshot,
            rule_actions,
        )
        if request_region_id is not None:
            candidate = self._with_intervention(
                base,
                request_region_id=request_region_id,
            )
            if self._has_consumable_intervention(
                snapshot,
                candidate,
                formal_decision=formal_decision,
            ):
                return candidate

        transfers = self._bounded_transfers(rule.transfers)
        if transfers:
            candidate = self._with_intervention(
                base,
                transfers=transfers,
            )
            if self._has_consumable_intervention(
                snapshot,
                candidate,
                formal_decision=formal_decision,
            ):
                return candidate

        hold_region_id = self._safe_hold_region(
            snapshot,
            rule_actions,
        )
        if hold_region_id is not None:
            candidate = self._with_intervention(
                base,
                hold_region_id=hold_region_id,
            )
            if self._has_consumable_intervention(
                snapshot,
                candidate,
                formal_decision=formal_decision,
            ):
                return candidate

        return base

    @staticmethod
    def _with_intervention(
        base: RegionResourceRecommendation,
        *,
        request_region_id: str | None = None,
        transfers: tuple[RegionTransferSuggestion, ...] = (),
        hold_region_id: str | None = None,
    ) -> RegionResourceRecommendation:
        actions: list[RegionResourceAction] = []
        for action in base.actions:
            hold = action.region_id == hold_region_id
            request_replan = action.region_id == request_region_id
            changed = bool(hold or request_replan)
            action_reason = (
                REGION_RESOURCE_DEVELOPMENT_REQUEST_REPLAN_REASON
                if request_replan
                else REGION_RESOURCE_DEVELOPMENT_HOLD_REASON
            )
            actions.append(
                replace(
                    action,
                    hold=hold,
                    request_replan=request_replan,
                    reasons=(
                        action.reasons
                        + (
                            (
                                REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON,
                                action_reason,
                            )
                            if changed
                            else ()
                        )
                    ),
                )
            )

        if transfers:
            affected = {
                item.source_region_id for item in transfers
            } | {
                item.target_region_id for item in transfers
            }
            actions = [
                replace(
                    action,
                    reasons=(
                        action.reasons
                        + (
                            REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON,
                            REGION_RESOURCE_DEVELOPMENT_TRANSFER_REASON,
                        )
                    ),
                )
                if action.region_id in affected
                else action
                for action in actions
            ]
            transfers = tuple(
                replace(
                    transfer,
                    reasons=(
                        transfer.reasons
                        + (
                            REGION_RESOURCE_DEVELOPMENT_INTERVENTION_REASON,
                            REGION_RESOURCE_DEVELOPMENT_TRANSFER_REASON,
                        )
                    ),
                )
                for transfer in transfers
            )

        return replace(
            base,
            policy_name=(
                REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_NAME
            ),
            policy_version=(
                REGION_RESOURCE_DEVELOPMENT_INTERVENTION_POLICY_VERSION
            ),
            actions=tuple(actions),
            transfers=transfers,
            projected=False,
            fallback_reason=None,
            projection_rejections=(),
        )

    def _bounded_transfers(
        self,
        transfers: tuple[RegionTransferSuggestion, ...],
    ) -> tuple[RegionTransferSuggestion, ...]:
        remaining = int(self.config.maximum_total_transfer_resources)
        bounded: list[RegionTransferSuggestion] = []
        for transfer in sorted(
            transfers,
            key=lambda item: (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            ),
        ):
            count = min(int(transfer.resource_count), remaining)
            if count <= 0:
                break
            bounded.append(replace(transfer, resource_count=count))
            remaining -= count
        return tuple(bounded)

    def _request_replan_region(
        self,
        snapshot: RegionResourceSnapshot,
        rule_actions: dict[str, RegionResourceAction],
    ) -> str | None:
        if not self.config.allow_request_replan:
            return None
        candidates = [
            node
            for node in snapshot.regions
            if rule_actions[node.region_id].request_replan
            and self._authority_locally_eligible(snapshot, node.region_id)
        ]
        if (
            not candidates
            and self.config.force_request_replan_on_projected_noop
        ):
            candidates = [
                node
                for node in snapshot.regions
                if self._authority_locally_eligible(
                    snapshot,
                    node.region_id,
                )
            ]
        if not candidates:
            return None

        high_threat_weight = float(self._rule.config.high_threat_weight)

        def priority(node: Any) -> tuple[float, int, int, str]:
            usable = max(
                0,
                node.available_resources - node.reserve_resources,
            )
            deficit = max(
                0.0,
                node.target_demand
                + high_threat_weight * node.high_threat_backlog
                - usable,
            )
            return (
                -deficit,
                -int(node.assignment_conflict_count),
                -int(bool(node.degradation_failed)),
                node.region_id,
            )

        return min(candidates, key=priority).region_id

    def _safe_hold_region(
        self,
        snapshot: RegionResourceSnapshot,
        rule_actions: dict[str, RegionResourceAction],
    ) -> str | None:
        if not self.config.allow_hold:
            return None
        candidates = [
            node
            for node in snapshot.regions
            if rule_actions[node.region_id].hold
            and int(node.committed_resources) == 0
            and self._authority_locally_eligible(snapshot, node.region_id)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda node: (
                -int(bool(node.degradation_failed)),
                -float(node.high_threat_backlog),
                node.region_id,
            ),
        ).region_id

    @staticmethod
    def _authority_locally_eligible(
        snapshot: RegionResourceSnapshot,
        region_id: str,
    ) -> bool:
        node = snapshot.region_by_id[region_id]
        return bool(
            snapshot.timestamp_s < node.lease_expires_at_s
            and node.owner_active
            and node.coalition_ack_complete
            and not node.fault_fenced
        )

    def _has_consumable_intervention(
        self,
        snapshot: RegionResourceSnapshot,
        recommendation: RegionResourceRecommendation,
        *,
        formal_decision: RegionalFailoverDecision | None,
    ) -> bool:
        projected = self._projector.project(
            snapshot,
            recommendation,
            formal_decision=formal_decision,
        )
        if projected.projection_rejections:
            return False
        advisory = self._projector.build_advisory_contract(
            snapshot,
            projected,
            formal_decision=formal_decision,
        )
        if advisory.publication_rejections:
            return False
        consumption = self._projector.validate_for_consumption(
            advisory,
            snapshot,
            evaluated_at_s=snapshot.timestamp_s,
            formal_decision=formal_decision,
        )
        if not consumption.consumable:
            return False
        intervention = _build_projected_intervention_evidence(advisory)
        return bool(intervention.identifiable_intervention_available)

    @staticmethod
    def _validate_base(
        snapshot: RegionResourceSnapshot,
        recommendation: Any,
    ) -> None:
        if not isinstance(recommendation, RegionResourceRecommendation):
            raise RegionResourceDevelopmentInterventionError(
                "development_base_recommendation_type_invalid"
            )
        if recommendation.source is not RecommendationSource.LEARNED:
            raise RegionResourceDevelopmentInterventionError(
                "development_base_candidate_not_learned"
            )
        if recommendation.projected:
            raise RegionResourceDevelopmentInterventionError(
                "development_base_candidate_already_projected"
            )
        if recommendation.fallback_reason is not None:
            raise RegionResourceDevelopmentInterventionError(
                "development_base_candidate_is_fallback"
            )
        if recommendation.projection_rejections:
            raise RegionResourceDevelopmentInterventionError(
                "development_base_candidate_has_projection_rejections"
            )
        if not isinstance(recommendation.model_sha256, str) or not (
            _SHA256_RE.fullmatch(recommendation.model_sha256)
        ):
            raise RegionResourceDevelopmentInterventionError(
                "development_base_model_identity_invalid"
            )
        expected_identity = (
            snapshot.snapshot_id,
            snapshot.scenario_id,
            snapshot.scenario_version,
            int(snapshot.seed),
            snapshot.authority_digest,
        )
        candidate_identity = (
            recommendation.snapshot_id,
            recommendation.scenario_id,
            recommendation.scenario_version,
            int(recommendation.seed),
            recommendation.authority_digest,
        )
        if candidate_identity != expected_identity:
            raise RegionResourceDevelopmentInterventionError(
                "development_base_snapshot_or_authority_mismatch"
            )
        if {
            action.region_id for action in recommendation.actions
        } != set(snapshot.region_by_id):
            raise RegionResourceDevelopmentInterventionError(
                "development_base_region_coverage_invalid"
            )
