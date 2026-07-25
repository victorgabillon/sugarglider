"""Sparse typed neighborhood operators for the shared global optimizer."""

from __future__ import annotations

from dataclasses import replace
from random import Random
from typing import Protocol

from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationMove,
    TourOptimizationState,
)
from sugarglider.planning.optimization.path_pool import LazyPathPool


class OptimizationOperator(Protocol):
    """Cheap descriptor generation followed by selected-path materialization."""

    kind: str

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]: ...

    async def materialize(
        self,
        descriptor: OptimizationMove,
        state: TourOptimizationState,
        *,
        path_pool: LazyPathPool,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> OptimizationMove | None: ...


class _DescriptorOperator:
    async def materialize(
        self,
        descriptor: OptimizationMove,
        state: TourOptimizationState,
        *,
        path_pool: LazyPathPool,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> OptimizationMove | None:
        del state, path_pool, diagnostics
        return descriptor


class PathOptionOperator:
    kind = "path_option"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        if len(state.anchors) < 2:
            return ()
        return tuple(
            OptimizationMove(
                operator="path_option",
                anchors=state.anchors,
                path_request_leg_index=leg_index,
            )
            for leg_index in range(
                min(
                    len(state.anchors) - 1,
                    settings.maximum_candidate_successors_per_anchor,
                )
            )
        )

    async def materialize(
        self,
        descriptor: OptimizationMove,
        state: TourOptimizationState,
        *,
        path_pool: LazyPathPool,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> OptimizationMove | None:
        leg_index = descriptor.path_request_leg_index
        if leg_index is None:
            return None
        options = await path_pool.options_for(
            state.anchors[leg_index],
            state.anchors[leg_index + 1],
            request_alternatives=True,
        )
        current = state.selected_path_option_by_leg[leg_index]
        option = next((value for value in options if value.id != current), None)
        if option is None:
            return None
        return replace(
            descriptor,
            forced_path_option_by_leg=((leg_index, option.id),),
        )


class RelocateOperator(_DescriptorOperator):
    kind = "relocate"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        moves: list[OptimizationMove] = []
        for index, anchor in enumerate(state.anchors):
            if not anchor.movable:
                continue
            same_window = tuple(
                target
                for target in range(1, len(state.anchors))
                if target != index
                and state.anchors[target].exact_window == anchor.exact_window
                and state.anchors[target].kind != "exact"
            )
            for target in same_window[
                : settings.maximum_candidate_successors_per_anchor
            ]:
                values = list(state.anchors)
                moved = values.pop(index)
                insertion = target - int(target > index)
                values.insert(insertion, moved)
                moves.append(
                    OptimizationMove(
                        operator="relocate",
                        anchors=tuple(values),
                        changed_anchor_ids=(anchor.id,),
                    )
                )
        return tuple(moves[: settings.maximum_candidate_successors_per_anchor])


class SwapOperator(_DescriptorOperator):
    kind = "swap"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        moves: list[OptimizationMove] = []
        soft = tuple(
            (index, anchor)
            for index, anchor in enumerate(state.anchors)
            if anchor.movable
        )
        for position, (left_index, left) in enumerate(soft):
            for right_index, right in soft[position + 1 :]:
                if left.exact_window != right.exact_window:
                    continue
                values = list(state.anchors)
                values[left_index], values[right_index] = (
                    values[right_index],
                    values[left_index],
                )
                moves.append(
                    OptimizationMove(
                        operator="swap",
                        anchors=tuple(values),
                        changed_anchor_ids=(left.id, right.id),
                    )
                )
        return tuple(moves[: settings.maximum_candidate_successors_per_anchor])


class TwoOptOperator(_DescriptorOperator):
    kind = "two_opt"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        moves: list[OptimizationMove] = []
        for start in range(1, len(state.anchors) - 1):
            for end in range(start + 1, min(len(state.anchors) - 1, start + 5)):
                section = state.anchors[start : end + 1]
                if (
                    not all(anchor.movable for anchor in section)
                    or len({anchor.exact_window for anchor in section}) != 1
                ):
                    continue
                values = (
                    *state.anchors[:start],
                    *reversed(section),
                    *state.anchors[end + 1 :],
                )
                moves.append(
                    OptimizationMove(
                        operator="two_opt",
                        anchors=values,
                        changed_anchor_ids=tuple(anchor.id for anchor in section),
                    )
                )
        return tuple(moves[: settings.maximum_candidate_successors_per_anchor])


class AlternateApproachOperator(_DescriptorOperator):
    kind = "alternate_approach"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        moves: list[OptimizationMove] = []
        for index, anchor in enumerate(state.anchors):
            if not anchor.movable or anchor.selected_approach is None:
                continue
            alternatives = tuple(
                option
                for option in anchor.approach_options
                if option.id != anchor.selected_approach.id
                and option.access not in {"private", "restricted"}
                and (
                    anchor.maximum_semantic_distance_m is None
                    or option.semantic_distance_m <= anchor.maximum_semantic_distance_m
                )
            )
            for approach in alternatives[
                : settings.maximum_relocation_targets_per_stop
            ]:
                values = list(state.anchors)
                values[index] = replace(
                    anchor,
                    coordinate=approach.coordinate,
                    selected_approach=approach,
                )
                moves.append(
                    OptimizationMove(
                        operator="alternate_approach",
                        anchors=tuple(values),
                        changed_anchor_ids=(anchor.id,),
                    )
                )
        return tuple(moves[: settings.maximum_candidate_successors_per_anchor])


class SpurRejoinOperator(_DescriptorOperator):
    kind = "spur_rejoin"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del state, rng, settings, diagnostics
        # Important-spur batches are deterministically materialized before ALNS.
        return ()


class RuinRecreateOperator(_DescriptorOperator):
    kind = "ruin_recreate"

    def propose_descriptors(
        self,
        state: TourOptimizationState,
        *,
        rng: Random,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
    ) -> tuple[OptimizationMove, ...]:
        del rng, diagnostics
        moves: list[OptimizationMove] = []
        for start in range(1, len(state.anchors) - 2):
            for size in range(2, 5):
                end = start + size
                if end >= len(state.anchors):
                    continue
                section = state.anchors[start:end]
                if (
                    not all(anchor.movable for anchor in section)
                    or len({anchor.exact_window for anchor in section}) != 1
                ):
                    continue
                recreated = (*section[1:], section[0])
                values = (
                    *state.anchors[:start],
                    *recreated,
                    *state.anchors[end:],
                )
                moves.append(
                    OptimizationMove(
                        operator="ruin_recreate",
                        anchors=values,
                        changed_anchor_ids=tuple(anchor.id for anchor in section),
                    )
                )
        return tuple(moves[: settings.maximum_candidate_successors_per_anchor])


def default_operators() -> tuple[OptimizationOperator, ...]:
    return (
        PathOptionOperator(),
        RelocateOperator(),
        SwapOperator(),
        TwoOptOperator(),
        AlternateApproachOperator(),
        SpurRejoinOperator(),
        RuinRecreateOperator(),
    )
