"""Shared ten-pixel recognition rule."""

from __future__ import annotations


DEFAULT_RECOGNITION_EXTENT_PX = 10.0


def bbox_longest_side_px(bbox_xyxy: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox_xyxy must have non-negative width and height")
    return max(x2 - x1, y2 - y1)


def is_recognizable_bbox(
    bbox_xyxy: tuple[float, float, float, float],
    *,
    minimum_extent_px: float = DEFAULT_RECOGNITION_EXTENT_PX,
) -> bool:
    if minimum_extent_px <= 0.0:
        raise ValueError("minimum_extent_px must be positive")
    return bbox_longest_side_px(bbox_xyxy) >= float(minimum_extent_px)
