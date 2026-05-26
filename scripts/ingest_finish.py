#!/usr/bin/env python3
"""
ingest_finish.py — Write ingest log entry and git commit.

Automates the mechanical post-ingest steps (log writing, git commit)
that would otherwise require multiple LLM API roundtrips.

Usage:
    # Auto-detect created/updated from git diff (recommended):
    python3 ingest_finish.py <wiki-root> \\
      --title "Article Title" \\
      --source "raw/articles/xxx.md"

    # Or specify manually:
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


def detect_changes(wiki_root: Path) -> tuple[str, str]:
    """Auto-detect created and updated files from git status.

    Returns (created_csv, updated_csv) — comma-separated relative paths.
    Uses git status --porcelain to capture both tracked and untracked files.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(wiki_root),
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return "", ""

    created = []
    updated = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # porcelain format: XY filename
        # X = index status, Y = worktree status
        # ?? = untracked (new), A = added to index, M = modified
        xy = line[:2]
        path = line[3:].strip()
        # Handle renamed: "R  old -> new"
        if " -> " in path:
            path = path.split(" -> ")[1]
        # Only track wiki/ and log/ changes
        if not path.startswith(("wiki/", "log/")):
            continue
        if xy[0] in ("A", "?") or xy[1] == "?":
            created.append(path)
        elif xy[0] == "R":
            created.append(path)
        elif "M" in xy:
            updated.append(path)

    return ",".join(created), ",".join(updated)


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
    parser.add_argument("--created", default=None, help="Comma-separated paths of created wiki pages (auto-detected if omitted)")
    parser.add_argument("--updated", default=None, help="Comma-separated paths of updated wiki pages (auto-detected if omitted)")
    parser.add_argument("--notes", default=None, help="Notes to include in log entry")
    parser.add_argument("--no-commit", action="store_true", help="Write log only, skip git commit")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    today = date.today().isoformat()

    # Auto-detect created/updated if not provided
    created = args.created
    updated = args.updated
    if created is None or updated is None:
        auto_created, auto_updated = detect_changes(wiki_root)
        if created is None:
            created = auto_created
            if auto_created:
                print(f"Auto-detected created: {auto_created}")
        if updated is None:
            updated = auto_updated
            if auto_updated:
                print(f"Auto-detected updated: {auto_updated}")

    # Write log
    log_path = wiki_root / "log" / f"{today}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = format_log_entry(args.title, args.source, created, updated, args.notes)

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