"""Normalized progress for semantic routing anchors."""


def normalized_anchor_progress(index: int, point_count: int) -> float:
    """Map one semantic routing-point index to stable normalized progress."""
    if point_count < 1:
        raise ValueError(
            "local refinement requires at least one semantic routing point"
        )
    if not 0 <= index < point_count:
        raise ValueError("local-refinement anchor index is outside its point sequence")
    if point_count == 1:
        return 0.0
    return index / (point_count - 1)
