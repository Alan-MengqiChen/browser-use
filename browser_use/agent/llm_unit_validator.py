from __future__ import annotations

import json
import re
from typing import Any

from browser_use.agent.work_unit_models import (
	CandidateStatus,
	WorkUnit,
	WorkUnitState,
)
from browser_use.llm.base import BaseChatModel
from browser_use.llm.messages import SystemMessage, UserMessage


class LLMUnitValidator:
	def _extract_json(self, text: str) -> dict[str, Any]:
		text = (text or "").strip()

		try:
			return json.loads(text)
		except Exception:
			pass

		match = re.search(r"\{.*\}", text, re.DOTALL)
		if match:
			try:
				return json.loads(match.group(0))
			except Exception:
				pass

		return {
			"is_distinct_unit": False,
			"confidence": 0.0,
			"reason": "Failed to parse validator output as JSON.",
		}

	async def validate_candidate_transition(
		self,
		llm: BaseChatModel,
		task: str,
		state: WorkUnitState,
		candidate_id: str,
	) -> dict[str, Any]:
		candidate = state.candidates.get(candidate_id)
		if candidate is None:
			return {
				"is_distinct_unit": False,
				"confidence": 0.0,
				"reason": f"Candidate {candidate_id} not found.",
			}

		before = state.last_pre_action_snapshot
		after = state.last_post_action_snapshot

		if before is None or after is None:
			return {
				"is_distinct_unit": False,
				"confidence": 0.0,
				"reason": "Missing navigation snapshots.",
			}

		system_prompt = """
You are validating whether a clicked candidate represents a distinct work unit for an enumerate-style web task.

A distinct work unit usually means:
- clicking it changes the main content, route, title, heading, or content region
- it represents an independently processable subtask
- it is not just a random inline link, repeated content card, or cosmetic navigation artifact

Return strict JSON only with this schema:
{
  "is_distinct_unit": true or false,
  "confidence": 0.0 to 1.0,
  "reason": "short explanation"
}
""".strip()

		user_prompt = f"""
Task:
{task}

Candidate:
- label: {candidate.label}
- locator: {candidate.locator or "-"}

Before:
- url: {before.url or "-"}
- title: {before.title or "-"}
- h1: {before.h1_text or "-"}
- h2: {before.h2_text or "-"}
- main_region_hash: {before.main_region_hash or "-"}

After:
- url: {after.url or "-"}
- title: {after.title or "-"}
- h1: {after.h1_text or "-"}
- h2: {after.h2_text or "-"}
- main_region_hash: {after.main_region_hash or "-"}

Decide whether this candidate should be upgraded into a confirmed work unit.
Return JSON only.
""".strip()

		response = await llm.ainvoke(
			[
				SystemMessage(content=system_prompt),
				UserMessage(content=user_prompt),
			]
		)

		text = getattr(response, "completion", None) or getattr(response, "text", None) or str(response)
		data = self._extract_json(text)

		if "is_distinct_unit" not in data:
			data["is_distinct_unit"] = False
		if "confidence" not in data:
			data["confidence"] = 0.0
		if "reason" not in data:
			data["reason"] = "Validator output missing reason."

		return data

	def apply_validation_result(
		self,
		state: WorkUnitState,
		candidate_id: str,
		result: dict[str, Any],
		current_step: int,
	) -> bool:
		candidate = state.candidates.get(candidate_id)
		if candidate is None:
			return False

		is_distinct = bool(result.get("is_distinct_unit", False))
		reason = str(result.get("reason", ""))

		candidate.metadata["validation_reason"] = reason
		candidate.metadata["validated_at_step"] = current_step
		candidate.metadata["validation_confidence"] = result.get("confidence", 0.0)

		if is_distinct:
			candidate.status = CandidateStatus.CONFIRMED

			if candidate.candidate_id not in state.units:
				state.units[candidate.candidate_id] = WorkUnit(
					unit_id=candidate.candidate_id,
					label=candidate.label,
					locator=candidate.locator,
					source_candidate_id=candidate.candidate_id,
					discovered_from_url=candidate.discovered_from_url,
				)

			return True

		candidate.status = CandidateStatus.REJECTED
		return False