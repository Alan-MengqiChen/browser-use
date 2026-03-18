from __future__ import annotations

import hashlib
from collections import defaultdict

from browser_use.agent.work_unit_models import UnitCandidate


class StructureClusterer:
    def __init__(self, min_cluster_size: int = 4):
        self.min_cluster_size = min_cluster_size

    def cluster(self, candidates: list[UnitCandidate]) -> dict[str, list[UnitCandidate]]:
        grouped: dict[str, list[UnitCandidate]] = defaultdict(list)

        for c in candidates:
            key = f"{c.parent_branch_key}|{c.tag_name}|{c.role}"
            grouped[key].append(c)

        clusters: dict[str, list[UnitCandidate]] = {}
        for key, items in grouped.items():
            if len(items) < self.min_cluster_size:
                continue

            cluster_id = hashlib.sha256(key.encode()).hexdigest()[:12]
            for item in items:
                item.cluster_id = cluster_id
            clusters[cluster_id] = items

        return clusters

    def rank_clusters(self, clusters: dict[str, list[UnitCandidate]]) -> list[tuple[str, list[UnitCandidate], float]]:
        ranked: list[tuple[str, list[UnitCandidate], float]] = []

        for cluster_id, items in clusters.items():
            labels = [i.label for i in items]
            unique_labels = len(set(labels))
            avg_len = sum(len(x) for x in labels) / max(len(labels), 1)

            score = 0.0
            score += len(items) * 1.5
            score += unique_labels * 0.5

            if avg_len <= 18:
                score += 2.0
            if all(i.locator for i in items):
                score += 2.0

            ranked.append((cluster_id, items, score))

        ranked.sort(key=lambda x: x[2], reverse=True)
        return ranked