"""Shared visual theme constants, status glyphs, and styling helpers.

Provides a unified status mapping across CLI, TUI, and HTML presentation layers.
"""

from typing import Dict, Any

# Standardized Status Glyphs
GLYPH_ACTIVE = "●"
GLYPH_PROPOSED = "◌"
GLYPH_SUPERSEDED = "↺"
GLYPH_REJECTED = "✕"

# Status Labels
LABEL_ACTIVE = "ACTIVE"
LABEL_PROPOSED = "PROPOSED"
LABEL_SUPERSEDED = "SUPERSEDED"
LABEL_REJECTED = "REJECTED"

# Hex Colors
COLOR_ACTIVE = "#10b981"      # Emerald Green
COLOR_PROPOSED = "#f59e0b"    # Amber Yellow
COLOR_SUPERSEDED = "#6b7280"  # Gray
COLOR_REJECTED = "#ef4444"    # Red

STATUS_THEME_MAP: Dict[str, Dict[str, str]] = {
    "active": {
        "label": LABEL_ACTIVE,
        "glyph": GLYPH_ACTIVE,
        "color": COLOR_ACTIVE,
        "rich_style": "bold green",
    },
    "proposed": {
        "label": LABEL_PROPOSED,
        "glyph": GLYPH_PROPOSED,
        "color": COLOR_PROPOSED,
        "rich_style": "bold yellow",
    },
    "superseded": {
        "label": LABEL_SUPERSEDED,
        "glyph": GLYPH_SUPERSEDED,
        "color": COLOR_SUPERSEDED,
        "rich_style": "dim gray",
    },
    "rejected": {
        "label": LABEL_REJECTED,
        "glyph": GLYPH_REJECTED,
        "color": COLOR_REJECTED,
        "rich_style": "bold red",
    },
}


def get_status_info(status: str) -> Dict[str, str]:
    """Return theme metadata (label, glyph, hex color, rich style) for a status string."""
    key = status.lower()
    return STATUS_THEME_MAP.get(
        key,
        {
            "label": status.upper(),
            "glyph": "•",
            "color": "#9ca3af",
            "rich_style": "white",
        },
    )
