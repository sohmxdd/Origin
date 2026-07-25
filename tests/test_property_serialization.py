"""Property-based round-trip serialization tests using Hypothesis.

Tests that arbitrary valid Decision and MemoryEntry models serialize to YAML
and deserialize back to identical object models without data loss.
"""

from datetime import datetime, timezone
import yaml
from hypothesis import given, strategies as st, settings, HealthCheck

from origin.domain.models import Decision, MemoryEntry


# Custom Hypothesis strategies
st_text_clean = st.text(alphabet=st.characters(blacklist_categories=('Cs', 'Cc')), min_size=1, max_size=100)
st_status = st.sampled_from(["active", "proposed", "superseded", "rejected"])
st_category = st.sampled_from(["architecture", "convention", "tech_stack", "glossary", "deployment"])
st_confidence = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
st_file_list = st.lists(st_text_clean, min_size=0, max_size=5)


@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
@given(
    id_val=st_text_clean,
    title=st_text_clean,
    rationale=st_text_clean,
    status=st_status,
    confidence=st_confidence,
    affected_files=st_file_list,
    alternatives=st_file_list,
    agent=st_text_clean,
)
def test_decision_roundtrip_property(
    id_val: str,
    title: str,
    rationale: str,
    status: str,
    confidence: float,
    affected_files: list[str],
    alternatives: list[str],
    agent: str,
) -> None:
    """Property test verifying Decision model YAML round-trip integrity."""
    now = datetime.now(timezone.utc)
    original = Decision(
        id=id_val,
        title=title,
        rationale=rationale,
        status=status,
        confidence=confidence,
        affected_files=affected_files,
        alternatives_considered=alternatives,
        originating_agent=agent,
        created_at=now,
        updated_at=now,
    )

    # Serialize to YAML
    yaml_str = yaml.safe_dump(original.model_dump(mode="json"))

    # Deserialize from YAML
    deserialized_data = yaml.safe_load(yaml_str)
    reconstructed = Decision.model_validate(deserialized_data)

    assert reconstructed.id == original.id
    assert reconstructed.title == original.title
    assert reconstructed.rationale == original.rationale
    assert reconstructed.status == original.status
    assert abs(reconstructed.confidence - original.confidence) < 1e-5
    assert reconstructed.affected_files == original.affected_files
    assert reconstructed.alternatives_considered == original.alternatives_considered
    assert reconstructed.originating_agent == original.originating_agent


@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
@given(
    id_val=st_text_clean,
    category=st_category,
    key=st_text_clean,
    value=st_text_clean,
    agent=st_text_clean,
)
def test_memory_entry_roundtrip_property(
    id_val: str,
    category: str,
    key: str,
    value: str,
    agent: str,
) -> None:
    """Property test verifying MemoryEntry model YAML round-trip integrity."""
    now = datetime.now(timezone.utc)
    original = MemoryEntry(
        id=id_val,
        category=category,
        key=key,
        value=value,
        originating_agent=agent,
        created_at=now,
        updated_at=now,
    )

    yaml_str = yaml.safe_dump(original.model_dump(mode="json"))
    deserialized_data = yaml.safe_load(yaml_str)
    reconstructed = MemoryEntry.model_validate(deserialized_data)

    assert reconstructed.id == original.id
    assert reconstructed.category == original.category
    assert reconstructed.key == original.key
    assert reconstructed.value == original.value
    assert reconstructed.originating_agent == original.originating_agent
