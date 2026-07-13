"""ULID utility module for generating sortable identifiers.

This module implements a dependency-free Crockford's Base32 ULID generator.
"""

import os
import time

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def encode_base32(num: int, length: int) -> str:
    """Encode an integer as a Crockford Base32 string of a specified length.

    Args:
        num: The integer to encode.
        length: The desired length of the returned string.

    Returns:
        The Base32-encoded string, left-padded with '0'.
    """
    chars = []
    temp = num
    for _ in range(length):
        temp, rem = divmod(temp, 32)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def generate_ulid() -> str:
    """Generate a 26-character Crockford Base32 ULID.

    The first 10 characters encode a 48-bit millisecond timestamp.
    The next 16 characters encode 80 bits of cryptographic randomness.

    Returns:
        A 26-character sortable ULID string.
    """
    # 48-bit timestamp in milliseconds
    timestamp = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    # 80-bit random value
    randomness = int.from_bytes(os.urandom(10), byteorder="big") & 0xFFFFFFFFFFFFFFFFFFFF
    return encode_base32(timestamp, 10) + encode_base32(randomness, 16)
