"""One cohesive request-scoped planning search context."""

from dataclasses import dataclass, field

from sugarglider.planning.budget import SearchBudget
from sugarglider.planning.routing_gateway import CachedRoutingGateway
from sugarglider.routing.backend import AutoTourRoutingBackend


@dataclass
class SearchDiagnosticsCollector:
    """Algorithmic facts which are deliberately not routing-call counters."""

    counters: dict[str, int] = field(default_factory=dict)
    warnings: set[str] = field(default_factory=set)
    rejections: list[str] = field(default_factory=list)

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount


@dataclass(frozen=True)
class PlanningSearchContext:
    budget: SearchBudget
    routes: CachedRoutingGateway
    diagnostics: SearchDiagnosticsCollector

    @classmethod
    def create(
        cls, *, backend: AutoTourRoutingBackend, budget: SearchBudget
    ) -> "PlanningSearchContext":
        return cls(
            budget=budget,
            routes=CachedRoutingGateway(backend, budget),
            diagnostics=SearchDiagnosticsCollector(),
        )
