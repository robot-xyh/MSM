"""Role-explicit D6 external pre-admission audit for D3 A1."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .learning_module_external_audit import (
    D3_A1_PROFILE,
    LearningModuleExternalAuditArtifact,
    LearningModuleExternalAuditError,
    LearningModuleExternalAuditInputs,
    audit_learning_module_external_evidence,
    load_learning_module_external_audit_inputs,
    render_learning_module_external_audit_markdown,
    write_learning_module_external_audit_report,
)


D3_A1_EXTERNAL_AUDIT_SCHEMA_VERSION = D3_A1_PROFILE.output_schema_version
D3_A1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION = (
    D3_A1_PROFILE.input_schema_version
)
D3_A1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION = (
    D3_A1_PROFILE.consumer_schema_version
)
D3_A1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION = (
    D3_A1_PROFILE.formal_profile_version
)

D3A1ExternalAuditArtifact = LearningModuleExternalAuditArtifact
D3A1ExternalAuditError = LearningModuleExternalAuditError
D3A1ExternalAuditInputs = LearningModuleExternalAuditInputs


def load_d3_a1_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D3A1ExternalAuditInputs:
    """Load one strict D3/A1 v1 request."""

    return load_learning_module_external_audit_inputs(
        path,
        repository_root=repository_root,
        profile_key=D3_A1_PROFILE.key,
    )


def audit_d3_a1_external_evidence(
    inputs: D3A1ExternalAuditInputs,
) -> dict[str, Any]:
    """Audit one D3/A1 candidate without granting runtime authority."""

    if inputs.profile_key != D3_A1_PROFILE.key:
        raise D3A1ExternalAuditError(
            "input_profile_mismatch",
            inputs.profile_key,
        )
    return audit_learning_module_external_evidence(inputs)


def write_d3_a1_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write the deterministic D3/A1 audit artifacts."""

    return write_learning_module_external_audit_report(
        output_dir,
        result,
        profile_key=D3_A1_PROFILE.key,
    )


def render_d3_a1_external_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the D3/A1 audit in Chinese."""

    return render_learning_module_external_audit_markdown(
        result,
        profile_key=D3_A1_PROFILE.key,
    )


__all__ = [
    "D3_A1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION",
    "D3_A1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION",
    "D3_A1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION",
    "D3_A1_EXTERNAL_AUDIT_SCHEMA_VERSION",
    "D3A1ExternalAuditArtifact",
    "D3A1ExternalAuditError",
    "D3A1ExternalAuditInputs",
    "audit_d3_a1_external_evidence",
    "load_d3_a1_external_audit_inputs",
    "render_d3_a1_external_audit_markdown",
    "write_d3_a1_external_audit_report",
]
