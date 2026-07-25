"""SQLite index and YAML filesystem repository for Origin artifacts.

Provides decentralized persistent storage using individual text files (YAML)
as the source of truth, with a local SQLite database acting as a rebuildable
query index/cache.
"""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import yaml

logger = logging.getLogger(__name__)

from origin.domain.models import Artifact, Decision, MemoryEntry, TimelineEvent


def sanitize_name(name: str) -> str:
    """Sanitize category or key names to be safe for filenames.

    Allows alphanumeric characters, underscores, and hyphens.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", name)
    if not sanitized:
        raise ValueError(
            f"Invalid identifier: '{name}'. Sanitized name cannot be empty."
        )
    return sanitized


def atomic_write_yaml(file_path: str, data: dict) -> None:
    """Write serialized data to a temporary file, then atomically replace the target file.

    Args:
        file_path: Target output path.
        data: Serialization dictionary.
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp_path = file_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        # Atomically replace
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e


class ArtifactRepository:
    """Repository class managing YAML file persistence and SQLite indexing."""

    def __init__(self, db_path: str) -> None:
        """Initialize the repository and configure subdirectories.

        Args:
            db_path: Path to the workspace index database (.origin/workspace.db).
        """
        self.db_path = os.path.abspath(db_path)
        self.origin_dir = os.path.dirname(self.db_path)
        
        self.decisions_dir = os.path.join(self.origin_dir, "decisions")
        self.memory_dir = os.path.join(self.origin_dir, "memory")
        self.timeline_dir = os.path.join(self.origin_dir, "timeline")

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a sqlite3.Connection with WAL mode enabled and dict-like row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        """Initialize the SQLite index database schemas."""
        os.makedirs(self.origin_dir, exist_ok=True)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            conn.commit()

    def _get_dir_state(self) -> Dict[str, Any]:
        """Generate a fast checksum/mtime snapshot of the YAML subdirectories.

        Returns:
            A dictionary tracking count and max mtime for each directory.
        """
        state = {}
        for sub, path in [
            ("decisions", self.decisions_dir),
            ("memory", self.memory_dir),
            ("timeline", self.timeline_dir),
        ]:
            if not os.path.isdir(path):
                state[sub] = {"count": 0, "max_mtime": 0.0}
                continue
            files = [
                os.path.join(path, f)
                for f in os.listdir(path)
                if f.endswith(".yaml") and not f.endswith(".tmp")
            ]
            if not files:
                state[sub] = {"count": 0, "max_mtime": 0.0}
                continue
            count = len(files)
            max_mtime = max(os.path.getmtime(f) for f in files)
            state[sub] = {"count": count, "max_mtime": max_mtime}
        return state

    def _get_stored_sync_state(self) -> Optional[Dict[str, Any]]:
        """Retrieve the last sync checksum snapshot from SQLite index metadata."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'last_sync_state'")
                row = cursor.fetchone()
                if row:
                    return json.loads(row["value"])
        except Exception:
            pass
        return None

    def _set_stored_sync_state(self, state: Dict[str, Any]) -> None:
        """Save the current sync checksum snapshot to SQLite index metadata."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync_state', ?)",
                    (json.dumps(state),),
                )
                conn.commit()
        except Exception:
            pass

    def _get_file_mtimes(self) -> Dict[str, float]:
        """Generate a dict mapping absolute file path -> mtime for all YAML artifacts."""
        mtimes: Dict[str, float] = {}
        for folder in [self.decisions_dir, self.memory_dir, self.timeline_dir]:
            if not os.path.isdir(folder):
                continue
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.endswith(".yaml") and not f.endswith(".tmp"):
                        full_path = os.path.join(root, f)
                        try:
                            mtimes[full_path] = os.path.getmtime(full_path)
                        except Exception:
                            pass
        return mtimes

    def _get_stored_file_mtimes(self) -> Dict[str, float]:
        """Retrieve last recorded file mtimes dictionary from metadata."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'file_mtimes'")
                row = cursor.fetchone()
                if row:
                    return json.loads(row["value"])
        except Exception:
            pass
        return {}

    def _set_stored_file_mtimes(self, mtimes: Dict[str, float]) -> None:
        """Save file mtimes dictionary to metadata."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('file_mtimes', ?)",
                    (json.dumps(mtimes),),
                )
                conn.commit()
        except Exception:
            pass

    def sync_index(self, force: bool = False) -> None:
        """Synchronize SQLite cache index from YAML source files incrementally."""
        current_mtimes = self._get_file_mtimes()

        if force:
            # Full rebuild requested
            with self._get_connection() as conn:
                conn.execute("DELETE FROM artifacts")
                conn.commit()
            stored_mtimes: Dict[str, float] = {}
        else:
            stored_mtimes = self._get_stored_file_mtimes()
            if stored_mtimes == current_mtimes:
                return  # Database index is already fresh!

        # Compute diff
        added_or_modified = [
            f for f, mtime in current_mtimes.items()
            if f not in stored_mtimes or mtime > stored_mtimes.get(f, 0.0)
        ]
        deleted_files = [
            f for f in stored_mtimes if f not in current_mtimes
        ]

        if not added_or_modified and not deleted_files and not force:
            return

        # Process removals
        if deleted_files:
            with self._get_connection() as conn:
                for f in deleted_files:
                    stem = os.path.splitext(os.path.basename(f))[0]
                    conn.execute("DELETE FROM artifacts WHERE id = ?", (stem,))
                conn.commit()

        # Process additions/modifications incrementally
        for f in added_or_modified:
            if not os.path.exists(f):
                continue
            folder_name = os.path.basename(os.path.dirname(f))
            if folder_name == "decisions":
                model_cls = Decision
            elif folder_name == "timeline":
                model_cls = TimelineEvent
            else:
                model_cls = MemoryEntry

            try:
                with open(f, "r", encoding="utf-8") as file_obj:
                    data = yaml.safe_load(file_obj)
                if data:
                    artifact = model_cls.model_validate(data)
                    self._save_to_index(artifact)
            except Exception as e:
                logger.warning(f"Error indexing file {f}: {e}")

        current_dir_state = self._get_dir_state()
        self._set_stored_sync_state(current_dir_state)
        self._set_stored_file_mtimes(current_mtimes)

    def _save_to_index(self, artifact: Artifact) -> None:
        """Save an artifact record directly to SQLite index (no file IO)."""
        data: Dict[str, Any] = {
            "id": artifact.id,
            "type": artifact.type,
            "created_at": artifact.created_at.isoformat(),
            "updated_at": artifact.updated_at.isoformat(),
            "originating_agent": artifact.originating_agent,
            "status": artifact.status,
            "superseded_by": artifact.superseded_by,
        }

        # Clear other type fields
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

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = list(data.values())

        query = f"INSERT OR REPLACE INTO artifacts ({columns}) VALUES ({placeholders})"

        with self._get_connection() as conn:
            conn.execute(query, values)
            conn.commit()

    def _row_to_artifact(self, row: sqlite3.Row) -> Artifact:
        """Map a database row dictionary to its appropriate Pydantic Artifact instance."""
        data = dict(row)
        art_type = data["type"]

        if art_type == "decision":
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
        """Save a new artifact or update an existing one to filesystem (source of truth).

        Args:
            artifact: The Decision, MemoryEntry, or TimelineEvent to persist.
        """
        # Determine target file path
        if isinstance(artifact, Decision):
            file_path = os.path.join(self.decisions_dir, f"{artifact.id}.yaml")
        elif isinstance(artifact, MemoryEntry):
            cat_san = sanitize_name(artifact.category)
            key_san = sanitize_name(artifact.key)
            file_path = os.path.join(self.memory_dir, f"{cat_san}.{key_san}.yaml")
        elif isinstance(artifact, TimelineEvent):
            file_path = os.path.join(self.timeline_dir, f"{artifact.id}.yaml")
        else:
            raise ValueError(f"Unknown artifact type: {type(artifact)}")

        # Serialize Pydantic model to JSON format first to clean dates, then write YAML
        serialized_data = artifact.model_dump(mode="json")
        atomic_write_yaml(file_path, serialized_data)

        # Mirror write to the local index directly to keep cache fast
        self._save_to_index(artifact)

        # Update metadata sync state immediately to avoid triggering sync checks on subsequent read
        self._set_stored_sync_state(self._get_dir_state())

    def get(self, artifact_id: str) -> Optional[Artifact]:
        """Retrieve an artifact by its unique ID.

        Args:
            artifact_id: The ID of the artifact to fetch.

        Returns:
            The Artifact instance if found, otherwise None.
        """
        self.sync_index()
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_artifact(row)
        return None

    def get_memory_entry(self, category: str, key: str) -> Optional[MemoryEntry]:
        """Retrieve an active memory entry by its category and key.

        Args:
            category: The category of the memory (e.g. tech_stack).
            key: The key identifier.

        Returns:
            The MemoryEntry instance if found and active, otherwise None.
        """
        self.sync_index()
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
            status: Optional status to filter by (e.g. "active", "superseded", "proposed").

        Returns:
            A list of Decision objects, sorted by created_at ascending.
        """
        self.sync_index()
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
        self.sync_index()
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
        self.sync_index()
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
            status: The new status value (e.g. active, superseded, rejected).
            superseded_by: Optional ID of the artifact replacing this one.
        """
        artifact = self.get(artifact_id)
        if artifact:
            artifact.status = status  # type: ignore
            artifact.superseded_by = superseded_by
            artifact.updated_at = datetime.now(timezone.utc)
            self.save(artifact)

    def search(self, query: str) -> List[Artifact]:
        """Perform keyword search across decisions and memory entries."""
        self.sync_index()
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
