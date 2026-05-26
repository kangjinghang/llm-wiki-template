#!/usr/bin/env python3
"""
update_overview.py — Insert a new ### section into wiki/overview.md.

Replaces the LLM Edit+Read+Grep cycle for updating overview.md with
a single Bash call. Finds the ## 开放问题 (or ## Notes) marker and
inserts content before it.

Usage:
    python3 update_overview.py <wiki-root> --content "### Title\\n\\nParagraph..."

Exit codes:
    0 — success
    1 — error
"""

import argparse
import re
import sys
from pathlib import Path

# Markers to search for, in priority order
_INSERT_BEFORE_MARKERS = [
    "\n## 开放问题",
    "\n## Open Questions",
    "\n## Notes / 笔记",
    "\n## Notes",
]


def _extract_heading(content_text: str) -> str | None:
    """Extract the ### heading from content text."""
    m = re.search(r"^###\s+(.+)$", content_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _heading_exists(body: str, heading: str) -> bool:
    """Check if a ### heading already exists in the body."""
    return bool(re.search(rf"^###\s+{re.escape(heading)}\s*$", body, re.MULTILINE))


def insert_section(content: str, new_section: str) -> tuple[str, bool]:
    """Insert new_section before the first matching marker.

    Returns (updated_content, changed).
    """
    heading = _extract_heading(new_section)

    # Split frontmatter from body
    body_start = 0
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            body_start = content.find("---", content.find("---") + 3) + 3

    body = content[body_start:]

    # Dedup by heading
    if heading and _heading_exists(body, heading):
        print(f"  SKIP: section '### {heading}' already exists in overview.md", file=sys.stderr)
        return content, False

    # Find insert point
    for marker in _INSERT_BEFORE_MARKERS:
        idx = content.find(marker)
        if idx != -1:
            insert_text = f"\n{new_section}\n"
            content = content[:idx] + insert_text + content[idx:]
            return content, True

    # No marker found — append at end
    content = content.rstrip("\n") + f"\n\n{new_section}\n"
    return content, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert a new ### section into wiki/overview.md."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--content", required=True,
                        help="Section content to insert (heading + body)")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    overview_path = wiki_root / "wiki" / "overview.md"

    if not overview_path.exists():
        print(f"ERROR: {overview_path} not found", file=sys.stderr)
        return 1

    # Unescape literal \n in --content (shell escaping)
    section_text = args.content.replace("\\n", "\n")

    content = overview_path.read_text(encoding="utf-8")
    content, changed = insert_section(content, section_text)

    if not changed:
        print("No changes needed: wiki/overview.md")
        return 0

    overview_path.write_text(content, encoding="utf-8")
    print(f"Updated: {overview_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
