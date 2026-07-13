"""Application use cases for Origin.

Coordinates business rules, database actions, git history checks,
and Markdown mirror file refreshes.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional

from origin.config import get_origin_dir, load_config, save_config, WorkspaceConfig
from origin.domain.models import Artifact, Decision, MemoryEntry, TimelineEvent
from origin.exceptions import (
    DecisionNotActiveError,
    DecisionNotFoundError,
    InvalidArtifactError,
    WorkspaceAlreadyInitializedError,
)
from origin.infrastructure.database import ArtifactRepository
from origin.infrastructure.git import GitHelper
from origin.infrastructure.mirror import MirrorWriter


def _get_infra(workspace_root: str) -> tuple[ArtifactRepository, MirrorWriter, GitHelper]:
    """Helper to initialize repository, mirror writer, and git helper for a workspace."""
    config = load_config(workspace_root)
    origin_dir = get_origin_dir(workspace_root)
    db_path = os.path.join(origin_dir, "workspace.db")
    
    repo = ArtifactRepository(db_path)
    mirror = MirrorWriter(origin_dir, config.workspace_name, config.schema_version)
    git = GitHelper(workspace_root)
    
    return repo, mirror, git


def init_workspace(workspace_root: str, workspace_name: str, with_hooks: bool) -> None:
    """Initialize a new Origin workspace in the given directory.

    Creates the .origin directory, config.yaml, empty SQLite database,
    and initializes mirrors.

    Args:
        workspace_root: Path to the workspace root directory.
        workspace_name: Display name for the workspace.
        with_hooks: Whether to install git pre-commit hooks.

    Raises:
        WorkspaceAlreadyInitializedError: If the workspace is already initialized.
    """
    origin_dir = get_origin_dir(workspace_root)
    if os.path.exists(origin_dir):
        raise WorkspaceAlreadyInitializedError(
            f"Origin workspace already initialized at '{origin_dir}'."
        )

    os.makedirs(origin_dir, exist_ok=True)

    # Save initial config
    config = WorkspaceConfig(workspace_name=workspace_name)
    save_config(workspace_root, config)

    # Initialize DB (which triggers table schema generation)
    db_path = os.path.join(origin_dir, "workspace.db")
    repo = ArtifactRepository(db_path)

    # Install Git hooks if requested
    git = GitHelper(workspace_root)
    if with_hooks:
        git.install_hooks()

    # Initial mirror refresh
    mirror = MirrorWriter(origin_dir, workspace_name, config.schema_version)
    mirror.refresh_all(repo)


def add_decision(
    workspace_root: str,
    title: str,
    rationale: str,
    alternatives_considered: List[str],
    affected_files: List[str],
    confidence: float,
    originating_agent: str,
    status: str = "active",
) -> Decision:
    """Record a new decision artifact and log a timeline event.

    Args:
        workspace_root: Path to the workspace root directory.
        title: The decision title.
        rationale: Explanation of the decision.
        alternatives_considered: Alternatives evaluated.
        affected_files: Files affected.
        confidence: Confidence score (0.0 to 1.0).
        originating_agent: Name of the agent recording the decision.
        status: The initial status of the decision (active or proposed).

    Returns:
        The created Decision instance.
    """
    repo, mirror, git = _get_infra(workspace_root)

    # Create and save Decision
    decision = Decision.create(
        title=title,
        rationale=rationale,
        alternatives_considered=alternatives_considered,
        affected_files=affected_files,
        confidence=confidence,
        originating_agent=originating_agent,
    )
    decision.status = status  # type: ignore
    repo.save(decision)

    try:
        # Create and save TimelineEvent
        commit_sha = git.get_current_commit_sha()
        event = TimelineEvent.create(
            event_type="decision_created",
            summary=f"Decision {status}: '{title}'",
            originating_agent=originating_agent,
            ref_artifact_id=decision.id,
            commit_sha=commit_sha,
        )
        repo.save(event)

        # Refresh mirrors
        mirror.refresh_all(repo)
    except Exception as e:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Timeline or mirror refresh post-write step failed: {e}", file=sys.stderr)

    return decision


def supersede_decision(
    workspace_root: str,
    old_decision_id: str,
    title: str,
    rationale: str,
    alternatives_considered: List[str],
    affected_files: List[str],
    confidence: float,
    originating_agent: str,
) -> Decision:
    """Supersede an existing decision with a new decision.

    Args:
        workspace_root: Path to the workspace root directory.
        old_decision_id: The ID of the decision to supersede.
        title: The new decision title.
        rationale: Explanation of the new decision.
        alternatives_considered: Alternatives evaluated.
        affected_files: Files affected.
        confidence: Confidence score (0.0 to 1.0).
        originating_agent: Name of the agent recording the decision.

    Returns:
        The new Decision instance.

    Raises:
        DecisionNotFoundError: If old_decision_id doesn't exist.
        DecisionNotActiveError: If the old decision is not active.
    """
    repo, mirror, git = _get_infra(workspace_root)

    # Retrieve old decision
    old_artifact = repo.get(old_decision_id)
    if not old_artifact or not isinstance(old_artifact, Decision):
        raise DecisionNotFoundError(f"Decision with ID '{old_decision_id}' not found.")

    if old_artifact.status != "active":
        raise DecisionNotActiveError(
            f"Decision '{old_decision_id}' is not active (status: {old_artifact.status})."
        )

    # Create new Decision
    new_decision = Decision.create(
        title=title,
        rationale=rationale,
        alternatives_considered=alternatives_considered,
        affected_files=affected_files,
        confidence=confidence,
        originating_agent=originating_agent,
    )
    repo.save(new_decision)

    # Link old decision to new decision
    repo.update_status(old_decision_id, status="superseded", superseded_by=new_decision.id)

    try:
        # Create and save TimelineEvent
        commit_sha = git.get_current_commit_sha()
        event = TimelineEvent.create(
            event_type="decision_superseded",
            summary=f"Decision superseded: '{old_artifact.title}' by '{title}' ({new_decision.id})",
            originating_agent=originating_agent,
            ref_artifact_id=old_decision_id,
            commit_sha=commit_sha,
        )
        repo.save(event)

        # Refresh mirrors
        mirror.refresh_all(repo)
    except Exception as e:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Timeline or mirror refresh post-write step failed: {e}", file=sys.stderr)

    return new_decision


def set_memory(
    workspace_root: str,
    category: str,
    key: str,
    value: str,
    originating_agent: str,
) -> MemoryEntry:
    """Insert or update a memory entry and write a timeline event.

    Args:
        workspace_root: Path to the workspace root directory.
        category: The category (must be architecture, convention, tech_stack, glossary, or deployment).
        key: Key identifier.
        value: The memory value content.
        originating_agent: Name of the agent recording the memory.

    Returns:
        The updated/created MemoryEntry.
    """
    repo, mirror, git = _get_infra(workspace_root)

    valid_categories = ["architecture", "convention", "tech_stack", "glossary", "deployment"]
    if category not in valid_categories:
        raise InvalidArtifactError(
            f"Invalid memory category '{category}'. Must be one of {valid_categories}."
        )

    # Check if memory entry exists
    existing = repo.get_memory_entry(category, key)
    if existing:
        # Update existing
        entry = existing
        entry.value = value
        entry.updated_at = datetime.now(timezone.utc)
        entry.originating_agent = originating_agent
    else:
        # Create new
        entry = MemoryEntry.create(
            category=category,  # type: ignore
            key=key,
            value=value,
            originating_agent=originating_agent,
        )

    repo.save(entry)

    try:
        # Create and save TimelineEvent
        commit_sha = git.get_current_commit_sha()
        event = TimelineEvent.create(
            event_type="memory_updated",
            summary=f"Memory updated: {category}.{key} = '{value}'",
            originating_agent=originating_agent,
            ref_artifact_id=entry.id,
            commit_sha=commit_sha,
        )
        repo.save(event)

        # Refresh mirrors
        mirror.refresh_all(repo)
    except Exception as e:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Timeline or mirror refresh post-write step failed: {e}", file=sys.stderr)

    return entry


def get_memory(workspace_root: str, category: str, key: str) -> Optional[MemoryEntry]:
    """Retrieve an active memory entry by category and key.

    Args:
        workspace_root: Path to the workspace root directory.
        category: Category namespace.
        key: Key identifier.

    Returns:
        The MemoryEntry if found, otherwise None.
    """
    repo, _, _ = _get_infra(workspace_root)
    return repo.get_memory_entry(category, key)


def search_artifacts(workspace_root: str, query: str) -> List[Artifact]:
    """Perform keyword search across decisions and memory entries.

    Args:
        workspace_root: Path to the workspace root directory.
        query: Search keyword.

    Returns:
        List of matching decisions and memory entries.
    """
    repo, _, _ = _get_infra(workspace_root)
    return repo.search(query)


def get_context_bundle(workspace_root: str) -> str:
    """Compile active decisions and memory entries into a prompt-friendly context string.

    Args:
        workspace_root: Path to the workspace root directory.

    Returns:
        A Markdown formatted context bundle string.
    """
    repo, mirror, _ = _get_infra(workspace_root)
    decisions = repo.list_decisions(status="active")
    memories = repo.list_memory()
    return mirror.generate_context_bundle(decisions, memories)


def accept_decision(workspace_root: str, decision_id: str, agent: str) -> Decision:
    """Accept a proposed decision, transitioning its status to active.

    Args:
        workspace_root: Path to the workspace root directory.
        decision_id: The ID of the decision to accept.
        agent: Name of the agent accepting the decision.

    Returns:
        The updated Decision instance.
    """
    repo, mirror, git = _get_infra(workspace_root)
    decision = repo.get(decision_id)
    if not decision or not isinstance(decision, Decision):
        raise DecisionNotFoundError(f"Decision with ID '{decision_id}' not found.")

    decision.status = "active"
    decision.updated_at = datetime.now(timezone.utc)
    decision.originating_agent = agent
    repo.save(decision)

    try:
        commit_sha = git.get_current_commit_sha()
        event = TimelineEvent.create(
            event_type="decision_created",
            summary=f"Decision accepted: '{decision.title}'",
            originating_agent=agent,
            ref_artifact_id=decision.id,
            commit_sha=commit_sha,
        )
        repo.save(event)
        mirror.refresh_all(repo)
    except Exception as e:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Timeline or mirror refresh post-write step failed: {e}", file=sys.stderr)
    return decision


def reject_decision(workspace_root: str, decision_id: str, agent: str) -> Decision:
    """Reject a proposed decision, transitioning its status to rejected.

    Args:
        workspace_root: Path to the workspace root directory.
        decision_id: The ID of the decision to reject.
        agent: Name of the agent rejecting the decision.

    Returns:
        The updated Decision instance.
    """
    repo, mirror, git = _get_infra(workspace_root)
    decision = repo.get(decision_id)
    if not decision or not isinstance(decision, Decision):
        raise DecisionNotFoundError(f"Decision with ID '{decision_id}' not found.")

    decision.status = "rejected"
    decision.updated_at = datetime.now(timezone.utc)
    decision.originating_agent = agent
    repo.save(decision)

    try:
        commit_sha = git.get_current_commit_sha()
        event = TimelineEvent.create(
            event_type="decision_superseded",
            summary=f"Decision rejected: '{decision.title}'",
            originating_agent=agent,
            ref_artifact_id=decision.id,
            commit_sha=commit_sha,
        )
        repo.save(event)
        mirror.refresh_all(repo)
    except Exception as e:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Timeline or mirror refresh post-write step failed: {e}", file=sys.stderr)
    return decision


def sync_git_commits(workspace_root: str, agent: str = "human") -> None:
    """Scan git log for Origin-Decision trailers and record commit events idempotently.

    Args:
        workspace_root: Path to the workspace root directory.
        agent: The originating agent mapping the commits.
    """
    repo, mirror, git = _get_infra(workspace_root)
    commits = git.get_commits_with_trailer()
    if not commits:
        return

    repo.sync_index()
    existing_events = {}
    with repo._get_connection() as conn:
        cursor = conn.execute(
            "SELECT ref_artifact_id, commit_sha FROM artifacts WHERE type = 'timeline_event' AND event_type = 'commit'"
        )
        for row in cursor:
            existing_events[(row["ref_artifact_id"], row["commit_sha"])] = True

    new_events_created = False
    for commit in commits:
        sha = commit["sha"]
        subject = commit["subject"]
        for dec_id in commit["decision_ids"]:
            if (dec_id, sha) in existing_events:
                continue

            event = TimelineEvent.create(
                event_type="commit",
                summary=f"Commit {sha[:7]}: {subject}",
                originating_agent=agent,
                ref_artifact_id=dec_id,
                commit_sha=sha,
            )
            repo.save(event)
            existing_events[(dec_id, sha)] = True
            new_events_created = True

    if new_events_created:
        mirror.refresh_all(repo)


def migrate_workspace(workspace_root: str) -> None:
    """Migrates a v1.0 SQLite-only workspace to a v2.0 filesystem-first workspace.

    Args:
        workspace_root: Path to the workspace root directory.
    """
    origin_dir = get_origin_dir(workspace_root)
    db_path = os.path.join(origin_dir, "workspace.db")
    if not os.path.exists(db_path):
        return

    # Check if already migrated
    try:
        config = load_config(workspace_root)
        if config.schema_version == "2.0":
            return
    except Exception:
        pass

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='artifacts'")
    if not cursor.fetchone():
        conn.close()
        return

    cursor = conn.execute("SELECT * FROM artifacts")
    rows = cursor.fetchall()
    conn.close()

    # Re-initialize repository
    repo = ArtifactRepository(db_path)

    import json
    for row in rows:
        data = dict(row)
        art_type = data["type"]

        if art_type == "decision":
            alts = data.get("alternatives_considered")
            affs = data.get("affected_files")
            data["alternatives_considered"] = json.loads(alts) if alts else []
            data["affected_files"] = json.loads(affs) if affs else []
            artifact = Decision.model_validate(data)
        elif art_type == "memory":
            artifact = MemoryEntry.model_validate(data)
        elif art_type == "timeline_event":
            artifact = TimelineEvent.model_validate(data)
        else:
            continue

        repo.save(artifact)

    config = WorkspaceConfig(workspace_name=load_config(workspace_root).workspace_name)
    config.schema_version = "2.0"
    save_config(workspace_root, config)

    repo.sync_index(force=True)
    mirror = MirrorWriter(origin_dir, config.workspace_name, "2.0")
    mirror.refresh_all(repo)


def import_conventions(workspace_root: str) -> List[dict]:
    """Scan project manifest files for high-signal tech stack and conventions memory.

    Files scanned:
      - pyproject.toml / requirements.txt (Python deps)
      - package.json (JS/TS deps)
      - docker-compose.yml (infra services)

    Falls back to README.md/ARCHITECTURE.md keyword parsing if no manifest findings exist.
    """
    suggestions = []

    # 1. Parse pyproject.toml
    pyproject_path = os.path.join(workspace_root, "pyproject.toml")
    if os.path.exists(pyproject_path):
        suggestions.append({
            "category": "tech_stack",
            "key": "language",
            "value": "python",
        })
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
                for fw in ["django", "flask", "fastapi", "pytest"]:
                    if fw in content.lower():
                        suggestions.append({
                            "category": "tech_stack",
                            "key": "framework",
                            "value": fw,
                        })
        except Exception:
            pass

    # 2. Parse requirements.txt
    reqs_path = os.path.join(workspace_root, "requirements.txt")
    if os.path.exists(reqs_path):
        suggestions.append({
            "category": "tech_stack",
            "key": "language",
            "value": "python",
        })
        try:
            with open(reqs_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for fw in ["django", "flask", "fastapi", "pytest"]:
                    if fw in content:
                        suggestions.append({
                            "category": "tech_stack",
                            "key": "framework",
                            "value": fw,
                        })
        except Exception:
            pass

    # 3. Parse package.json
    pkg_path = os.path.join(workspace_root, "package.json")
    if os.path.exists(pkg_path):
        suggestions.append({
            "category": "tech_stack",
            "key": "language",
            "value": "javascript/typescript",
        })
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for fw in ["react", "vue", "next", "express", "nestjs"]:
                    if fw in content:
                        suggestions.append({
                            "category": "tech_stack",
                            "key": "framework",
                            "value": fw,
                        })
        except Exception:
            pass

    # 4. Parse docker-compose.yml
    compose_path = os.path.join(workspace_root, "docker-compose.yml")
    if os.path.exists(compose_path):
        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for db in ["postgres", "mysql", "redis", "mongodb"]:
                    if db in content:
                        suggestions.append({
                            "category": "tech_stack",
                            "key": "database",
                            "value": db,
                        })
        except Exception:
            pass

    # Fallback to README/ARCHITECTURE keyword scanning if suggestions list is empty
    if not suggestions:
        for filename in ["README.md", "ARCHITECTURE.md"]:
            doc_path = os.path.join(workspace_root, filename)
            if os.path.exists(doc_path):
                try:
                    with open(doc_path, "r", encoding="utf-8") as f:
                        content = f.read().lower()
                        if "python" in content:
                            suggestions.append({"category": "tech_stack", "key": "language", "value": "python"})
                        if "javascript" in content or "typescript" in content:
                            suggestions.append({"category": "tech_stack", "key": "language", "value": "javascript/typescript"})
                        if "fastapi" in content:
                            suggestions.append({"category": "tech_stack", "key": "framework", "value": "fastapi"})
                        if "postgresql" in content or "postgres" in content:
                            suggestions.append({"category": "tech_stack", "key": "database", "value": "postgres"})
                        if "sqlite" in content:
                            suggestions.append({"category": "tech_stack", "key": "database", "value": "sqlite"})
                except Exception:
                    pass

    # Deduplicate suggestions by (category, key)
    seen = set()
    deduped = []
    for s in suggestions:
        pair = (s["category"], s["key"])
        if pair not in seen:
            seen.add(pair)
            deduped.append(s)

    return deduped
