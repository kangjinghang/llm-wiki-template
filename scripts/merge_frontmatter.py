#!/usr/bin/env python3
"""
merge_frontmatter.py — Deterministically merge array fields and body sections into wiki pages.

Replaces multiple LLM Edit calls for adding sources/tags/related, related pages sections,
and timeline entries with a single Bash call.

Usage:
    python3 merge_frontmatter.py <page-path> \
      --sources "[[新来源1]],[[新来源2]]" \
      --tags "新标签" \
      --related "[[关联页面]]" \
      --related-pages "[[Foo]] — desc1||[[Bar]] — desc2" \
      --timeline "2021.06：《Title》（Authors）——desc"

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


def _extract_wikilink_target(entry: str) -> str:
    """Extract first [[...]] target from an entry for deduplication."""
    m = re.search(r"\[\[([^\]]+)\]\]", entry)
    return m.group(1) if m else ""


def _find_section_end(body: str, start: int) -> int:
    """Find the start of the next ## heading after position start, or EOF."""
    idx = body.find("\n## ", start + 1)
    return idx if idx != -1 else len(body)


def _find_related_pages_insert_point(body: str) -> int:
    """Find insert point before Sources/Notes heading, or EOF."""
    for marker in ["\n## Sources / 来源", "\n## Sources", "\n## Notes / 笔记", "\n## Notes"]:
        idx = body.find(marker)
        if idx != -1:
            return idx
    return len(body)


def merge_related_pages_section(body: str, entries: list[str]) -> tuple[str, bool]:
    """Append entries to ## Related Pages / 关联页面 section.

    Deduplicates by wikilink target. Creates the section if missing
    (inserted before Sources/Notes/EOF).

    Returns (updated_body, changed).
    """
    if not entries:
        return body, False

    # Try both heading variants
    section_markers = ["## Related Pages / 关联页面", "## Related Pages"]
    section_start = -1
    for marker in section_markers:
        idx = body.find(marker)
        if idx != -1:
            section_start = idx
            break

    if section_start == -1:
        # Create section before Sources/Notes/EOF
        insert_pos = _find_related_pages_insert_point(body)
        new_section = "\n## Related Pages / 关联页面\n"
        for entry in entries:
            new_section += f"\n- {entry}"
        new_section += "\n"
        body = body[:insert_pos] + new_section + body[insert_pos:]
        return body, True

    section_end = _find_section_end(body, section_start)

    # Extract existing wikilink targets in the section
    section_text = body[section_start:section_end]
    existing_targets = set()
    for m in re.finditer(r"\[\[([^\]]+)\]\]", section_text):
        existing_targets.add(m.group(1))

    # Filter new entries by dedup
    to_add = []
    for entry in entries:
        target = _extract_wikilink_target(entry)
        if target and target in existing_targets:
            continue
        to_add.append(entry)
        if target:
            existing_targets.add(target)

    if not to_add:
        return body, False

    # Append entries before section end
    lines_to_add = "".join(f"\n- {entry}" for entry in to_add)
    body = body[:section_end] + lines_to_add + body[section_end:]
    return body, True


