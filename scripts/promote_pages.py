#!/usr/bin/env python3
"""
promote_pages.py — Promote page status based on content maturity criteria.

Status lifecycle: seed → developing → mature → evergreen

Promotion rules:
  - seed → developing: page has sources (≥1) OR body has ≥30 words
  - developing → mature: page has ≥3 sources AND body has ≥40 words AND ≥3 inline wikilinks
  - mature → evergreen: page hasn't been modified in 30+ days AND status is mature

Usage:
    python scripts/promote_pages.py <wiki-root> [--dry-run] [--verbose]

Exit codes:
    0 — success
    1 — error
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from merge_frontmatter import parse_frontmatter, _extract_existing_list_items


def count_words(text: str) -> int:
    """Count words in mixed Chinese/English text."""
    hanzi = len(re.findall(r'[一-鿿]', text))
    remainder = re.sub(r'[一-鿿]', ' ', text)
    ascii_words = len([w for w in remainder.split() if len(w) > 1])
    return hanzi + ascii_words


def count_inline_wikilinks(body: str) -> int:
    """Count inline wikilinks in body, excluding Related Pages/Sources sections."""
    # Strip sections that shouldn't count
    clean = re.sub(
        r"## (Related Pages|Sources|来源|Open Questions).*?(?=## |$)",
        "", body, flags=re.DOTALL,
    )
    return len(re.findall(r"\[\[([^\]]+)\]\]", clean))


def promote_pages(wiki_root: Path, dry_run: bool = False, verbose: bool = False) -> dict:
    """Promote pages based on maturity criteria.

    Returns stats: {promoted_to_developing, promoted_to_mature, promoted_to_evergreen, skipped}
    """
    wiki_dir = wiki_root / "wiki"
    today = date.today()
    threshold_evergreen = today - timedelta(days=30)

    stats = {
        "promoted_to_developing": 0,
        "promoted_to_mature": 0,
        "promoted_to_evergreen": 0,
        "skipped": 0,
    }

    for subdir in ("concepts", "entities"):
        dir_path = wiki_dir / subdir
        if not dir_path.exists():
            continue

        for page_file in sorted(dir_path.glob("*.md")):
            text = page_file.read_text(encoding="utf-8")
            fm, body, raw_fm = parse_frontmatter(text)
            if fm is None:
                continue

            current_status = str(fm.get("status", "")).strip().strip('"').strip("'")
            if not current_status:
                current_status = "seed"

            # Extract metrics
            parts = text.split("---", 2)
            raw_fm_text = parts[1] if len(parts) >= 3 else ""
            source_items = _extract_existing_list_items(raw_fm_text, "sources")
            source_count = len(source_items)
            word_count = count_words(body)
            wikilink_count = count_inline_wikilinks(body)

            # Determine target status
            new_status = current_status
            reason = ""

            if current_status == "seed":
                if source_count >= 1:
                    new_status = "developing"
                    reason = f"has {source_count} source(s)"
                elif word_count >= 30:
                    new_status = "developing"
                    reason = f"has {word_count} words"

            if current_status == "developing" or (current_status == "seed" and new_status == "developing"):
                # Check if eligible for mature (only if already developing)
                if current_status == "developing" and source_count >= 3 and word_count >= 40 and wikilink_count >= 3:
                    new_status = "mature"
                    reason = f"{source_count} sources, {word_count} words, {wikilink_count} wikilinks"

            if current_status == "mature":
                # Check evergreen: 30+ days since last update
                updated_str = str(fm.get("updated", "")).strip().strip('"').strip("'")
                try:
                    updated_date = date.fromisoformat(updated_str)
                    if updated_date <= threshold_evergreen:
                        new_status = "evergreen"
                        reason = f"unchanged since {updated_str} ({(today - updated_date).days} days)"
                except (ValueError, TypeError):
                    pass

            if new_status == current_status:
                stats["skipped"] += 1
                continue

            if verbose:
                print(f"  {page_file.name}: {current_status} → {new_status} ({reason})")

            if dry_run:
                stats[f"promoted_to_{new_status}"] += 1
                continue

            # Apply promotion
            raw_fm = re.sub(
                r"^status:\s*.*$",
                f"status: {new_status}",
                raw_fm,
                count=1,
                flags=re.MULTILINE,
            )
            # Only update date for evergreen (preserve real change date for others)
            if new_status == "evergreen":
                raw_fm = re.sub(
                    r"^updated:\s*.*$",
                    f"updated: {today.isoformat()}",
                    raw_fm,
                    count=1,
                    flags=re.MULTILINE,
                )

            result = "---" + raw_fm + "---" + body
            page_file.write_text(result, encoding="utf-8")
            stats[f"promoted_to_{new_status}"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote page status based on content maturity criteria."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show each promotion decision")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.exists():
        print(f"ERROR: {wiki_root} not found", file=sys.stderr)
        return 1

    print(f"Scanning pages in {wiki_root}...")
    stats = promote_pages(wiki_root, dry_run=args.dry_run, verbose=args.verbose)

    print(f"\nResults:")
    print(f"  seed → developing: {stats['promoted_to_developing']}")
    print(f"  developing → mature: {stats['promoted_to_mature']}")
    print(f"  mature → evergreen: {stats['promoted_to_evergreen']}")
    print(f"  Unchanged: {stats['skipped']}")
    if args.dry_run:
        print("  (dry-run: no files written)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
