"""Own the mutable search resources shared by every phase of one request.

Producers and refinements receive the same context. Routing-call facts come from
its gateway and budget; algorithm counters describe proposals and rejections,
so they must never be used to reconstruct backend usage.
"""

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
    """Fix resource identity while allowing the budget, cache and facts to advance.

    Freezing this container prevents a phase from replacing a shared resource.
    It does not freeze the request's mutable counters or make it reusable across
    independent planning requests.
    """

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
