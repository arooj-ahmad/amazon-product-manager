# app/services/shopify/_helpers.py
# Shared helpers

import logging

logger = logging.getLogger(__name__)


def _slugify_key(name: str) -> str:
    """Field name → snake_case key."""
    return (
        name.lower()
        .strip()
        .replace(" ", "_")
        .replace("&", "and")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .strip("_")
        [:50]
    )