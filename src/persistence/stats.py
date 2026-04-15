"""
Pipeline statistics tracking — accumulates stats across the pipeline run.
"""

from dataclasses import dataclass, field


@dataclass
class PipelineStats:
    """Mutable stats tracker for a single pipeline run."""

    total_scanned: int = 0
    pre_filtered: int = 0
    llm_scored: int = 0
    delivered: int = 0
    sources_active: int = 0
    sources_total: int = 0
    source_errors: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_scanned": self.total_scanned,
            "pre_filtered": self.pre_filtered,
            "llm_scored": self.llm_scored,
            "delivered": self.delivered,
            "sources_active": self.sources_active,
            "sources_total": self.sources_total,
            "source_errors": self.source_errors,
            "source_counts": self.source_counts,
        }
