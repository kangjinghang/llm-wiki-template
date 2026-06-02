"""slug_utils.py — Shared slug generation for wiki page filenames.

Provides two functions:
- slugify(title): Convert a title to a filesystem-friendly slug.
- derive_slug(raw_path): Derive a slug from a raw article filename.
"""

import re
from pathlib import Path


def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug.

    Keeps Chinese characters, ASCII letters/digits. Replaces other
    characters with '-', then collapses repeated separators.
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s一-鿿-]+", "-", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug or "untitled"


def derive_slug(raw_path: str) -> str:
    """Derive a URL-safe slug from the raw article filename.

    Strips [timestamp] prefix and .md extension, then normalizes
    through slugify for consistency with page filenames.
    """
    name = Path(raw_path).stem
    # Remove [YYYYMMDDHHMM] prefix
    name = re.sub(r"^\[\d+\]", "", name)
    return slugify(name)
