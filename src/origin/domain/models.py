"""Domain models for Origin artifacts.

Defines Pydantic schemas and metadata for the core artifacts:
Decisions, Memory entries, and Timeline events.
"""

from datetime import datetime, timezone
from typing import Literal, Union
from pydantic import BaseModel, Field

from origin.domain.ulid import generate_ulid


class ArtifactBase(BaseModel):
    """Base class for all Origin artifacts."""

    id: str = Field(description="Sortable identifier prefixed by type, e.g. dec_01HXYZ...")
    type: Literal["decision", "memory", "timeline_event"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    originating_agent: str = Field(description="e.g. 'claude-code', 'codex-cli', 'human'")
    status: Literal["active", "superseded", "deprecated", "proposed", "rejected"] = "active"
    superseded_by: str | None = None
    warnings: list[str] = Field(default_factory=list, exclude=True)


class Decision(ArtifactBase):
    """Represents an architectural or project decision decision artifact."""

    type: Literal["decision"] = "decision"
    title: str = Field(description="High-level title of the decision")
    rationale: str = Field(description="Detailed explanation of why the decision was made")
    alternatives_considered: list[str] = Field(default_factory=list, description="Other options evaluated")
    affected_files: list[str] = Field(default_factory=list, description="Files affected by this decision")
    confidence: float = Field(default=1.0, description="Confidence level between 0.0 and 1.0")

    @classmethod
    def create(
        cls,
        title: str,
        rationale: str,
        alternatives_considered: list[str],
        affected_files: list[str],
        confidence: float,
        originating_agent: str,
    ) -> "Decision":
        """Helper to create a Decision with an auto-generated prefixed ULID."""
        uid = f"dec_{generate_ulid()}"
        now = datetime.now(timezone.utc)
        return cls(
            id=uid,
            title=title,
            rationale=rationale,
            alternatives_considered=alternatives_considered,
            affected_files=affected_files,
            confidence=confidence,
            originating_agent=originating_agent,
            created_at=now,
            updated_at=now,
        )


class MemoryEntry(ArtifactBase):
    """Represents a long-term piece of project knowledge (architecture, stack, glossary)."""

    type: Literal["memory"] = "memory"
    category: Literal["architecture", "convention", "tech_stack", "glossary", "deployment"]
    key: str = Field(description="Key namespace identifier for the memory")
    value: str = Field(description="Content associated with the memory key")

    @classmethod
    def create(
        cls,
        category: Literal["architecture", "convention", "tech_stack", "glossary", "deployment"],
        key: str,
        value: str,
        originating_agent: str,
    ) -> "MemoryEntry":
        """Helper to create a MemoryEntry with an auto-generated prefixed ULID."""
        uid = f"mem_{generate_ulid()}"
        now = datetime.now(timezone.utc)
        return cls(
            id=uid,
            category=category,
            key=key,
            value=value,
            originating_agent=originating_agent,
            created_at=now,
            updated_at=now,
        )


class TimelineEvent(ArtifactBase):
    """Represents an automatically generated event logging history."""

    type: Literal["timeline_event"] = "timeline_event"
    event_type: Literal["decision_created", "decision_superseded", "memory_updated", "commit"]
    ref_artifact_id: str | None = None
    commit_sha: str | None = None
    summary: str

    @classmethod
    def create(
        cls,
        event_type: Literal["decision_created", "decision_superseded", "memory_updated", "commit"],
        summary: str,
        originating_agent: str,
        ref_artifact_id: str | None = None,
        commit_sha: str | None = None,
    ) -> "TimelineEvent":
        """Helper to create a TimelineEvent with an auto-generated prefixed ULID."""
        uid = f"evt_{generate_ulid()}"
        now = datetime.now(timezone.utc)
        return cls(
            id=uid,
            event_type=event_type,
            summary=summary,
            originating_agent=originating_agent,
            ref_artifact_id=ref_artifact_id,
            commit_sha=commit_sha,
            created_at=now,
            updated_at=now,
        )


# Union type for all artifact variants
Artifact = Union[Decision, MemoryEntry, TimelineEvent]
