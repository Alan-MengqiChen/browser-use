from __future__ import annotations

from dataclasses import dataclass

from browser_use.agent.work_unit_models import CandidateStatus, PageKind, WorkUnitState, WorkUnitStatus


@dataclass
class SchedulerDecision:
    mode: str
    target_candidate_id: str | None = None
    target_unit_id: str | None = None
    target_label: str | None = None
    target_locator: str | None = None
    reason: str = ""


class CoverageScheduler:
	
	def choose(self, state: WorkUnitState) -> SchedulerDecision:
		# 1. continue validating current candidate if any
		if state.validating_candidate_id and state.validating_candidate_id in state.candidates:
			c = state.candidates[state.validating_candidate_id]
			if c.status == CandidateStatus.CANDIDATE:
				return SchedulerDecision(
					mode="validate_candidate",
					target_candidate_id=c.candidate_id,
					target_label=c.label,
					target_locator=c.locator,
					reason="continue validating active candidate",
				)

		# 2. validate unresolved candidates first
		if state.unresolved_candidate_ids():
			cid = state.unresolved_candidate_ids()[0]
			c = state.candidates[cid]
			return SchedulerDecision(
				mode="validate_candidate",
				target_candidate_id=cid,
				target_label=c.label,
				target_locator=c.locator,
				reason="validate unresolved candidate before continuing execution",
			)

		# 3. continue active confirmed unit
		if state.active_unit_id and state.active_unit_id in state.units:
			unit = state.units[state.active_unit_id]
			if unit.status == WorkUnitStatus.IN_PROGRESS:
				return SchedulerDecision(
					mode="continue_active_unit",
					target_unit_id=unit.unit_id,
					target_label=unit.label,
					target_locator=unit.locator,
					reason="continue active confirmed unit",
				)

		# 4. switch to next pending confirmed unit
		for unit_id in state.pending_unit_ids():
			unit = state.units[unit_id]
			return SchedulerDecision(
				mode="switch_to_pending_unit",
				target_unit_id=unit.unit_id,
				target_label=unit.label,
				target_locator=unit.locator,
				reason="switch to next pending confirmed unit",
			)
		
		return SchedulerDecision(
			mode="finalize",
			reason="no pending units or unresolved candidates",
        )
	
	def render_hint(self, state: WorkUnitState, decision: SchedulerDecision) -> str:
		return (
            f"[WORK_UNIT_SCHEDULER]\n"
            f"mode={decision.mode}\n"
            f"reason={decision.reason}\n"
            f"page_kind={state.page_kind.value}\n"
            f"hub_url={state.preferred_hub_url or '-'}\n"
            f"target_label={decision.target_label or '-'}\n"
            f"target_locator={decision.target_locator or '-'}\n"
            f"pending_units={state.pending_units()}\n"
            f"unresolved_candidates={len(state.unresolved_candidate_ids())}\n"
            f"Rules:\n"
            f"1. If mode=validate_candidate, navigate to the candidate and verify whether it represents a distinct work unit.\n"
            f"2. If mode=continue_active_unit, keep extracting/paginating current unit.\n"
            f"3. If mode=switch_to_pending_unit, navigate toward the selected unit.\n"
            f"4. Do not finish while pending_units > 0 or unresolved_candidates > 0.\n"
        )