"""Native Waypoint quality scoring invoked only by the shared evaluator."""

from dataclasses import dataclass

from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PlanRequestBase, WaypointPlanRequest
from sugarglider.planning.result import PlanScore


@dataclass(frozen=True)
class WaypointScoringWeights:
    distance_error: float = 10.0
    immediate_backtracking: float = 4.0
    repetition: float = 3.0
    major_road: float = 2.0
    paved: float = 1.0
    unknown_surface: float = 0.25
    trail_like: float = 1.5
    hiking_network: float = 0.75
    nature: float = 0.5


class WaypointCandidateScorer:
    """Keep distance and structural safety above optional route preferences."""

    def __init__(self, weights: WaypointScoringWeights | None = None) -> None:
        self._weights = weights or WaypointScoringWeights()

    def score(self, *, request: PlanRequestBase, draft: CandidateDraft) -> PlanScore:
        if not isinstance(request, WaypointPlanRequest):
            raise TypeError("Waypoint scorer requires a Waypoint request")
        route = draft.route
        analysis = route.analysis
        weights = self._weights
        error_ratio = (
            abs(route.summary.distance_m - request.distance_objective.target_m)
            / request.distance_objective.target_m
        )
        distance_weight = {
            "strict": 2.0,
            "balanced": 1.25,
            "flexible": 1.0,
        }[request.distance_objective.priority]
        components = {
            "distance_error_ratio": error_ratio,
            "immediate_backtracking_penalty": (
                weights.immediate_backtracking * analysis.immediate_backtrack.share
            ),
            "repetition_penalty": (
                weights.repetition * analysis.repetition.repeated_distance.share
            ),
            "major_road_penalty": weights.major_road * analysis.major_road.share,
            "paved_penalty": weights.paved * analysis.paved.share,
            "unknown_surface_penalty": (
                weights.unknown_surface * analysis.unknown_surface.share
            ),
            "trail_like_reward": weights.trail_like * analysis.trail_like.share,
            "hiking_network_reward": (
                weights.hiking_network * analysis.official_hiking_network.share
            ),
        }
        nature_reward = 0.0
        if request.preferences.nature == "prefer" and analysis.nature is not None:
            nature_reward = weights.nature * analysis.nature.nature_score / 100.0
        components["nature_reward"] = nature_reward
        total = (
            weights.distance_error * distance_weight * error_ratio
            + components["immediate_backtracking_penalty"]
            + components["repetition_penalty"]
            + components["major_road_penalty"]
            + components["paved_penalty"]
            + components["unknown_surface_penalty"]
            - components["trail_like_reward"]
            - components["hiking_network_reward"]
            - nature_reward
        )
        return PlanScore(total=total, components=components)
