"""Role-explicit D6 external pre-admission audit for D4 A2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .learning_module_external_audit import (
    D4_A2_PROFILE,
    LearningModuleExternalAuditArtifact,
    LearningModuleExternalAuditError,
    LearningModuleExternalAuditInputs,
    audit_learning_module_external_evidence,
    load_learning_module_external_audit_inputs,
    render_learning_module_external_audit_markdown,
    write_learning_module_external_audit_report,
)


D4_A2_EXTERNAL_AUDIT_SCHEMA_VERSION = D4_A2_PROFILE.output_schema_version
D4_A2_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION = (
    D4_A2_PROFILE.input_schema_version
)
D4_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION = (
    D4_A2_PROFILE.consumer_schema_version
)
D4_A2_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION = (
    D4_A2_PROFILE.formal_profile_version
)

D4A2ExternalAuditArtifact = LearningModuleExternalAuditArtifact
D4A2ExternalAuditError = LearningModuleExternalAuditError
D4A2ExternalAuditInputs = LearningModuleExternalAuditInputs


def load_d4_a2_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D4A2ExternalAuditInputs:
    """Load one strict D4/A2 v1 request."""

    return load_learning_module_external_audit_inputs(
        path,
        repository_root=repository_root,
        profile_key=D4_A2_PROFILE.key,
    )


def audit_d4_a2_external_evidence(
    inputs: D4A2ExternalAuditInputs,
) -> dict[str, Any]:
    """Audit one D4/A2 candidate without granting runtime authority."""

    if inputs.profile_key != D4_A2_PROFILE.key:
        raise D4A2ExternalAuditError(
            "input_profile_mismatch",
            inputs.profile_key,
        )
    return audit_learning_module_external_evidence(inputs)


def write_d4_a2_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write the deterministic D4/A2 audit artifacts."""

    return write_learning_module_external_audit_report(
        output_dir,
        result,
        profile_key=D4_A2_PROFILE.key,
    )


def render_d4_a2_external_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the D4/A2 audit in Chinese."""

    return render_learning_module_external_audit_markdown(
        result,
        profile_key=D4_A2_PROFILE.key,
    )


__all__ = [
    "D4_A2_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION",
    "D4_A2_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION",
    "D4_A2_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION",
    "D4_A2_EXTERNAL_AUDIT_SCHEMA_VERSION",
    "D4A2ExternalAuditArtifact",
    "D4A2ExternalAuditError",
    "D4A2ExternalAuditInputs",
    "audit_d4_a2_external_evidence",
    "load_d4_a2_external_audit_inputs",
    "render_d4_a2_external_audit_markdown",
    "write_d4_a2_external_audit_report",
]
