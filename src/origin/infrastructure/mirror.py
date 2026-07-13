"""Markdown mirror writer for Origin.

Generates human-readable and agent-friendly markdown files inside the
.origin/ folder reflecting the current active decisions and memory state.
"""

import os
from typing import List

from origin.domain.models import Decision, MemoryEntry
from origin.infrastructure.database import ArtifactRepository


class MirrorWriter:
    """Class responsible for generating Markdown files from repository state."""

    def __init__(self, origin_dir: str, workspace_name: str, schema_version: str) -> None:
        """Initialize the MirrorWriter.

        Args:
            origin_dir: Absolute path to the .origin folder.
            workspace_name: Name of the current workspace.
            schema_version: Schema version of the workspace format.
        """
        self.origin_dir = os.path.abspath(origin_dir)
        self.workspace_name = workspace_name
        self.schema_version = schema_version

    def generate_decisions_md(self, decisions: List[Decision]) -> str:
        """Format active decisions into a structured markdown string."""
        content = [
            "# Origin Decisions Mirror\n",
            "This file is an auto-generated mirror of the active decisions in this workspace. Do not edit directly.\n",
            "## Active Decisions Index\n",
        ]

        if not decisions:
            content.append("No active decisions recorded yet.\n")
            return "\n".join(content)

        # Index table
        content.append("| Decision ID | Title | Confidence | Originating Agent | Updated At |")
        content.append("| :--- | :--- | :---: | :--- | :--- |")
        for dec in decisions:
            updated_str = dec.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content.append(f"| `{dec.id}` | {dec.title} | {dec.confidence:.2f} | {dec.originating_agent} | {updated_str} |")

        content.append("\n---\n")
        content.append("## Active Decisions Details\n")

        for dec in decisions:
            updated_str = dec.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content.append(f"### {dec.title} (`{dec.id}`)")
            content.append(f"- **Confidence:** {dec.confidence:.2f}")
            content.append(f"- **Originating Agent:** {dec.originating_agent}")
            content.append(f"- **Updated At:** {updated_str}")
            content.append("\n#### Rationale")
            content.append(dec.rationale.strip())

            content.append("\n#### Alternatives Considered")
            if dec.alternatives_considered:
                for alt in dec.alternatives_considered:
                    content.append(f"- {alt}")
            else:
                content.append("*None recorded.*")

            content.append("\n#### Affected Files")
            if dec.affected_files:
                for f in dec.affected_files:
                    content.append(f"- `{f}`")
            else:
                content.append("*None recorded.*")
            content.append("\n---\n")

        return "\n".join(content)

    def generate_memory_md(self, entries: List[MemoryEntry]) -> str:
        """Format active memory entries into a structured markdown string."""
        content = [
            "# Origin Memory Entries Mirror\n",
            "This file is an auto-generated mirror of the active memory entries in this workspace. Do not edit directly.\n",
        ]

        if not entries:
            content.append("No active memory entries recorded yet.\n")
            return "\n".join(content)

        # Group by category
        categories = ["architecture", "convention", "tech_stack", "glossary", "deployment"]
        for cat in categories:
            cat_entries = [e for e in entries if e.category == cat]
            if not cat_entries:
                continue

            content.append(f"## Category: {cat}")
            for entry in cat_entries:
                content.append(f"- **{entry.key}**: {entry.value}")
            content.append("")  # Empty line between categories

        return "\n".join(content)

    def generate_context_bundle(self, decisions: List[Decision], entries: List[MemoryEntry]) -> str:
        """Compile a single prompt-friendly context bundle string."""
        content = [
            "# Origin Project Context\n",
            "This is the active project memory and decision history. Use this context to align with architecture and decisions.\n",
            "## Workspace Information",
            f"- **Workspace Name:** {self.workspace_name}",
            f"- **Schema Version:** {self.schema_version}\n",
            "## Active Decisions\n",
        ]

        if not decisions:
            content.append("No active decisions recorded yet.\n")
        else:
            for dec in decisions:
                updated_str = dec.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                content.append(f"### {dec.title} (`{dec.id}`)")
                content.append(f"- **Confidence:** {dec.confidence:.2f} | **Agent:** {dec.originating_agent} | **Updated:** {updated_str}")
                content.append(f"- **Rationale:** {dec.rationale.strip()}")
                if dec.alternatives_considered:
                    alts_str = ", ".join(dec.alternatives_considered)
                    content.append(f"- **Alternatives Considered:** {alts_str}")
                if dec.affected_files:
                    files_str = ", ".join(f"`{f}`" for f in dec.affected_files)
                    content.append(f"- **Affected Files:** {files_str}")
                content.append("")

        content.append("## Active Project Memory\n")
        if not entries:
            content.append("No active memory entries recorded yet.\n")
        else:
            categories = ["architecture", "convention", "tech_stack", "glossary", "deployment"]
            for cat in categories:
                cat_entries = [e for e in entries if e.category == cat]
                if not cat_entries:
                    continue
                content.append(f"### {cat.replace('_', ' ').title()}")
                for entry in cat_entries:
                    content.append(f"- **{entry.key}**: {entry.value}")
                content.append("")

        return "\n".join(content)

    def refresh_all(self, repo: ArtifactRepository) -> None:
        """Query active entries and write all mirrors to the .origin folder.

        Args:
            repo: The repository instance to query from.
        """
        # Fetch active decisions and memories
        decisions = repo.list_decisions(status="active")
        memories = repo.list_memory()

        # Generate contents
        decisions_content = self.generate_decisions_md(decisions)
        memory_content = self.generate_memory_md(memories)
        context_content = self.generate_context_bundle(decisions, memories)

        # Write to files
        os.makedirs(self.origin_dir, exist_ok=True)

        with open(os.path.join(self.origin_dir, "decisions.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(decisions_content)

        with open(os.path.join(self.origin_dir, "memory.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(memory_content)

        with open(os.path.join(self.origin_dir, "ORIGIN.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(context_content)
