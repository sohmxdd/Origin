"""Configuration manager for Origin workspaces.

Handles loading, validating, and saving config.yaml files.
"""

import os
import yaml
from typing import List
from pydantic import BaseModel, Field

from origin.exceptions import WorkspaceNotInitializedError


class WorkspaceConfig(BaseModel):
    """Pydantic model representing workspace config.yaml."""

    workspace_name: str = Field(description="Name of the workspace project")
    schema_version: str = Field(default="2.0", description="Schema version of the Origin metadata")
    agent_allowlist: List[str] = Field(
        default_factory=lambda: ["claude-code", "codex-cli", "human"],
        description="Allowlist of agents that can write artifacts",
    )
    token_budget: int = Field(default=4000, description="Token budget for context bundling")


def get_origin_dir(workspace_root: str) -> str:
    """Get the path to the .origin directory in the workspace root."""
    return os.path.join(os.path.abspath(workspace_root), ".origin")


def load_config(workspace_root: str) -> WorkspaceConfig:
    """Load the workspace configuration from .origin/config.yaml.

    Args:
        workspace_root: The root folder of the project.

    Returns:
        The loaded WorkspaceConfig.

    Raises:
        WorkspaceNotInitializedError: If the .origin folder or config.yaml doesn't exist.
    """
    origin_dir = get_origin_dir(workspace_root)
    config_path = os.path.join(origin_dir, "config.yaml")

    if not os.path.isdir(origin_dir) or not os.path.exists(config_path):
        raise WorkspaceNotInitializedError(
            f"Origin workspace is not initialized. Run 'origin init' first."
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return WorkspaceConfig.model_validate(data)
    except Exception as e:
        raise WorkspaceNotInitializedError(f"Failed to load workspace config.yaml: {e}")


def save_config(workspace_root: str, config: WorkspaceConfig) -> None:
    """Save the workspace configuration to .origin/config.yaml.

    Args:
        workspace_root: The root folder of the project.
        config: The WorkspaceConfig instance to save.
    """
    origin_dir = get_origin_dir(workspace_root)
    os.makedirs(origin_dir, exist_ok=True)
    config_path = os.path.join(origin_dir, "config.yaml")

    with open(config_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)
