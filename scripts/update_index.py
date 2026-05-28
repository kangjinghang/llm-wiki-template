#!/usr/bin/env python3
"""
update_index.py — Append entries to the correct section of wiki/index.md.

Replaces multiple LLM Edit calls for adding sources/concepts/entities/syntheses
to index.md with a single Bash call.

Usage:
    python3 update_index.py <wiki-root> \
      --source "[[page]] — description" \
      --concept "[[page]] — description" \
      --entity "[[page]] — description" \
      --synthesis "[[page]] — description"

Flags can be repeated. Entries are deduplicated by [[wikilink]] target.

Exit codes:
    0 — success
    1 — error
"""

import argparse
import re
import sys
from pathlib import Path

# Map flag names to index.md section headings
_SECTION_MAP = {
    "source": "## Sources",
    "concept": "## Concepts",
    "entity": "## Entities",
    "synthesis": "## Syntheses",
}


def _extract_wikilink(entry: str) -> str | None:
    """Extract the first [[...]] target from an entry line."""
    m = re.search(r"\[\[([^\]]+)\]\]", entry)
    return m.group(1) if m else None


def _find_section_range(content: str, section_heading: str) -> tuple[int, int] | None:
    """Find the start and end positions of a ## section.

    Returns (start_of_heading, start_of_next_##_heading) or None.
    """
    idx = content.find(section_heading)
    if idx == -1:
        return None
    # Find the next ## heading after this one
    next_h2 = content.find("\n## ", idx + len(section_heading))
    if next_h2 == -1:
        return idx, len(content)
    return idx, next_h2


def _entries_in_section(content: str, section_heading: str) -> set[str]:
    """Extract all [[wikilink]] targets already present in a section."""
    rng = _find_section_range(content, section_heading)
    if rng is None:
        return set()
    section_text = content[rng[0]:rng[1]]
    return set(re.findall(r"\[\[([^\]]+)\]\]", section_text))


def _find_or_create_section(content: str, section_heading: str) -> tuple[str, int]:
    """Ensure a section exists in content, creating it if necessary.

    Returns (possibly_modified_content, section_start_offset).
    """
    rng = _find_section_range(content, section_heading)
    if rng is not None:
        return content, rng[1]  # return end-of-section offset for appending

    # Section not found — create it before ## Open Questions or ## Active Threads or EOF
    for marker in ["\n## Open Questions", "\n## Active Threads", "\n## Syntheses"]:
        idx = content.find(marker)
        if idx != -1:
            new_section = f"\n{section_heading}\n\n"
            content = content[:idx] + new_section + content[idx:]
            rng = _find_section_range(content, section_heading)
            return content, rng[1]

    # Fallback: append at end
    content = content.rstrip("\n") + f"\n\n{section_heading}\n\n"
    rng = _find_section_range(content, section_heading)
    return content, rng[1]


def add_entries(content: str, section_name: str, entries: list[str]) -> str:
    """Add entries to the specified section, deduplicating by wikilink target.

    Returns the modified content.
    """
    section_heading = _SECTION_MAP[section_name]
    existing = _entries_in_section(content, section_heading)

    # Filter out duplicates
    to_add = []
    for entry in entries:
        target = _extract_wikilink(entry)
        if target and target in existing:
            print(f"  SKIP (duplicate): {target}", file=sys.stderr)
            continue
        to_add.append(entry)
        if target:
            existing.add(target)

    if not to_add:
        return content

    content, insert_offset = _find_or_create_section(content, section_heading)

    # Find the last non-empty line before insert_offset to append after it
    before = content[:insert_offset].rstrip("\n")
    after = content[insert_offset:]

    lines_to_add = "".join(f"\n- {entry}" for entry in to_add)
    content = before + lines_to_add + "\n" + after

    return content


def _strip_description(entry: str) -> str:
    """Strip description from an entry, keeping only [[wikilink]]."""
    m = re.search(r"\[\[[^\]]+\]\]", entry)
    return m.group(0) if m else f"[[{entry}]]"


def _generate_summary(index_content: str) -> str:
    """Generate compact index-summary.md content from index.md."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in index_content.splitlines():
        h = re.match(r"^## (.+)$", line)
        if h:
            current = h.group(1).strip()
            if current not in sections:
                sections[current] = []
        elif current:
            for name in re.findall(r"\[\[([^\]]+)\]\]", line):
                sections[current].append(name)

    # Extract title from first line
    title_match = re.match(r"^#\s+(.+)$", index_content.splitlines()[0]) if index_content else None
    title = title_match.group(1).replace("Index", "Index Summary") if title_match else "Index Summary"

    parts = [f"# {title}", ""]
    for cat in ("Sources", "Concepts", "Entities", "Syntheses"):
        names = sections.get(cat)
        if names:
            parts.append(f"## {cat}")
            for n in names:
                parts.append(f"- [[{n}]]")
            parts.append("")

    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append entries to wiki/index.md sections."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--source", action="append", default=[],
                        help="Source entry, e.g. '[[page]] — description'")
    parser.add_argument("--concept", action="append", default=[],
                        help="Concept entry")
    parser.add_argument("--entity", action="append", default=[],
                        help="Entity entry")
    parser.add_argument("--synthesis", action="append", default=[],
                        help="Synthesis entry")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    index_path = wiki_root / "wiki" / "index.md"

    if not index_path.exists():
        print(f"ERROR: {index_path} not found", file=sys.stderr)
        return 1

    all_entries = args.source + args.concept + args.entity + args.synthesis
    if not all_entries:
        print("No entries to add (use --source/--concept/--entity/--synthesis)")
        return 0

    content = index_path.read_text(encoding="utf-8")
    changed = False

    for section_name in ["source", "concept", "entity", "synthesis"]:
        entries = getattr(args, section_name)
        if entries:
            before = content
            content = add_entries(content, section_name, entries)
            if content != before:
                changed = True
                print(f"  Added {len(entries)} entry/entries to {_SECTION_MAP[section_name]}")

    if not changed:
        print("No changes needed: wiki/index.md")
        return 0

    index_path.write_text(content, encoding="utf-8")
    print(f"Updated: {index_path}")

    # Regenerate index-summary.md from updated index.md
    summary_path = wiki_root / "wiki" / "index-summary.md"
    summary_content = _generate_summary(content)
    summary_path.write_text(summary_content, encoding="utf-8")
    print(f"Updated: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
