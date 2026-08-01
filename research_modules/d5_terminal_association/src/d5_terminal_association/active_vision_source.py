"""Source-domain semantics for D5 active-vision research artifacts.

The source domain is a bounded declaration that is hashed with the episode
artifact.  It is not a runtime attestation.  In particular, declaring AirSim
or real-camera provenance cannot establish that evidence without an external
audit owned by main/D6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION = (
    "d5.active-vision-source-provenance.v1"
)


class ActiveVisionSourceDomain(str, Enum):
    """Closed source-domain vocabulary for active-vision episodes."""

    LEGACY_UNSPECIFIED = "legacy_unspecified"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    SCALABLE_3D_POINT_MASS_RUNTIME = "scalable_3d_point_mass_runtime"
    AIRSIM_RUNTIME = "airsim_runtime"
    REAL_CAMERA_RUNTIME = "real_camera_runtime"


class ActiveVisionEvidenceTier(str, Enum):
    """Maximum claim scope implied by a source declaration alone."""

    LEGACY_UNCLASSIFIED = "legacy_unclassified"
    SOFTWARE_FIXTURE_ONLY = "software_fixture_only"
    SIMULATION_RESEARCH = "simulation_research"
    AIRSIM_DECLARATION_ONLY = "airsim_declaration_only"
    REAL_CAMERA_DECLARATION_ONLY = "real_camera_declaration_only"


_EVIDENCE_TIER_BY_DOMAIN = {
    ActiveVisionSourceDomain.LEGACY_UNSPECIFIED: (
        ActiveVisionEvidenceTier.LEGACY_UNCLASSIFIED
    ),
    ActiveVisionSourceDomain.SYNTHETIC_FIXTURE: (
        ActiveVisionEvidenceTier.SOFTWARE_FIXTURE_ONLY
    ),
    ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME: (
        ActiveVisionEvidenceTier.SIMULATION_RESEARCH
    ),
    ActiveVisionSourceDomain.AIRSIM_RUNTIME: (
        ActiveVisionEvidenceTier.AIRSIM_DECLARATION_ONLY
    ),
    ActiveVisionSourceDomain.REAL_CAMERA_RUNTIME: (
        ActiveVisionEvidenceTier.REAL_CAMERA_DECLARATION_ONLY
    ),
}


class ActiveVisionSourceValidationError(ValueError):
    """Stable validation error for source-domain declarations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class ActiveVisionSourceProvenanceV1:
    """A declaration bound to an episode, not an external attestation."""

    source_domain: ActiveVisionSourceDomain
    schema_version: str = ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION:
            raise ActiveVisionSourceValidationError(
                "source_provenance_schema_mismatch",
                "active-vision source provenance schema mismatch",
            )
        try:
            domain = ActiveVisionSourceDomain(self.source_domain)
        except (TypeError, ValueError) as exc:
            raise ActiveVisionSourceValidationError(
                "source_domain_invalid",
                "active-vision source domain is unknown",
            ) from exc
        if domain is ActiveVisionSourceDomain.LEGACY_UNSPECIFIED:
            raise ActiveVisionSourceValidationError(
                "legacy_source_domain_declaration_forbidden",
                "legacy_unspecified is represented only by an absent provenance envelope",
            )
        object.__setattr__(self, "source_domain", domain)

    @property
    def evidence_tier(self) -> ActiveVisionEvidenceTier:
        return evidence_tier_for_source_domain(self.source_domain)

    def to_payload(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "source_domain": self.source_domain.value,
            "evidence_tier": self.evidence_tier.value,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        synthetic_fixture: bool,
    ) -> "ActiveVisionSourceProvenanceV1":
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version",
            "source_domain",
            "evidence_tier",
        }:
            raise ActiveVisionSourceValidationError(
                "source_provenance_fields_mismatch",
                "active-vision source provenance fields mismatch",
            )
        try:
            domain = ActiveVisionSourceDomain(payload["source_domain"])
        except (TypeError, ValueError) as exc:
            raise ActiveVisionSourceValidationError(
                "source_domain_invalid",
                "active-vision source domain is unknown",
            ) from exc
        value = cls(
            source_domain=domain,
            schema_version=str(payload["schema_version"]),
        )
        if payload["evidence_tier"] != value.evidence_tier.value:
            raise ActiveVisionSourceValidationError(
                "source_evidence_tier_mismatch",
                "source evidence tier does not match the declared source domain",
            )
        validate_source_fixture_consistency(
            value.source_domain,
            synthetic_fixture=synthetic_fixture,
        )
        return value


def evidence_tier_for_source_domain(
    source_domain: ActiveVisionSourceDomain | str,
) -> ActiveVisionEvidenceTier:
    try:
        domain = ActiveVisionSourceDomain(source_domain)
    except (TypeError, ValueError) as exc:
        raise ActiveVisionSourceValidationError(
            "source_domain_invalid",
            "active-vision source domain is unknown",
        ) from exc
    return _EVIDENCE_TIER_BY_DOMAIN[domain]


