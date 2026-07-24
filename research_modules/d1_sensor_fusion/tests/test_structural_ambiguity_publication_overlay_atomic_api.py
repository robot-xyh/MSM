from __future__ import annotations

import inspect

from d1_sensor_fusion import (
    run_experimental_centroid_publication_overlay_atomically,
)


def test_atomic_publication_overlay_signature_is_frozen() -> None:
    parameters = inspect.signature(
        run_experimental_centroid_publication_overlay_atomically
    ).parameters

    assert tuple(parameters) == (
        "canonical_tracks",
        "evidence_items",
        "state",
        "config",
        "disposition",
        "base_publication_revision",
        "overlay_valid_for_publication_id",
    )
    assert (
        parameters["canonical_tracks"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert (
        parameters["evidence_items"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    for name in tuple(parameters)[2:]:
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
