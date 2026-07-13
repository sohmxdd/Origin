"""SQLite infrastructure repository for Origin artifacts.

Provides persistent storage, retrieval, and search over a single SQLite database table.
Includes list serialization/deserialization and WAL mode configuration.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from origin.domain.models import Artifact, Decision, MemoryEntry, TimelineEvent


class ArtifactRepository:
    """Repository class managing database persistence for all Origin artifacts."""

    def __init__(self, db_path: str) -> None:
        """Initialize the repository, open the database, and establish WAL mode.

        Args:
            db_path: Absolute or relative path to the SQLite workspace database.
        """
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a sqlite3.Connection with WAL mode enabled and dict-like row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema if it doesn't already exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    originating_agent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    superseded_by TEXT,
                    
                    -- Decision specific fields
                    title TEXT,
                    rationale TEXT,
                    alternatives_considered TEXT, -- JSON list
                    affected_files TEXT,          -- JSON list
                    confidence REAL,
                    
                    -- MemoryEntry specific fields
                    category TEXT,
                    key TEXT,
                    value TEXT,
                    
                    -- TimelineEvent specific fields
                    event_type TEXT,
                    ref_artifact_id TEXT,
                    commit_sha TEXT,
                    summary TEXT
                )
                """
            )
            conn.commit()

    def _row_to_artifact(self, row: sqlite3.Row) -> Artifact:
        """Map a database row dictionary to its appropriate Pydantic Artifact instance.

        Args:
            row: A sqlite3.Row instance from the artifacts table.

        Returns:
            The parsed Decision, MemoryEntry, or TimelineEvent.
        """
        data = dict(row)
        art_type = data["type"]

        if art_type == "decision":
            # Deserialize JSON fields
            alts = data.get("alternatives_considered")
            affs = data.get("affected_files")
            data["alternatives_considered"] = json.loads(alts) if alts else []
            data["affected_files"] = json.loads(affs) if affs else []
            return Decision.model_validate(data)

        elif art_type == "memory":
            return MemoryEntry.model_validate(data)

        elif art_type == "timeline_event":
            return TimelineEvent.model_validate(data)

        else:
            raise ValueError(f"Unknown artifact type in database: {art_type}")

    def save(self, artifact: Artifact) -> None:
        """Save a new artifact or update an existing one.

        Args:
            artifact: The Decision, MemoryEntry, or TimelineEvent to persist.
        """
        # Serialize fields into a dictionary
        data: Dict[str, Any] = {
            "id": artifact.id,
            "type": artifact.type,
            "created_at": artifact.created_at.isoformat(),
            "updated_at": artifact.updated_at.isoformat(),
            "originating_agent": artifact.originating_agent,
            "status": artifact.status,
            "superseded_by": artifact.superseded_by,
        }

        # Clear other type fields to ensure clean row schema representation
        for field in [
            "title", "rationale", "alternatives_considered", "affected_files", "confidence",
            "category", "key", "value",
            "event_type", "ref_artifact_id", "commit_sha", "summary"
        ]:
            data[field] = None

        if isinstance(artifact, Decision):
            data["title"] = artifact.title
            data["rationale"] = artifact.rationale
            data["alternatives_considered"] = json.dumps(artifact.alternatives_considered)
            data["affected_files"] = json.dumps(artifact.affected_files)
            data["confidence"] = artifact.confidence

        elif isinstance(artifact, MemoryEntry):
            data["category"] = artifact.category
            data["key"] = artifact.key
            data["value"] = artifact.value

        elif isinstance(artifact, TimelineEvent):
            data["event_type"] = artifact.event_type
            data["ref_artifact_id"] = artifact.ref_artifact_id
            data["commit_sha"] = artifact.commit_sha
            data["summary"] = artifact.summary

        # Insert or Replace
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = list(data.values())

        query = f"INSERT OR REPLACE INTO artifacts ({columns}) VALUES ({placeholders})"

        with self._get_connection() as conn:
            conn.execute(query, values)
            conn.commit()

    def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by its unique ID.

        Args:
            artifact_id: The ID of the artifact to fetch.

        Returns:
            The Artifact instance if found, otherwise None.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_artifact(row)
        return None

    def get_memory_entry(self, category: str, key: str) -> Optional[MemoryEntry]:
        """Retrieve an active memory entry by its category and key.

        Args:
            category: The category of the memory (e.g. architecture).
            key: The key identifier.

        Returns:
            The MemoryEntry instance if found and active, otherwise None.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE type = 'memory' AND category = ? AND key = ? AND status = 'active'",
                (category, key),
            )
            row = cursor.fetchone()
            if row:
                artifact = self._row_to_artifact(row)
                if isinstance(artifact, MemoryEntry):
                    return artifact
        return None

    def list_decisions(self, status: Optional[str] = None) -> List[Decision]:
        """List decision artifacts, optionally filtered by status.

        Args:
            status: Optional status to filter by (e.g. "active", "superseded").

        Returns:
            A list of Decision objects, sorted by created_at ascending.
        """
        query = "SELECT * FROM artifacts WHERE type = 'decision'"
        params: List[str] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at ASC"

        decisions: List[Decision] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor:
                artifact = self._row_to_artifact(row)
                if isinstance(artifact, Decision):
                    decisions.append(artifact)
        return decisions

    def list_memory(self) -> List[MemoryEntry]:
        """List active memory entries.

        Returns:
            A list of active MemoryEntry objects, sorted by category and key.
        """
        query = "SELECT * FROM artifacts WHERE type = 'memory' AND status = 'active' ORDER BY category ASC, key ASC"
        entries: List[MemoryEntry] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            for row in cursor:
                artifact = self._row_to_artifact(row)
                if isinstance(artifact, MemoryEntry):
                    entries.append(artifact)
        return entries

    def list_timeline(self) -> List[TimelineEvent]:
        """List all timeline events.

        Returns:
            A list of TimelineEvent objects, sorted by created_at ascending.
        """
        query = "SELECT * FROM artifacts WHERE type = 'timeline_event' ORDER BY created_at ASC"
        events: List[TimelineEvent] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            for row in cursor:
                artifact = self._row_to_artifact(row)
                if isinstance(artifact, TimelineEvent):
                    events.append(artifact)
        return events

    def update_status(self, artifact_id: str, status: str, superseded_by: Optional[str] = None) -> None:
        """Update the status and supersession pointer of an artifact.

        Args:
            artifact_id: The ID of the artifact to update.
            status: The new status value.
            superseded_by: Optional ID of the artifact replacing this one.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE artifacts
                SET status = ?, superseded_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, superseded_by, now_str, artifact_id),
            )
            conn.commit()

    def search(self, query: str) -> List[Artifact]:
        """Perform keyword search across decisions and memory entries.

        Matches against decision title, rationale, and memory key/value.

        Args:
            query: The search term to match.

        Returns:
            A list of matching Artifact objects.
        """
        sql_query = """
            SELECT * FROM artifacts
            WHERE type IN ('decision', 'memory')
              AND (
                title LIKE ?
                OR rationale LIKE ?
                OR key LIKE ?
                OR value LIKE ?
              )
            ORDER BY created_at DESC
        """
        like_pattern = f"%{query}%"
        results: List[Artifact] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql_query, [like_pattern] * 4)
            for row in cursor:
                results.append(self._row_to_artifact(row))
        return results
