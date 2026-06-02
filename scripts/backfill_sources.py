#!/usr/bin/env python3
"""
backfill_sources.py — One-time backfill of empty sources fields on concept/entity pages.

Scans all source page bodies for [[wikilinks]] to concept/entity pages,
then reverse-infers which source pages each concept/entity came from
and fills the sources frontmatter field.

Usage:
    python scripts/backfill_sources.py <wiki-root> [--dry-run]

Exit codes:
    0 — success
    1 — error
"""

import re
import sys
from datetime import date
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from merge_frontmatter import parse_frontmatter, merge_array_field

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def _page_stems(directory: Path) -> set[str]:
    """Return the set of .md file stems in a directory."""
    if not directory.exists():
        return set()
    return {p.stem for p in directory.glob("*.md")}


def build_source_map(wiki_dir: Path) -> dict[str, list[str]]:
    """Build reverse mapping: concept/entity stem → [source page stems that link to it].

    Scans wiki/sources/*.md body text (not frontmatter) for wikilinks.
    Only includes targets that exist as concept or entity pages.
    Deduplicates per source page (a source linking the same concept twice counts once).
    """
    sources_dir = wiki_dir / "sources"
    concepts_dir = wiki_dir / "concepts"
    entities_dir = wiki_dir / "entities"

    # All valid concept/entity stems
    valid_targets = _page_stems(concepts_dir) | _page_stems(entities_dir)

    # Build reverse map
    reverse_map: dict[str, list[str]] = {}
    if not sources_dir.exists():
        return reverse_map

    for source_file in sorted(sources_dir.glob("*.md")):
        text = source_file.read_text(encoding="utf-8")
        # Split off frontmatter — only scan body
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
        else:
            body = text

        # Find unique wikilink targets in body
        seen_in_this_source: set[str] = set()
        for m in WIKILINK_RE.finditer(body):
            target = m.group(1).strip()
            if target in valid_targets and target not in seen_in_this_source:
                seen_in_this_source.add(target)
                reverse_map.setdefault(target, []).append(source_file.stem)

    return reverse_map


def backfill_sources(wiki_root: Path, dry_run: bool = False) -> dict[str, int]:
    """Backfill empty sources fields on concept/entity pages.

    Returns stats dict with keys: filled, skipped, promoted.
    """
    wiki_dir = wiki_root / "wiki"
    concepts_dir = wiki_dir / "concepts"
    entities_dir = wiki_dir / "entities"

    source_map = build_source_map(wiki_dir)

    stats = {"filled": 0, "skipped": 0, "promoted": 0}
    today = date.today().isoformat()

    # Process both concepts and entities
    target_dirs = [concepts_dir, entities_dir]
    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        is_concepts = target_dir.name == "concepts"

        for page_file in sorted(target_dir.glob("*.md")):
            stem = page_file.stem
            if stem not in source_map:
                # No source pages link to this — skip
                continue

            text = page_file.read_text(encoding="utf-8")
            fm, body, raw_fm = parse_frontmatter(text)
            if fm is None:
                continue

            # Check if sources is already populated
            # Use merge_frontmatter's extractor for reliable list parsing
            from merge_frontmatter import _extract_existing_list_items
            existing_items = _extract_existing_list_items(raw_fm, "sources")
            has_sources = len(existing_items) > 0

            if has_sources:
                stats["skipped"] += 1
                continue

            # Build new source links
            new_sources = [f"[[{s}]]" for s in source_map[stem]]
            if not new_sources:
                continue

            if dry_run:
                stats["filled"] += 1
                is_seed = fm.get("status", "").strip().strip('"').strip("'") == "seed"
                if is_seed:
                    stats["promoted"] += 1
                print(f"  [dry-run] Would fill {page_file.name}: {new_sources}")
                continue

            # Merge sources into frontmatter
            raw_fm = merge_array_field(raw_fm, "sources", new_sources)

            # Update date
            raw_fm = re.sub(
                r"^updated:\s*.*$",
                f"updated: {today}",
                raw_fm,
                count=1,
                flags=re.MULTILINE,
            )

            # Promote seed → developing
            if fm.get("status", "").strip().strip('"').strip("'") == "seed":
                raw_fm = re.sub(
                    r"^status:\s*.*$",
                    "status: developing",
                    raw_fm,
                    count=1,
                    flags=re.MULTILINE,
                )
                stats["promoted"] += 1

            result = "---" + raw_fm + "---" + body
            page_file.write_text(result, encoding="utf-8")
            stats["filled"] += 1
            print(f"  Filled: {page_file.name} ← {new_sources}")

    return stats


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill empty sources fields on concept/entity pages via wikilink reverse inference."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing files",
    )
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.exists():
        print(f"ERROR: {wiki_root} not found", file=sys.stderr)
        return 1

    print(f"Scanning source pages in {wiki_root}...")
    stats = backfill_sources(wiki_root, dry_run=args.dry_run)

    print(f"\nResults:")
    print(f"  Filled:   {stats['filled']} pages")
    print(f"  Skipped:  {stats['skipped']} pages (already have sources)")
    print(f"  Promoted: {stats['promoted']} pages (seed → developing)")
    if args.dry_run:
        print("  (dry-run: no files written)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
