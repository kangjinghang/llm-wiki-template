#!/usr/bin/env python3
"""
merge_frontmatter.py — Deterministically merge array fields into wiki page frontmatter.

Replaces multiple LLM Edit calls for adding sources/tags/related to entity
and concept pages with a single Bash call.

Usage:
    python3 merge_frontmatter.py <page-path> \
      --sources "[[新来源1]],[[新来源2]]" \
      --tags "新标签" \
      --related "[[关联页面]]"

Exit codes:
    0 — success
    1 — error
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict | None, str, str]:
    """Split file content into frontmatter dict, body, and raw frontmatter text.

    Returns (frontmatter_dict, body_text, raw_frontmatter_text).
    The dict maps field names to their raw string values (no parsing of values).
    Returns (None, content, "") if no frontmatter block found.
    """
    if not content.startswith("---"):
        return None, content, ""

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content, ""

    raw_fm = parts[1]
    body = parts[2]
    # Normalize: if body starts with double newline, treat the first as part of
    # the --- delimiter so body starts with exactly one \n
    if body.startswith("\n\n"):
        body = body[1:]

    # Parse key: value pairs (simple, no nesting)
    fm = {}
    for line in raw_fm.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if match:
            fm[match.group(1)] = match.group(2)

    return fm, body, raw_fm


def _extract_existing_list_items(raw_fm: str, field: str) -> list[str]:
    """Extract existing items from a YAML list-format array field.

    Given:
      sources:
        - "[[a]]"
        - "[[b]]"

    Returns: ['[[a]]', '[[b]]']
    """
    items = []
    in_field = False
    for line in raw_fm.split("\n"):
        stripped = line.strip()
        if re.match(rf"^{re.escape(field)}:", stripped):
            in_field = True
            # Check if inline format: field: [a, b]
            inline_match = re.match(rf"^{re.escape(field)}:\s*\[(.+)\]\s*$", stripped)
            if inline_match:
                return [item.strip().strip('"').strip("'") for item in inline_match.group(1).split(",")]
            # If field: with nothing after, it's an empty list
            if stripped == f"{field}:" or stripped.endswith(":"):
                continue
            continue
        if in_field:
            if stripped.startswith("- "):
                item = stripped[2:].strip().strip('"').strip("'")
                items.append(item)
            elif stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                # New field started, stop
                in_field = False
    return items


def merge_array_field(raw_fm: str, field: str, new_items: list[str]) -> str:
    """Merge new items into an existing array field in raw frontmatter text.

    Handles both YAML list format and inline [a, b] format.
    Skips items that already exist (deduplication).
    Returns the updated raw frontmatter string.
    """
    if not re.search(rf"^{re.escape(field)}:", raw_fm, re.MULTILINE):
        return raw_fm

    existing = _extract_existing_list_items(raw_fm, field)
    to_add = [item for item in new_items if item not in existing]

    if not to_add:
        return raw_fm

    lines = raw_fm.split("\n")
    result_lines = []
    in_field = False
    field_indent = ""
    added = False

    for line in lines:
        stripped = line.strip()

        if re.match(rf"^{re.escape(field)}:", stripped):
            in_field = True
            # Determine indentation
            field_indent = line[:len(line) - len(line.lstrip())]

            # Check inline format: field: [a, b]
            inline_match = re.match(rf"^{re.escape(field)}:\s*\[(.+)\]\s*$", stripped)
            if inline_match:
                existing_inline = [item.strip().strip('"').strip("'") for item in inline_match.group(1).split(",")]
                all_items = existing_inline + to_add
                new_inline = ", ".join(all_items)
                result_lines.append(f"{field_indent}{field}: [{new_inline}]")
                added = True
                in_field = False
                continue

            result_lines.append(line)
            continue

        if in_field:
            if stripped.startswith("- "):
                result_lines.append(line)
            elif stripped == "" and not added:
                # Empty line at end of list — insert new items here
                for item in to_add:
                    result_lines.append(f'{field_indent}  - "{item}"')
                added = True
                result_lines.append(line)
                in_field = False
            elif stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                # Next field — insert new items before it
                if not added:
                    for item in to_add:
                        result_lines.append(f'{field_indent}  - "{item}"')
                    added = True
                in_field = False
                result_lines.append(line)
            else:
                result_lines.append(line)
        else:
            result_lines.append(line)

    # If we never found a blank line or next field, append at the end
    if in_field and not added:
        for item in to_add:
            result_lines.append(f'{field_indent}  - "{item}"')

    return "\n".join(result_lines)


def serialize_frontmatter(raw_fm: str, body: str) -> str:
    """Reassemble file content from raw frontmatter and body."""
    return "---" + raw_fm + "---" + body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge array fields into wiki page frontmatter."
    )
    parser.add_argument("page_path", help="Path to the wiki page file")
    parser.add_argument("--sources", default=None, help="Comma-separated source names to append")
    parser.add_argument("--tags", default=None, help="Comma-separated tags to append")
    parser.add_argument("--related", default=None, help="Comma-separated related page slugs to append")
    args = parser.parse_args()

    page_path = Path(args.page_path).resolve()
    if not page_path.exists():
        print(f"ERROR: File not found: {page_path}", file=sys.stderr)
        return 1

    content = page_path.read_text(encoding="utf-8")

    # Validate input args: reject [[[ syntax
    for arg_val in [args.sources, args.tags, args.related]:
        if arg_val and "[[[" in arg_val:
            print("ERROR: Input contains [[[ syntax (should be [[). Fix wikilinks.", file=sys.stderr)
            return 1

    fm, body, raw_fm = parse_frontmatter(content)

    if fm is None:
        print(f"ERROR: No frontmatter found in {page_path}", file=sys.stderr)
        return 1

    changed = False

    if args.sources:
        new_sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        before = raw_fm
        raw_fm = merge_array_field(raw_fm, "sources", new_sources)
        if raw_fm != before:
            changed = True

    if args.tags:
        new_tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        before = raw_fm
        raw_fm = merge_array_field(raw_fm, "tags", new_tags)
        if raw_fm != before:
            changed = True

    if args.related:
        new_related = [r.strip() for r in args.related.split(",") if r.strip()]
        before = raw_fm
        raw_fm = merge_array_field(raw_fm, "related", new_related)
        if raw_fm != before:
            changed = True

    if not changed:
        print(f"No changes needed: {page_path}")
        return 0

    # Validate: reject [[[ wikilink syntax
    if "[[[" in raw_fm:
        print("ERROR: Result contains [[[ syntax (should be [[). Fix wikilinks before merging.", file=sys.stderr)
        return 1

    # Update the `updated` date
    today = date.today().isoformat()
    raw_fm = re.sub(r"^updated:\s*.*$", f"updated: {today}", raw_fm, count=1, flags=re.MULTILINE)

    # Write back
    result = serialize_frontmatter(raw_fm, body)
    page_path.write_text(result, encoding="utf-8")
    print(f"Updated: {page_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
