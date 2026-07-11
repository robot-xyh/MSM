"""Runtime guidance-law selection contract exposed by D7 to main."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RuntimeGuidanceLaw(str, Enum):
    """The four runtime strategies supported by the main/D7 contract."""

    PURE_PURSUIT = "pure_pursuit"
    RADAR_PN = "radar_pn"
    PNG_VM = "png_vm"
    PNG_TTC = "png_ttc"


VISUAL_HANDOVER_LAWS = frozenset(
    {RuntimeGuidanceLaw.PNG_VM, RuntimeGuidanceLaw.PNG_TTC}
)


@dataclass(frozen=True)
class GuidanceLawSelection:
    """Normalized full-course or radar-to-vision guidance strategy."""

    requested_law: RuntimeGuidanceLaw
    midcourse_law: RuntimeGuidanceLaw
    terminal_law: RuntimeGuidanceLaw | None
    requires_terminal_gate: bool


def select_runtime_guidance_law(
    value: RuntimeGuidanceLaw | str | Any | None,
    *,
    default_visual_law: str = "png_vm",
) -> GuidanceLawSelection:
    """Normalize a caller request without changing any guidance-law formula.

    ``pn`` remains accepted as an input alias for older offline callers, but
    the public/logged runtime name is always ``radar_pn``.
    """

    if value is None:
        value = default_visual_law
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip().lower()
    if text == "pn":
        text = RuntimeGuidanceLaw.RADAR_PN.value
    try:
        requested = RuntimeGuidanceLaw(text)
    except ValueError as exc:
        supported = ", ".join(law.value for law in RuntimeGuidanceLaw)
        raise ValueError(f"guidance law must be one of: {supported}") from exc

    if requested in VISUAL_HANDOVER_LAWS:
        return GuidanceLawSelection(
            requested_law=requested,
            midcourse_law=RuntimeGuidanceLaw.RADAR_PN,
            terminal_law=requested,
            requires_terminal_gate=True,
        )
    return GuidanceLawSelection(
        requested_law=requested,
        midcourse_law=requested,
        terminal_law=None,
        requires_terminal_gate=False,
    )
