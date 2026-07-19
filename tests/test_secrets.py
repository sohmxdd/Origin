"""Unit tests for the domain-level secrets guard and input validation."""

import pytest
from datetime import datetime, timezone
from origin.domain.secrets import detect_secret_patterns
from origin.exceptions import SecretDetectedError
from origin.application.use_cases import add_decision, set_memory


def test_detect_secret_patterns():
    """Verify secrets detection on individual test strings."""
    # 1. AWS Access Key ID
    assert "AWS Access Key ID" in detect_secret_patterns("Here is my key: AKIAIOSFODNN7EXAMPLE")
    assert "AWS Access Key ID" in detect_secret_patterns("ASIAIOSFODNN7EXAMPLE")

    # 2. Private Key PEM Header
    assert "Private Key" in detect_secret_patterns("-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQD...")
    assert "Private Key" in detect_secret_patterns("-----BEGIN RSA PRIVATE KEY-----")

    # 3. Generic Secret Assignment
    assert "Generic Secret Assignment" in detect_secret_patterns("api_key = 'abcdefghijklmnopqrstuvwxyz'")
    assert "Generic Secret Assignment" in detect_secret_patterns('{"secret": "1234567890abcdef1234"}')
    assert "Generic Secret Assignment" in detect_secret_patterns("token: 1234567890abcdef1234")

    # 4. High-Entropy Long String
    assert "High Entropy Long String (Potential Secret)" in detect_secret_patterns("a4f8b92d6e3c5a1f7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f")

    # 5. Descriptive Words (False Positives check)
    assert len(detect_secret_patterns("The team discussed the security token protocol.")) == 0
    assert len(detect_secret_patterns("Please do not share the API key keyholder list.")) == 0
    assert len(detect_secret_patterns("Reset the password on Monday.")) == 0

    # 6. Exclusions
    # URL exclusion
    assert len(detect_secret_patterns("Visit https://github.com/sohmxdd/Origin/commit/4eb6730a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e")) == 0
    # Git SHA exclusion
    assert len(detect_secret_patterns("Commit 4eb6730a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e has been merged.")) == 0
    # Origin ULID exclusions (dec_, mem_, evt_ followed by 26-char base32 ULID)
    assert len(detect_secret_patterns("This decision supersedes dec_01KXBTA5DD6A9YQ91HGW762P9E successfully.")) == 0
    assert len(detect_secret_patterns("Check mem_01KXBTA5DD6A9YQ91HGW762P9E for context.")) == 0
    assert len(detect_secret_patterns("Associated with evt_01KXBTA5DD6A9YQ91HGW762P9E timeline event.")) == 0
    # Concatenated English text check
    assert len(detect_secret_patterns("thisisareallylongstringofcharacterswithoutanyspaces")) == 0


def test_use_cases_block_secrets(tmp_path):
    """Verify that use case actions block credential writes and raise SecretDetectedError."""
    workspace_root = str(tmp_path)
    from origin.application.use_cases import init_workspace
    init_workspace(workspace_root, "SecuredWS", with_hooks=False)

    # 1. Block decision add containing AWS Access Key
    with pytest.raises(SecretDetectedError) as exc_info:
        add_decision(
            workspace_root=workspace_root,
            title="Safe Title",
            rationale="AWS Key: AKIAIOSFODNN7EXAMPLE",
            alternatives_considered=[],
            affected_files=[],
            confidence=1.0,
            originating_agent="human",
        )
    assert "appears to contain a credential pattern (AWS Access Key ID)" in str(exc_info.value)

    # 2. Block memory set containing a private key
    with pytest.raises(SecretDetectedError) as exc_info:
        set_memory(
            workspace_root=workspace_root,
            category="tech_stack",
            key="ssl_key",
            value="-----BEGIN PRIVATE KEY-----",
            originating_agent="human",
        )
    assert "appears to contain a credential pattern (Private Key)" in str(exc_info.value)

    # 3. Block decision add containing generic secret assignment
    with pytest.raises(SecretDetectedError) as exc_info:
        add_decision(
            workspace_root=workspace_root,
            title="Safe Title",
            rationale="No secret here",
            alternatives_considered=["api_key = 'abcdefghijklmnopqrstuvwxyz'"],
            affected_files=[],
            confidence=1.0,
            originating_agent="human",
        )
    assert "appears to contain a credential pattern (Generic Secret Assignment)" in str(exc_info.value)
