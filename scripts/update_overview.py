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
from datetime import date
from pathlib import Path

# Ensure stdout/stderr handle Unicode on Windows (GBK console default)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from slug_utils import slugify

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


def check_dead_wikilinks(content: str, wiki_dir: Path) -> list[str]:
    """Check wikilinks in content against existing wiki pages.

    Returns a list of dead link targets (links with no matching page file).
    Prints warnings to stderr but does not modify content.
    """
    # Collect all existing page filenames (stems) across wiki subdirectories
    existing_pages: set[str] = set()
    if wiki_dir.exists():
        for p in wiki_dir.rglob("*.md"):
            existing_pages.add(p.stem)

    # Extract all wikilink targets
    targets = re.findall(r"\[\[([^\]]+)\]\]", content)
    dead = []
    for target in targets:
        # Handle alias syntax: [[slug|Display]] → use slug part only
        slug = target.split("|")[0].strip() if "|" in target else target.strip()
        if slug not in existing_pages:
            dead.append(slug)

    if dead:
        print(f"  ⚠️  Dead wikilinks in overview content: {dead}", file=sys.stderr)

    return dead


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert a new ### section into wiki/overview.md."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--content", required=True,
                        help="Section content to insert (heading + body)")
    parser.add_argument("--topic", type=str, default=None,
                        help="Write to a topic overview file in wiki/overviews/ instead of overview.md")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()

    if args.topic:
        overviews_dir = wiki_root / "wiki" / "overviews"
        overviews_dir.mkdir(parents=True, exist_ok=True)
        overview_path = overviews_dir / f"{args.topic}-关键发现.md"
        if not overview_path.exists():
            # Create the topic file with minimal frontmatter
            today = date.today().isoformat()
            stub = (
                '---\n'
                f'title: "{args.topic}：关键发现"\n'
                f'title_zh: "{args.topic}：关键发现"\n'
                "type: overview\n"
                f'summary: ""\n'
                "tags: []\n"
                "sources: []\n"
                "origin: agent-compiled\n"
                "status: developing\n"
                f"created: {today}\n"
                f"updated: {today}\n"
                'review_by: ""\n'
                "---\n\n"
                f"# {args.topic}：关键发现\n\n"
                "## Notes / 笔记\n\n"
                "<!-- human:start -->\n<!-- human:end -->\n"
            )
            overview_path.write_text(stub, encoding="utf-8")
            print(f"Created: {overview_path}")
    else:
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

    # Warn about dead wikilinks (non-blocking)
    wiki_dir = wiki_root / "wiki"
    check_dead_wikilinks(section_text, wiki_dir)

    overview_path.write_text(content, encoding="utf-8")
    print(f"Updated: {overview_path}")

    # Warn if overview.md is getting too large
    line_count = content.count("\n") + 1
    size_kb = len(content.encode("utf-8")) // 1024
    if line_count > 2000 or size_kb > 300:
        print(
            f"  ⚠️  overview.md is large ({line_count} lines, {size_kb}KB). "
            "Consider consolidating older sections into topic-specific syntheses.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
