#!/usr/bin/env python3
"""
ingest_finish.py — Write ingest log entry and git commit.

Automates the mechanical post-ingest steps (log writing, git commit)
that would otherwise require multiple LLM API roundtrips.

Usage:
    python3 ingest_finish.py <wiki-root> \\
      --title "Article Title" \\
      --source "raw/articles/xxx.md" \\
      --created "wiki/sources/a.md,wiki/concepts/b.md" \\
      --updated "wiki/entities/c.md" \\
      [--notes "Key concepts notes"] \\
      [--no-commit]

Exit codes:
    0 — success
    1 — error
"""

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


def format_log_entry(
    title: str,
    source: str,
    created: str | None,
    updated: str | None,
    notes: str | None,
) -> str:
    """Format a single ingest log entry.

    Returns a string ready to append to log/{date}.md.
    """
    lines = [f"## Ingest: {title}", ""]

    lines.append(f"- Source: `{source}`")

    if created:
        for page in created.split(","):
            page = page.strip()
            if page:
                lines.append(f"- Created: `{page}`")

    if updated:
        for page in updated.split(","):
            page = page.strip()
            if page:
                lines.append(f"- Updated: `{page}`")

    if notes:
        lines.append(f"- {notes}")

    lines.append("")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write ingest log entry and git commit."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--title", required=True, help="Title of the ingested article")
    parser.add_argument("--source", required=True, help="Raw source file path (relative to wiki-root)")
    parser.add_argument("--created", default=None, help="Comma-separated paths of created wiki pages")
    parser.add_argument("--updated", default=None, help="Comma-separated paths of updated wiki pages")
    parser.add_argument("--notes", default=None, help="Notes to include in log entry")
    parser.add_argument("--no-commit", action="store_true", help="Write log only, skip git commit")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    today = date.today().isoformat()

    # Write log
    log_path = wiki_root / "log" / f"{today}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = format_log_entry(args.title, args.source, args.created, args.updated, args.notes)

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        # Ensure blank line separation between entries
        separator = "" if existing.endswith("\n\n") else "\n"
        log_path.write_text(existing + separator + entry, encoding="utf-8")
    else:
        log_path.write_text(f"# {today}\n\n{entry}", encoding="utf-8")

    print(f"Log entry written to {log_path}")

    # Git commit
    if not args.no_commit:
        subprocess.run(["git", "add", "-A"], cwd=str(wiki_root), check=True)
        subprocess.run(["git", "commit", "-m", f"ingest: {args.title}"], cwd=str(wiki_root), check=True)
        print(f"Committed: ingest: {args.title}")

    return 0


if __name__ == "__main__":
    sys.exit(main())