from __future__ import annotations

import hashlib
import re

from browser_use.agent.work_unit_models import CandidateStatus, NavigationSnapshot, WorkUnit, WorkUnitState


class CandidateValidator:
    def normalize_text(self, text: str | None) -> str:
        if not text:
            return ""
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def main_region_hash(self, selector_map) -> str | None:
        texts: list[str] = []

        for node in selector_map.values():
            if getattr(node, "is_visible", None) is False:
                continue

            tag = (getattr(node, "tag_name", "") or "").lower()
            if tag not in {"main", "article", "section", "div"}:
                continue

            try:
                txt = self.normalize_text(node.get_meaningful_text_for_llm())
            except Exception:
                txt = ""

            if txt and len(txt) > 30:
                texts.append(txt[:500])

        if not texts:
            return None

        joined = "\n".join(texts[:10])
        return hashlib.sha256(joined.encode()).hexdigest()[:16]

    def snapshot_from_state(self, browser_state_summary, selector_map) -> NavigationSnapshot:
        title = getattr(browser_state_summary, "title", None)
        url = getattr(browser_state_summary, "url", None)

        h1_text = None
        h2_text = None

        for node in selector_map.values():
            if getattr(node, "is_visible", None) is False:
                continue
            tag = (getattr(node, "tag_name", "") or "").lower()

            try:
                txt = self.normalize_text(node.get_meaningful_text_for_llm())
            except Exception:
                txt = ""

            if not txt:
                continue

            if tag == "h1" and h1_text is None:
                h1_text = txt
            elif tag == "h2" and h2_text is None:
                h2_text = txt

        return NavigationSnapshot(
            url=url,
            title=title,
            h1_text=h1_text,
            h2_text=h2_text,
            main_region_hash=self.main_region_hash(selector_map),
        )

    def validate_candidate_transition(
        self,
        state: WorkUnitState,
        candidate_id: str,
    ) -> bool:
        before = state.last_pre_action_snapshot
        after = state.last_post_action_snapshot

        if before is None or after is None:
            return False

        changed = 0

        if before.url != after.url:
            changed += 1
        if before.title != after.title:
            changed += 1
        if before.h1_text != after.h1_text and after.h1_text:
            changed += 1
        if before.main_region_hash != after.main_region_hash and after.main_region_hash:
            changed += 1

        if changed >= 1:
            candidate = state.candidates.get(candidate_id)
            if candidate is None:
                return False

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

        candidate = state.candidates.get(candidate_id)
        if candidate is not None:
            candidate.status = CandidateStatus.REJECTED
        return False