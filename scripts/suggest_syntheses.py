#!/usr/bin/env python3
"""
suggest_syntheses.py — Identify cross-source analysis opportunities.

Scans the wiki for concepts/entities that are referenced by 3+ source pages
and suggests synthesis pages for them. Also identifies tag clusters where
3+ source pages share the same tag combination.

Usage:
    python scripts/suggest_syntheses.py <wiki-root> [--min-sources 3] [--format json|markdown]

Exit codes:
    0 — success
    1 — error
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from merge_frontmatter import parse_frontmatter, _extract_existing_list_items


def load_existing_syntheses(wiki_dir: Path) -> set[str]:
    """Return stems of existing synthesis pages to avoid duplicates."""
    syn_dir = wiki_dir / "syntheses"
    if not syn_dir.exists():
        return set()
    return {p.stem for p in syn_dir.glob("*.md")}


def build_concept_source_map(wiki_dir: Path) -> dict[str, dict]:
    """Build mapping: concept/entity stem → {sources: [stems], title, tags, type}.

    Uses the sources field (populated by backfill or cascade-update).
    """
    result: dict[str, dict] = {}
    for subdir in ("concepts", "entities"):
        dir_path = wiki_dir / subdir
        if not dir_path.exists():
            continue
        for page_file in sorted(dir_path.glob("*.md")):
            text = page_file.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            raw_fm = parts[1]
            fm, _, _ = parse_frontmatter(text)
            if fm is None:
                continue

            source_items = _extract_existing_list_items(raw_fm, "sources")
            # Extract stems from [[source-stem]] format
            source_stems = []
            for item in source_items:
                m = re.search(r"\[\[([^\]]+)\]\]", item)
                if m:
                    source_stems.append(m.group(1).strip())

            if not source_stems:
                continue

            # Extract tags
            tag_items = _extract_existing_list_items(raw_fm, "sources")  # placeholder
            tags_val = fm.get("tags", "")
            if isinstance(tags_val, str) and tags_val.startswith("["):
                tags_val = tags_val.strip("[]").strip()
            tags = []
            if isinstance(tags_val, list):
                tags = [str(t).strip().strip('"').strip("'") for t in tags_val]
            elif isinstance(tags_val, str) and tags_val:
                tags = [t.strip().strip('"').strip("'") for t in tags_val.split(",")]

            result[page_file.stem] = {
                "sources": source_stems,
                "source_count": len(source_stems),
                "title": str(fm.get("title", page_file.stem)).strip('"').strip("'"),
                "tags": [t for t in tags if t],
                "type": subdir.rstrip("s"),  # "concept" or "entitie" → fix below
                "page_path": str(page_file.relative_to(wiki_dir.parent)),
            }
            result[page_file.stem]["type"] = "concept" if subdir == "concepts" else "entity"

    return result


def find_synthesis_candidates(
    concept_map: dict[str, dict],
    existing_syntheses: set[str],
    min_sources: int = 3,
) -> list[dict]:
    """Find concepts/entities referenced by min_sources+ source pages.

    Returns sorted by source_count descending.
    Skips concepts that already have a synthesis page.
    """
    candidates = []
    for stem, info in concept_map.items():
        if info["source_count"] < min_sources:
            continue
        # Skip if a synthesis already covers this topic
        slug_lower = stem.lower()
        if any(slug_lower in s.lower() or s.lower() in slug_lower for s in existing_syntheses):
            continue

        candidates.append({
            "stem": stem,
            "title": info["title"],
            "source_count": info["source_count"],
            "sources": info["sources"],
            "tags": info["tags"],
            "type": info["type"],
            "suggested_slug": f"{stem}-综合分析",
        })

    candidates.sort(key=lambda x: x["source_count"], reverse=True)
    return candidates


def find_tag_clusters(
    wiki_dir: Path,
    concept_map: dict[str, dict],
    min_sources: int = 3,
) -> list[dict]:
    """Find tag combinations shared by 3+ source pages.

    Returns clusters of source pages that share tags, suggesting
    cross-source analyses by topic area.
    """
    sources_dir = wiki_dir / "sources"
    if not sources_dir.exists():
        return []

    # Build: source stem → tags
    source_tags: dict[str, list[str]] = {}
    for sf in sources_dir.glob("*.md"):
        text = sf.read_text(encoding="utf-8")
        fm, _, _ = parse_frontmatter(text)
        if fm is None:
            continue
        tags_val = fm.get("tags", "")
        if isinstance(tags_val, str) and tags_val.startswith("["):
            tags_val = tags_val.strip("[]").strip()
        tags = []
        if isinstance(tags_val, list):
            tags = [str(t).strip().strip('"').strip("'") for t in tags_val]
        elif isinstance(tags_val, str) and tags_val:
            tags = [t.strip().strip('"').strip("'") for t in tags_val.split(",")]
        tags = [t for t in tags if t]
        if tags:
            source_tags[sf.stem] = tags

    # Group by tag
    tag_to_sources: dict[str, list[str]] = defaultdict(list)
    for stem, tags in source_tags.items():
        for tag in tags:
            tag_to_sources[tag].append(stem)

    # Find tags with 3+ sources that don't already have a concept page
    existing_stems = set(concept_map.keys())
    clusters = []
    for tag, sources in sorted(tag_to_sources.items(), key=lambda x: -len(x[1])):
        if len(sources) < min_sources:
            continue
        if tag in existing_stems:
            continue  # Already has a concept page

        clusters.append({
            "tag": tag,
            "source_count": len(sources),
            "sources": sources,
        })

    return clusters


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Suggest synthesis pages based on cross-source analysis opportunities."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--min-sources", type=int, default=3,
                        help="Minimum source count to suggest a synthesis (default: 3)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--tag-clusters", action="store_true",
                        help="Also suggest tag-based clusters (slower)")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.exists():
        print(f"ERROR: {wiki_root} not found", file=sys.stderr)
        return 1

    wiki_dir = wiki_root / "wiki"

    existing = load_existing_syntheses(wiki_dir)
    concept_map = build_concept_source_map(wiki_dir)

    candidates = find_synthesis_candidates(concept_map, existing, args.min_sources)

    if args.format == "json":
        output = {"candidates": candidates}
        if args.tag_clusters:
            output["tag_clusters"] = find_tag_clusters(wiki_dir, concept_map, args.min_sources)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    # Markdown output
    print(f"# Synthesis Suggestions (min {args.min_sources} sources)")
    print(f"\nExisting synthesis pages: {len(existing)}")
    print(f"Candidates found: {len(candidates)}\n")

    if not candidates:
        print("No candidates found. Try lowering --min-sources.")
        return 0

    # Group by rough category
    for i, c in enumerate(candidates[:50], 1):
        print(f"## {i}. {c['title']} ({c['source_count']} sources)")
        print(f"- Type: {c['type']}")
        print(f"- Slug: `{c['suggested_slug']}`")
        print(f"- Tags: {', '.join(c['tags'][:5])}")
        print(f"- Sources: {', '.join(f'[[{s}]]' for s in c['sources'][:5])}"
              + (f" +{c['source_count']-5} more" if c['source_count'] > 5 else ""))
        print()

    if args.tag_clusters:
        print("\n---\n\n# Tag Cluster Suggestions\n")
        clusters = find_tag_clusters(wiki_dir, concept_map, args.min_sources)
        for cl in clusters[:20]:
            print(f"- **{cl['tag']}** ({cl['source_count']} sources)")

    print(f"\nTotal: {len(candidates)} candidates, showing top {min(50, len(candidates))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
