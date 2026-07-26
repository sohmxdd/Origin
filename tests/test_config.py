"""Unit tests for workspace configuration management and InvalidConfigError handling."""

import os
import pytest
from origin.exceptions import InvalidConfigError, OriginError
from origin.config import load_config, save_config, WorkspaceConfig
from origin.application.use_cases import init_workspace, get_config_value, set_config_value


def test_config_get_and_set_values(tmp_path) -> None:
    """Verify getting and setting config values with automatic type casting."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "ConfigTestWorkspace", with_hooks=False)

    # Read default token budget
    tb = get_config_value(workspace_root, "token_budget")
    assert tb == 4000

    # Set new token budget (integer type casting)
    new_tb = set_config_value(workspace_root, "token_budget", "8000")
    assert new_tb == 8000
    assert get_config_value(workspace_root, "token_budget") == 8000

    # Set workspace name
    new_name = set_config_value(workspace_root, "workspace_name", "UpdatedProject")
    assert new_name == "UpdatedProject"
    assert get_config_value(workspace_root, "workspace_name") == "UpdatedProject"

    # Test unknown key
    with pytest.raises(OriginError):
        get_config_value(workspace_root, "invalid_key")

    with pytest.raises(OriginError):
        set_config_value(workspace_root, "invalid_key", "val")

    # Test invalid integer casting
    with pytest.raises(OriginError):
        set_config_value(workspace_root, "token_budget", "not_a_number")


def test_malformed_config_yaml_raises_invalid_config_error(tmp_path) -> None:
    """Verify malformed or invalid YAML in config.yaml raises InvalidConfigError."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "MalformedConfigTest", with_hooks=False)
    config_path = os.path.join(workspace_root, ".origin", "config.yaml")

    # Corrupt config.yaml with invalid YAML syntax
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("workspace_name: [unclosed list\n  token_budget: invalid")

    with pytest.raises(InvalidConfigError):
        load_config(workspace_root)

    # Corrupt config.yaml with invalid field types
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("workspace_name: 12345\ntoken_budget: 'not_an_int'\n")

    with pytest.raises(InvalidConfigError):
        load_config(workspace_root)
