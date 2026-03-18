from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urljoin, urldefrag, urlparse

from browser_use.agent.work_unit_models import UnitCandidate


class UnitCandidateExtractor:
    def __init__(self, max_label_len: int = 32):
        self.max_label_len = max_label_len

    def canon_url(self, base_url: str, href: str) -> str | None:
        if not href:
            return None
        href = href.strip()
        if href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            return None
        abs_url = urljoin(base_url, href)
        abs_url, _ = urldefrag(abs_url)
        return abs_url

    def normalize_label(self, text: str) -> str:
        t = (text or "").strip()
        t = t.splitlines()[0].strip()
        t = re.sub(r"\s+", " ", t)
        return t

    def clickish(self, node: Any) -> bool:
        tag = getattr(node, "tag_name", "")
        attrs = getattr(node, "attributes", {}) or {}
        role = (attrs.get("role") or "").lower()
        return tag in {"a", "button"} or getattr(node, "has_js_click_listener", False) or role in {"link", "button", "tab", "menuitem"}

    def has_bad_ancestor(self, node: Any, max_depth: int = 8) -> bool:
        bad_tags = {"footer", "header"}
        bad_roles = {"contentinfo", "banner"}

        cur = getattr(node, "parent_node", None)
        depth = 0
        while cur is not None and depth < max_depth:
            tag = (getattr(cur, "tag_name", "") or "").lower()
            attrs = getattr(cur, "attributes", {}) or {}
            role = (attrs.get("role") or "").lower()

            if tag in bad_tags or role in bad_roles:
                return True

            cur = getattr(cur, "parent_node", None)
            depth += 1

        return False

    def looks_like_candidate_label(self, text: str) -> bool:
        t = self.normalize_label(text)
        if not t:
            return False
        if len(t) < 2 or len(t) > self.max_label_len:
            return False
        if len(t.split()) > 8:
            return False

        has_meaningful = False
        for ch in t:
            if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
                has_meaningful = True
                break
        return has_meaningful

    def parent_branch_key(self, node: Any) -> str:
        try:
            return str(node.parent_branch_hash())
        except Exception:
            parent = getattr(node, "parent_node", None)
            return f"fallback:{getattr(parent, 'tag_name', 'root')}"

    def extract(self, selector_map: dict[int, Any], current_url: str) -> list[UnitCandidate]:
        results: list[UnitCandidate] = []

        try:
            base_netloc = urlparse(current_url).netloc
        except Exception:
            base_netloc = ""

        for node in selector_map.values():
            if getattr(node, "is_visible", None) is False:
                continue
            if getattr(getattr(node, "node_type", None), "name", "") != "ELEMENT_NODE":
                continue
            if not self.clickish(node):
                continue
            if self.has_bad_ancestor(node):
                continue

            attrs = getattr(node, "attributes", {}) or {}
            role = (attrs.get("role") or "").lower()

            try:
                raw_text = (node.get_meaningful_text_for_llm() or "").strip()
            except Exception:
                raw_text = ""

            label = self.normalize_label(raw_text)
            if not self.looks_like_candidate_label(label):
                continue

            href = (attrs.get("href") or "").strip()
            locator = self.canon_url(current_url, href) if href else None

            if locator:
                try:
                    if base_netloc and urlparse(locator).netloc and urlparse(locator).netloc != base_netloc:
                        continue
                except Exception:
                    pass

            tag_name = getattr(node, "tag_name", None)
            branch_key = self.parent_branch_key(node)

            candidate_id_seed = f"{label}|{locator or ''}|{branch_key}|{tag_name or ''}"
            candidate_id = hashlib.sha256(candidate_id_seed.encode()).hexdigest()[:16]

            results.append(
                UnitCandidate(
                    candidate_id=candidate_id,
                    label=label,
                    locator=locator,
                    parent_branch_key=branch_key,
                    tag_name=tag_name,
                    role=role,
                    discovered_from_url=current_url,
                )
            )

        return results