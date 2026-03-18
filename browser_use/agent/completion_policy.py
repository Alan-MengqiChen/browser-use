from __future__ import annotations

from dataclasses import dataclass

from browser_use.agent.work_unit_models import WorkUnitState


@dataclass
class CompletionDecision:
    allow_done: bool
    reason: str
    next_label: str | None = None


class CompletionPolicy:
    def __init__(self, max_consecutive_failures_before_partial_stop: int = 8):
        self.max_consecutive_failures_before_partial_stop = max_consecutive_failures_before_partial_stop

    def evaluate(
        self,
        state: WorkUnitState,
        result_success: bool | None,
        consecutive_failures: int,
    ) -> CompletionDecision:
        if state.pending_units() == 0 and len(state.unresolved_candidate_ids()) == 0:
            return CompletionDecision(
                allow_done=True,
                reason="all confirmed work units completed and no unresolved candidates remain",
            )

        next_label = None
        if state.pending_unit_ids():
            next_label = state.units[state.pending_unit_ids()[0]].label
        elif state.unresolved_candidate_ids():
            next_label = state.candidates[state.unresolved_candidate_ids()[0]].label

        if result_success is True:
            return CompletionDecision(
                allow_done=False,
                reason="coverage incomplete",
                next_label=next_label,
            )

        if consecutive_failures < self.max_consecutive_failures_before_partial_stop:
            return CompletionDecision(
                allow_done=False,
                reason="partial stop rejected because recoverable progress is still possible",
                next_label=next_label,
            )

        return CompletionDecision(
            allow_done=True,
            reason="allowing partial stop after repeated failures",
            next_label=next_label,
        )