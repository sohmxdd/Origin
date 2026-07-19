"""Domain secrets validation utility for Origin.

Provides pure functions to detect credentials or secrets in free-text fields.
"""

import math
import re
from collections import Counter
from typing import List


def calculate_shannon_entropy(s: str) -> float:
    """Calculate the Shannon entropy of a string."""
    if not s:
        return 0.0
    entropy = 0.0
    len_s = len(s)
    counts = Counter(s)
    for count in counts.values():
        p = count / len_s
        entropy -= p * math.log2(p)
    return entropy


def detect_secret_patterns(text: str) -> List[str]:
    """Scan text for potential credential or API key patterns.

    Args:
        text: The free-text content to check.

    Returns:
        A list of matched pattern names (empty list if clean).
    """
    if not text:
        return []

    findings = []

    # 1. AWS Access Key ID Check
    aws_pattern = re.compile(r'\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b')
    if aws_pattern.search(text):
        findings.append("AWS Access Key ID")

    # 2. Private Key PEM Header Check
    private_key_pattern = re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')
    if private_key_pattern.search(text):
        findings.append("Private Key")

    # 3. Generic Secret/Token Assignment Pattern Check
    # api_key = "...", token: "..."
    assignment_pattern = re.compile(
        r'["\']?\b(?:api_?[kK]ey|secret_?[kK]ey|secret|token|password|passwd|auth_?token|client_?secret)\b["\']?\s*[:=]\s*["\'\s]?([a-zA-Z0-9_\-\.\~\+\/]{16,})["\'\s]?'
    )
    if assignment_pattern.search(text):
        findings.append("Generic Secret Assignment")

    # 4. High-Entropy Long String Check (Catch-all)
    # Split text by common separators to inspect individual tokens/words
    tokens = re.split(r'[\s\'\"`,;\(\)\[\]\{\}\<\>]+', text)
    for token in tokens:
        # We only inspect tokens with length >= 32 characters
        if len(token) < 32:
            continue

        # Exclusion 1: URLs
        if token.startswith(("http://", "https://")) or "://" in token:
            continue

        # Exclusion 2: Git SHAs (exactly 40 hexadecimal characters)
        if len(token) == 40 and re.match(r'^[0-9a-fA-F]{40}$', token):
            continue

        # Exclusion 3: Origin ULID Identifiers (dec_..., mem_..., evt_... followed by 26-char base32 ULID)
        # We match dec_, mem_, evt_ prefixes or pattern matching ID structure
        if token.startswith(("dec_", "mem_", "evt_")) or re.match(r'^(dec|mem|evt)_[A-Za-z0-9]{26}$', token):
            continue

        # Check if the token is strictly hexadecimal
        is_hex = bool(re.match(r'^[0-9a-fA-F]+$', token))
        if is_hex:
            findings.append("High Entropy Long String (Potential Secret)")
            break
        else:
            # Calculate Shannon entropy to filter out concatenated English text
            entropy = calculate_shannon_entropy(token)
            if entropy >= 4.3:
                findings.append("High Entropy Long String (Potential Secret)")
                break

    return findings
