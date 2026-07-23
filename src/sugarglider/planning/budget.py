"""One typed request-scoped search-budget manager."""

from enum import StrEnum

from sugarglider.planning.diagnostics import BudgetDiagnostics, PhaseUsage


class SearchPhase(StrEnum):
    CONTROL = "control"
    SKELETON = "skeleton"
    REQUESTED_STOP = "requested_stop"
    APPROACH = "approach"
    DISCOVERED_POI = "discovered_poi"
    THROUGH_ROUTE = "through_route"
    EXCURSION = "excursion"
    REPAIR = "repair"
    ALTERNATIVE_LEG = "alternative_leg"
    SPUR_REPAIR = "spur_repair"
    REVERSE = "reverse"


class SearchBudget:
    """Reserve typed phase capacity before every uncached routing operation."""

    __slots__ = ("_limits", "_total_limit", "_used")

    def __init__(
        self, limits: dict[SearchPhase, int], *, total_limit: int | None = None
    ) -> None:
        if set(limits) != set(SearchPhase):
            raise ValueError("search budget must define every phase")
        if any(value < 0 for value in limits.values()):
            raise ValueError("search budget limits must be non-negative")
        phase_total = sum(limits.values())
        resolved_total = phase_total if total_limit is None else total_limit
        if resolved_total < 1 or resolved_total > phase_total:
            raise ValueError("global budget must be positive and no larger than phases")
        self._limits = dict(limits)
        self._used = {phase: 0 for phase in SearchPhase}
        self._total_limit = resolved_total

    def reserve(self, phase: SearchPhase) -> bool:
        if self.exhausted(phase) or self.global_exhausted:
            return False
        self._used[phase] += 1
        return True

    def used(self, phase: SearchPhase) -> int:
        return self._used[phase]

    def remaining(self, phase: SearchPhase) -> int:
        return max(0, self._limits[phase] - self._used[phase])

    def limit(self, phase: SearchPhase) -> int:
        return self._limits[phase]

    def exhausted(self, phase: SearchPhase) -> bool:
        return self.remaining(phase) == 0

    @property
    def total_used(self) -> int:
        return sum(self._used.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self._total_limit - self.total_used)

    @property
    def total_limit(self) -> int:
        return self._total_limit

    def snapshot(self) -> BudgetDiagnostics:
        return self.diagnostics()

    @property
    def global_exhausted(self) -> bool:
        return self.total_remaining == 0

    def diagnostics(self) -> BudgetDiagnostics:
        return BudgetDiagnostics(
            phases={
                phase.value: PhaseUsage(
                    used=self.used(phase),
                    limit=self._limits[phase],
                    remaining=self.remaining(phase),
                    exhausted=self.exhausted(phase),
                )
                for phase in SearchPhase
            },
            total_used=self.total_used,
            total_limit=self._total_limit,
            total_remaining=self.total_remaining,
            global_exhausted=self.global_exhausted,
        )
