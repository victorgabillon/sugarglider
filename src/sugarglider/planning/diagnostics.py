"""Immutable canonical search, budget, and cache diagnostics."""

from typing import Any, Self

from pydantic import Field, model_validator

from sugarglider.planning.models import CanonicalModel


class PhaseUsage(CanonicalModel):
    used: int = Field(ge=0)
    limit: int = Field(ge=0)
    remaining: int = Field(ge=0)
    exhausted: bool


class BudgetDiagnostics(CanonicalModel):
    phases: dict[str, PhaseUsage]
    total_used: int = Field(ge=0)
    total_limit: int = Field(ge=0)
    total_remaining: int = Field(ge=0)
    global_exhausted: bool

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        if self.total_remaining != max(0, self.total_limit - self.total_used):
            raise ValueError("budget total remaining is inconsistent")
        if self.global_exhausted != (self.total_remaining == 0):
            raise ValueError("budget exhausted flag is inconsistent")
        return self


class CacheDiagnostics(CanonicalModel):
    lookup_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    miss_count: int = Field(ge=0)
    entry_count: int = Field(ge=0)
    successful_entry_count: int = Field(ge=0)
    failed_entry_count: int = Field(ge=0)
    backend_call_count: int = Field(ge=0)
    pre_backend_rejection_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        if self.lookup_count != self.hit_count + self.miss_count:
            raise ValueError("cache lookups must equal hits plus misses")
        if self.entry_count != (self.successful_entry_count + self.failed_entry_count):
            raise ValueError("cache entries must equal successful plus failed entries")
        if self.backend_call_count != self.miss_count:
            raise ValueError("backend calls must equal cache misses")
        return self

    @property
    def hits(self) -> int:
        return self.hit_count

    @property
    def misses(self) -> int:
        return self.miss_count

    @property
    def entries(self) -> int:
        return self.entry_count


class PlanSearchDiagnostics(CanonicalModel):
    budget: BudgetDiagnostics
    cache: CacheDiagnostics
    warnings: tuple[str, ...] = ()
    details: dict[str, Any] = Field(default_factory=dict)
