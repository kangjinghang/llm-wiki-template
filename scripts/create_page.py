#!/usr/bin/env python3
"""
create_page.py — Create a wiki page with correct frontmatter from a template.

Usage:
    python3 create_page.py <wiki-root> <type> "<title>" [options]

Arguments:
    wiki-root    Path to the wiki root directory
    type         Page type: source, concept, entity, synthesis, comparison
    title        Page title

Options:
    --title-zh "中文标题"     Chinese title (optional)
    --tags "tag1,tag2"        Comma-separated tags (optional)
    --sources "path1,path2"   Comma-separated source paths (optional)
    --raw-path "path"         Raw source file path (source type only)
    --compute-hash            Compute SHA256 of raw_path file and add to frontmatter

Examples:
    python3 create_page.py . concept "Attention Mechanism" --title-zh "注意力机制" --tags "AI,Deep-Learning"
    python3 create_page.py . source "Transformer" --sources "raw/articles/attention-is-all-you-need.md"
    python3 create_page.py . entity "OpenAI" --tags "AI,Company"

Exit codes:
    0 — page created successfully
    1 — error (missing args, duplicate page, invalid type)
"""

import argparse
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

VALID_TYPES = {"source", "concept", "entity", "synthesis", "comparison"}


def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug.

    Keeps Chinese characters, ASCII letters/digits. Replaces other
    characters with '-', then collapses repeated separators.
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s\u4e00-\u9fff-]+", "-", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug or "untitled"


def load_template(template_dir: Path, page_type: str) -> str:
    """Load the template file for a given page type."""
    path = template_dir / f"{page_type}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def fill_template(
    template: str,
    title: str,
    title_zh: str | None,
    today: str,
    tags: list[str],
    sources: list[str],
    raw_path: str | None,
) -> str:
    """Fill template placeholders with actual values."""
    content = template

    # Replace {date} with today's date
    content = content.replace("{date}", today)
    # Replace {title} with actual title
    content = content.replace("{title}", title)

    # Fill frontmatter fields
    content = fill_fm_field(content, "title", f'"{title}"')
    content = fill_fm_field(content, "title_zh", f'"{title_zh}"' if title_zh else "")
    content = fill_fm_field(content, "summary", '""')
    if tags:
        tags_str = "[" + ", ".join(tags) + "]"
        content = fill_fm_field(content, "tags", tags_str)
    if sources:
        sources_str = "[" + ", ".join(sources) + "]"
        content = fill_fm_field(content, "sources", sources_str)
    if raw_path:
        content = fill_fm_field(content, "raw_path", f'"{raw_path}"')

    return content


def fill_fm_field(content: str, field: str, value: str) -> str:
    """Replace a frontmatter field value. Only matches inside the --- YAML block."""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    fm = parts[1]
    fm = re.sub(rf"(^{field}:\s*).*?$", rf"\g<1>{value}", fm, count=1, flags=re.MULTILINE)
    return "---" + fm + "---" + parts[2]


def type_to_dir(page_type: str) -> str:
    """Map page type to its wiki subdirectory."""
    mapping = {
        "source": "sources",
        "concept": "concepts",
        "entity": "entities",
        "synthesis": "syntheses",
        "comparison": "syntheses",
    }
    return mapping.get(page_type, "concepts")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a wiki page from a template with correct frontmatter."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("page_type", choices=sorted(VALID_TYPES), help="Page type")
    parser.add_argument("title", help="Page title")
    parser.add_argument("--title-zh", default=None, help="Chinese title")
    parser.add_argument("--tags", default=None, help='Comma-separated tags (e.g. "AI,Deep-Learning")')
    parser.add_argument("--sources", default=None, help='Comma-separated source paths')
    parser.add_argument("--raw-path", default=None, help="Raw source file path (source type only)")
    parser.add_argument("--compute-hash", action="store_true", help="Compute SHA256 of raw_path file and add to frontmatter")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()

    # Determine template directory
    template_dir = wiki_root / "_templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parent.parent / "_templates"
    if not template_dir.exists():
        print(f"ERROR: _templates/ directory not found (tried {template_dir})", file=sys.stderr)
        return 1

    # Load template (synthesis falls back to concept template)
    template = load_template(template_dir, args.page_type)
    if template is None and args.page_type == "synthesis":
        template = load_template(template_dir, "concept")
    if template is None:
        print(f"ERROR: No template found for type '{args.page_type}'", file=sys.stderr)
        return 1

    # Fix type field when synthesis fell back to concept template
    if args.page_type == "synthesis":
        template = fill_fm_field(template, "type", "synthesis")

    # Determine output path
    slug = slugify(args.title)
    subdir = type_to_dir(args.page_type)
    out_dir = wiki_root / "wiki" / subdir
    out_path = out_dir / f"{slug}.md"

    # Check if page already exists
    if out_path.exists():
        print(f"ERROR: Page already exists: {out_path}", file=sys.stderr)
        return 1

    # Parse optional arguments
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else []
    today = date.today().isoformat()

    # Validate raw_path exists
    if args.raw_path:
        raw_full = wiki_root / args.raw_path
        if not raw_full.exists():
            print(f"WARNING: raw_path does not exist: {raw_full}", file=sys.stderr)

    # Compute SHA256 hash of raw source if requested
    raw_hash = None
    if args.compute_hash and args.raw_path:
        raw_full = wiki_root / args.raw_path
        if raw_full.exists():
            raw_hash = hashlib.sha256(raw_full.read_bytes()).hexdigest()

    # Fill template
    content = fill_template(template, args.title, args.title_zh, today, tags, sources, args.raw_path)

    # Add hash to frontmatter if computed
    if raw_hash:
        # Insert raw_hash before the closing --- of frontmatter
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = "---" + parts[1].rstrip() + f'\nraw_hash: "{raw_hash}"\n---' + parts[2]

    # Write file
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    # Output the path for the agent to use
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
