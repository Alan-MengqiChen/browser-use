from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PageKind(str, Enum):
    UNKNOWN = "unknown"
    HUB = "hub"
    UNIT = "unit"
    DETAIL = "detail"
    PAGINATION = "pagination"
    NOISY = "noisy"


class CandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class WorkUnitStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FATAL = "failed_fatal"
    SKIPPED = "skipped"


class UnitCandidate(BaseModel):
    candidate_id: str
    label: str
    locator: str | None = None
    cluster_id: str | None = None
    parent_branch_key: str | None = None
    tag_name: str | None = None
    role: str | None = None
    discovered_from_url: str | None = None
    status: CandidateStatus = CandidateStatus.CANDIDATE
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkUnit(BaseModel):
    unit_id: str
    label: str
    locator: str | None = None
    source_candidate_id: str | None = None
    status: WorkUnitStatus = WorkUnitStatus.NEW
    visit_count: int = 0
    retry_count: int = 0
    result_count: int = 0
    last_error: str | None = None
    discovered_from_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NavigationSnapshot(BaseModel):
    url: str | None = None
    title: str | None = None
    h1_text: str | None = None
    h2_text: str | None = None
    main_region_hash: str | None = None


class WorkUnitState(BaseModel):
    page_kind: PageKind = PageKind.UNKNOWN
    current_url: str | None = None

    preferred_hub_url: str | None = None
    active_unit_id: str | None = None
    validating_candidate_id: str | None = None

    hub_pages: set[str] = Field(default_factory=set)

    candidates: dict[str, UnitCandidate] = Field(default_factory=dict)
    units: dict[str, WorkUnit] = Field(default_factory=dict)

    last_pre_action_snapshot: NavigationSnapshot | None = None
    last_post_action_snapshot: NavigationSnapshot | None = None

    last_discovery_step: int = 0
    last_progress_step: int = 0
    last_discovered_labels: list[str] = Field(default_factory=list)

    def pending_unit_ids(self) -> list[str]:
        return [
            unit_id
            for unit_id, unit in self.units.items()
            if unit.status in {
                WorkUnitStatus.NEW,
                WorkUnitStatus.IN_PROGRESS,
                WorkUnitStatus.FAILED_RETRYABLE,
            }
        ]

    def confirmed_candidate_ids(self) -> list[str]:
        return [
            cid for cid, c in self.candidates.items()
            if c.status == CandidateStatus.CONFIRMED
        ]

    def unresolved_candidate_ids(self) -> list[str]:
        return [
            cid for cid, c in self.candidates.items()
            if c.status == CandidateStatus.CANDIDATE
        ]

    def total_units(self) -> int:
        return len(self.units)

    def pending_units(self) -> int:
        return len(self.pending_unit_ids())

    def summary(self) -> str:
        return (
            f"page_kind={self.page_kind.value}, "
            f"candidates={len(self.candidates)}, "
            f"confirmed_candidates={len(self.confirmed_candidate_ids())}, "
            f"units={self.total_units()}, "
            f"pending_units={self.pending_units()}, "
            f"active_unit={self.active_unit_id or '-'}, "
            f"validating_candidate={self.validating_candidate_id or '-'}"
        )