def merge_timeline_entries(body: str, entries: list[str]) -> tuple[str, bool]:
    """Append entries to - 研究时间线： sublist in ## Key Facts / 关键事实.

    Deduplicates by exact text. Creates the sublist if missing.
    Returns unchanged if no Key Facts section exists.

    Returns (updated_body, changed).
    """
    if not entries:
        return body, False

    # Find Key Facts section
    kf_markers = ["## Key Facts / 关键事实", "## Key Facts"]
    kf_start = -1
    for marker in kf_markers:
        idx = body.find(marker)
        if idx != -1:
            kf_start = idx
            break

    if kf_start == -1:
        # No Key Facts section — don't create one, just skip
        return body, False

    kf_end = _find_section_end(body, kf_start)
    section_text = body[kf_start:kf_end]

    # Find timeline sublist
    timeline_idx = section_text.find("- 研究时间线：")
    if timeline_idx == -1:
        # No timeline sublist yet — skip (don't create structure from scratch)
        return body, False

    # Find existing entries in the timeline sublist (indented lines after the marker)
    existing_entries = set()
    pos = timeline_idx + len("- 研究时间线：")
    for line in section_text[pos:].split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            existing_entries.add(stripped[2:])
        elif stripped and not stripped.startswith("-") and not stripped.startswith("#"):
            break

    to_add = [e for e in entries if e not in existing_entries]
    if not to_add:
        return body, False

    # Find the absolute position of the timeline marker in body
    abs_timeline = kf_start + timeline_idx
    # Find the end of the timeline sublist
    abs_pos = abs_timeline + len("- 研究时间线：")
    lines = body[abs_pos:].split("\n")
    sublist_end_offset = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0:
            # First line after the marker — might be content on same line or empty
            continue
        if stripped.startswith("- "):
            sublist_end_offset += len(lines[i - 1]) + 1  # +1 for \n
            continue
        if stripped == "":
            sublist_end_offset += len(lines[i - 1]) + 1 if i > 0 else 0
            break
        break

    # Recalculate: find end of indented sublist items
    after_marker = body[abs_timeline:]
    sublist_lines = after_marker[len("- 研究时间线："):].split("\n")
    insert_offset = 0
    for i, line in enumerate(sublist_lines):
        if line.strip().startswith("- "):
            insert_offset += len(line) + 1  # +1 for \n
        elif i == 0 and line.strip() == "":
            # Empty line right after marker
            continue
        else:
            break

    abs_insert = abs_timeline + len("- 研究时间线：") + insert_offset
    lines_to_add = "".join(f"\n  - {entry}" for entry in to_add)
    body = body[:abs_insert] + lines_to_add + body[abs_insert:]
    return body, True


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
    parser.add_argument("--related-pages", default=None,
                        help="||-separated Related Pages section entries, e.g. '[[Foo]] — desc1||[[Bar]] — desc2'")
    parser.add_argument("--timeline", default=None,
                        help="||-separated timeline entries, e.g. '2021.06：《Title》（Authors）——desc'")
    args = parser.parse_args()

    page_path = Path(args.page_path).resolve()
    if not page_path.exists():
        print(f"ERROR: File not found: {page_path}", file=sys.stderr)
        return 1

    content = page_path.read_text(encoding="utf-8")

    # Auto-fix [[[ wikilink syntax from LLM (input args)
    for attr in ["sources", "tags", "related", "related_pages", "timeline"]:
        val = getattr(args, attr)
        if val and "[[[" in val:
            print(f"WARNING: Auto-fixing [[[ → [[ in --{attr}", file=sys.stderr)
            setattr(args, attr, val.replace("[[[", "[[").replace("]]]", "]]"))

    fm, body, raw_fm = parse_frontmatter(content)

    if fm is None:
        print(f"ERROR: No frontmatter found in {page_path}", file=sys.stderr)
        return 1

    # Auto-fix [[[ wikilink syntax in existing frontmatter
    if "[[[" in raw_fm:
        print("WARNING: Auto-fixing [[[ → [[ in existing frontmatter", file=sys.stderr)
        raw_fm = raw_fm.replace("[[[", "[[").replace("]]]", "]]")

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

    # Body operations
    if args.related_pages:
        new_rp = [e.strip() for e in args.related_pages.split("||") if e.strip()]
        body, body_changed = merge_related_pages_section(body, new_rp)
        if body_changed:
            changed = True

    if args.timeline:
        new_tl = [e.strip() for e in args.timeline.split("||") if e.strip()]
        body, body_changed = merge_timeline_entries(body, new_tl)
        if body_changed:
            changed = True

    if not changed:
        print(f"No changes needed: {page_path}")
        return 0

    # Auto-fix any remaining [[[ in result (shouldn't happen, but safety net)
    if "[[[" in raw_fm:
        print("WARNING: Auto-fixing [[[ → [[ in merged frontmatter", file=sys.stderr)
        raw_fm = raw_fm.replace("[[[", "[[").replace("]]]", "]]")

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