def normalize_declared_source_domain(
    source_domain: ActiveVisionSourceDomain | str | None,
    *,
    synthetic_fixture: bool,
) -> ActiveVisionSourceDomain | None:
    """Normalize an explicit declaration while preserving legacy absence."""

    if type(synthetic_fixture) is not bool:
        raise ActiveVisionSourceValidationError(
            "synthetic_fixture_flag_invalid",
            "synthetic_fixture must be boolean",
        )
    if source_domain is None:
        return None
    try:
        domain = ActiveVisionSourceDomain(source_domain)
    except (TypeError, ValueError) as exc:
        raise ActiveVisionSourceValidationError(
            "source_domain_invalid",
            "active-vision source domain is unknown",
        ) from exc
    if domain is ActiveVisionSourceDomain.LEGACY_UNSPECIFIED:
        raise ActiveVisionSourceValidationError(
            "legacy_source_domain_declaration_forbidden",
            "legacy_unspecified is represented only by an absent provenance envelope",
        )
    validate_source_fixture_consistency(
        domain,
        synthetic_fixture=synthetic_fixture,
    )
    return domain


def effective_source_domain(
    source_domain: ActiveVisionSourceDomain | str | None,
    *,
    synthetic_fixture: bool,
) -> ActiveVisionSourceDomain:
    """Resolve old artifacts conservatively without promoting their evidence."""

    declared = normalize_declared_source_domain(
        source_domain,
        synthetic_fixture=synthetic_fixture,
    )
    if declared is not None:
        return declared
    if synthetic_fixture:
        return ActiveVisionSourceDomain.SYNTHETIC_FIXTURE
    return ActiveVisionSourceDomain.LEGACY_UNSPECIFIED


def validate_source_fixture_consistency(
    source_domain: ActiveVisionSourceDomain | str,
    *,
    synthetic_fixture: bool,
) -> None:
    if type(synthetic_fixture) is not bool:
        raise ActiveVisionSourceValidationError(
            "synthetic_fixture_flag_invalid",
            "synthetic_fixture must be boolean",
        )
    try:
        domain = ActiveVisionSourceDomain(source_domain)
    except (TypeError, ValueError) as exc:
        raise ActiveVisionSourceValidationError(
            "source_domain_invalid",
            "active-vision source domain is unknown",
        ) from exc
    if (
        domain is ActiveVisionSourceDomain.SYNTHETIC_FIXTURE
        and not synthetic_fixture
    ):
        raise ActiveVisionSourceValidationError(
            "source_fixture_flag_mismatch",
            "synthetic_fixture source domain requires the legacy fixture flag",
        )
    if synthetic_fixture and domain is not ActiveVisionSourceDomain.SYNTHETIC_FIXTURE:
        raise ActiveVisionSourceValidationError(
            "source_fixture_flag_mismatch",
            "only the synthetic-fixture source domain may use the fixture flag",
        )


def source_domain_for_new_artifact(
    source_domain: ActiveVisionSourceDomain | str | None,
    *,
    synthetic_fixture: bool,
) -> ActiveVisionSourceDomain:
    """Resolve the mandatory explicit domain for a newly written artifact.

    Legacy in-memory fixture records may omit the provenance envelope.  They
    can be written only after being conservatively and explicitly classified
    as ``synthetic_fixture``.  A non-fixture record without provenance is
    ambiguous and therefore cannot enter a new artifact.
    """

    declared = normalize_declared_source_domain(
        source_domain,
        synthetic_fixture=synthetic_fixture,
    )
    if declared is not None:
        return declared
    if synthetic_fixture:
        return ActiveVisionSourceDomain.SYNTHETIC_FIXTURE
    raise ActiveVisionSourceValidationError(
        "source_provenance_required_for_new_artifact",
        "new non-fixture active-vision artifacts require an explicit source domain",
    )


def optional_source_provenance_payload(
    source_domain: ActiveVisionSourceDomain | str | None,
    *,
    synthetic_fixture: bool,
) -> dict[str, str] | None:
    declared = normalize_declared_source_domain(
        source_domain,
        synthetic_fixture=synthetic_fixture,
    )
    if declared is None:
        return None
    return ActiveVisionSourceProvenanceV1(declared).to_payload()


def source_domain_from_optional_provenance(
    payload: Mapping[str, Any] | None,
    *,
    synthetic_fixture: bool,
) -> tuple[ActiveVisionSourceDomain, bool]:
    """Return the effective domain and whether it was explicitly declared."""

    if payload is None:
        return (
            effective_source_domain(
                None,
                synthetic_fixture=synthetic_fixture,
            ),
            False,
        )
    provenance = ActiveVisionSourceProvenanceV1.from_payload(
        payload,
        synthetic_fixture=synthetic_fixture,
    )
    return provenance.source_domain, True


__all__ = [
    "ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION",
    "ActiveVisionEvidenceTier",
    "ActiveVisionSourceDomain",
    "ActiveVisionSourceProvenanceV1",
    "ActiveVisionSourceValidationError",
    "effective_source_domain",
    "evidence_tier_for_source_domain",
    "normalize_declared_source_domain",
    "optional_source_provenance_payload",
    "source_domain_for_new_artifact",
    "source_domain_from_optional_provenance",
    "validate_source_fixture_consistency",
]
