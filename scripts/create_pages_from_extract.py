#!/usr/bin/env python3
"""
create_pages_from_extract.py — Create/update all wiki pages from an extraction JSON.

Reads the extraction JSON produced by extract_knowledge.py and:
  1. Creates the source summary page
  2. Creates new concept/entity pages (is_new=true / existing_page=null)
  3. Cascade-updates existing pages (sources, tags, related)
  4. Updates wiki/index.md and wiki/index-summary.md

Usage:
    python create_pages_from_extract.py <wiki-root> <extract-json>

Exit codes:
    0 — success
    1 — error
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

from create_page import slugify, load_template, fill_template, fill_fm_field, type_to_dir
from extract_knowledge import load_api_config
from merge_frontmatter import (
    parse_frontmatter, merge_array_field,
    merge_related_pages_section, merge_timeline_entries,
)


def _auto_fix_wikilinks(text: str) -> str:
    """Fix [[[ → [[ triple bracket typos from LLM output."""
    return text.replace("[[[", "[[").replace("]]]", "]]")


def _create_page(
    wiki_root: Path,
    template_dir: Path,
    page_type: str,
    title: str,
    summary: str,
    content: str,
    raw_path: str | None = None,
    compute_hash: bool = False,
    tags: list[str] | None = None,
) -> Path | None:
    """Create a single wiki page. Returns path or None if it already exists."""
    slug = slugify(title)
    subdir = type_to_dir(page_type)
    out_dir = wiki_root / "wiki" / subdir
    out_path = out_dir / f"{slug}.md"

    if out_path.exists():
        print(f"  SKIP (exists): {out_path}", file=sys.stderr)
        return None

    template = load_template(template_dir, page_type)
    if template is None and page_type == "synthesis":
        template = load_template(template_dir, "concept")
    if template is None:
        print(f"  SKIP (no template for {page_type}): {title}", file=sys.stderr)
        return None

    if page_type == "synthesis":
        template = fill_fm_field(template, "type", "synthesis")

    today = date.today().isoformat()
    filled = fill_template(template, title, None, today, tags or [], [], raw_path)

    # Compute hash
    if compute_hash and raw_path:
        raw_full = wiki_root / raw_path
        if raw_full.exists():
            raw_hash = hashlib.sha256(raw_full.read_bytes()).hexdigest()
            parts = filled.split("---", 2)
            if len(parts) >= 3:
                filled = "---" + parts[1].rstrip() + f'\nraw_hash: "{raw_hash}"\n---' + parts[2]

    # Fill summary
    if summary:
        filled = fill_fm_field(filled, "summary", f'"{summary}"')

    # Replace body with content
    content = _auto_fix_wikilinks(content)
    if content:
        parts = filled.split("---", 2)
        if len(parts) >= 3:
            filled = "---" + parts[1] + "---\n" + content.lstrip("\n") + "\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(filled, encoding="utf-8")
    return out_path


def _call_merge_api(
    config: dict,
    existing_body: str,
    new_content: str,
    source_title: str,
) -> str | None:
    """Call the LLM API to generate incremental content for an existing page.

    Returns incremental text to append, or None if nothing new to add.
    """
    system_prompt = (
        "你是一个知识编辑。已有页面写了一些内容，新文章提供了补充信息。"
        "只输出需要追加到已有页面的新内容。如果新信息已在已有页面中存在，不要重复。"
        "输出格式：要追加的 markdown 文本。如果没有新信息需要追加，只输出 \"无\"。"
    )
    user_message = (
        f"## 已有页面内容\n{existing_body[:3000]}\n\n"
        f"## 新文章补充\n{new_content[:2000]}\n\n"
        f"## 来源\n{source_title}"
    )

    api_url = config["base_url"].rstrip("/") + "/v1/messages"
    request_body = json.dumps({
        "model": config["model"],
        "max_tokens": 1024,
        "temperature": 0.1,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  WARNING: merge API call failed: {e}", file=sys.stderr)
        return None

    response_text = ""
    for block in resp_data.get("content", []):
        if block.get("type") == "text":
            response_text += block.get("text", "")

    text = response_text.strip()
    if not text or text == "无" or text == "无新信息":
        return None
    return text


def _merge_page_content(
    page_path: Path,
    incremental_text: str,
    source_title: str,
) -> bool:
    """Append incremental content to an existing page before ## 来源 / Sources."""
    text = page_path.read_text(encoding="utf-8")

    # Only modify the body part (after frontmatter)
    fm, body, raw_fm = parse_frontmatter(text)
    if fm is None:
        return False

    slug = slugify(source_title)
    subsection_header = f"### 来自 [[{slug}]]"

    # Skip if this subsection already exists (dedup)
    if subsection_header in body:
        print(f"  SKIP (subsection exists): {subsection_header}", file=sys.stderr)
        return False

    new_section = f"\n## 补充发现 / Additional Findings\n\n{subsection_header}\n\n{incremental_text}\n"

    # Insert before ## 来源 / Sources or ## Sources
    insert_markers = ["## 来源 / Sources", "## Sources", "## 来源"]
    inserted = False
    for marker in insert_markers:
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx] + new_section + body[idx:]
            inserted = True
            break

    if not inserted:
        # Append at end
        body = body.rstrip("\n") + new_section

    result = "---" + raw_fm + "---" + body
    page_path.write_text(result, encoding="utf-8")
    return True


def _cascade_update(
    page_path: Path,
    source_wikilink: str,
    tags: list[str],
    related_pages: list[str] | None = None,
    timeline_entries: list[str] | None = None,
) -> bool:
    """Update an existing page with new source, tags, related pages, and timeline."""
    if not page_path.exists():
        print(f"  SKIP (not found): {page_path}", file=sys.stderr)
        return False

    text = page_path.read_text(encoding="utf-8")
    fm, body, raw_fm = parse_frontmatter(text)
    if fm is None:
        print(f"  SKIP (bad frontmatter): {page_path}", file=sys.stderr)
        return False

    # Merge source into frontmatter
    raw_fm = merge_array_field(raw_fm, "sources", [source_wikilink])

    # Merge tags into frontmatter
    raw_fm = merge_array_field(raw_fm, "tags", tags)

    # Update date
    today = date.today().isoformat()
    raw_fm = re.sub(r"(^updated:\s*).*?$", rf"\g<1>{today}", raw_fm, count=1, flags=re.MULTILINE)

    # Merge related pages into body
    if related_pages:
        body, _ = merge_related_pages_section(body, related_pages)

    # Merge timeline entries into body
    if timeline_entries:
        body, _ = merge_timeline_entries(body, timeline_entries)

    result = "---" + raw_fm + "---" + body
    page_path.write_text(result, encoding="utf-8")
    return True


def _find_existing_page(wiki_root: Path, page_type: str, name: str) -> Path | None:
    """Find an existing page by name."""
    subdir = type_to_dir(page_type)
    slug = slugify(name)
    path = wiki_root / "wiki" / subdir / f"{slug}.md"
    return path if path.exists() else None


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python create_pages_from_extract.py <wiki-root> <extract-json>", file=sys.stderr)
        return 1

    wiki_root = Path(sys.argv[1]).resolve()
    extract_path = Path(sys.argv[2]).resolve()

    if not extract_path.exists():
        print(f"ERROR: {extract_path} not found", file=sys.stderr)
        return 1

    data = json.loads(extract_path.read_text(encoding="utf-8"))

    # Resolve template dir
    template_dir = wiki_root / "_templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parent.parent / "_templates"
    if not template_dir.exists():
        print(f"ERROR: _templates/ not found", file=sys.stderr)
        return 1

    title = data.get("title", "")
    tags = data.get("tags", [])
    summary = data.get("summary", "")
    concepts = data.get("concepts", [])
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    source_wikilink = f"[[{slugify(title)}]]"
    created_pages: list[str] = []
    updated_pages: list[str] = []

    # 1. Determine raw_path
    raw_path = None
    raw_dir = wiki_root / "raw" / "articles"
    if raw_dir.exists():
        for article in sorted(raw_dir.glob("*.md")):
            # Match by checking if title is in filename
            if title and title[:10] in article.stem:
                raw_path = f"raw/articles/{article.name}"
                break

    # 2. Create source page
    source_content = data.get("source_content", "")
    if title and source_content:
        result = _create_page(
            wiki_root, template_dir, "source", title,
            summary=summary, content=source_content,
            raw_path=raw_path, compute_hash=True,
        )
        if result:
            created_pages.append(f"source: {result.name}")
            print(f"  Created source: {result}")

    # 3. Create new concept pages
    for concept in concepts:
        if not concept.get("is_new", True):
            continue
        name = concept.get("name", "")
        page_content = concept.get("page_content", "")
        desc = concept.get("description", "")
        if not name:
            continue
        result = _create_page(
            wiki_root, template_dir, "concept", name,
            summary=desc, content=page_content, tags=tags,
        )
        if result:
            created_pages.append(f"concept: {result.name}")
            print(f"  Created concept: {result}")

    # 4. Create new entity pages
    for entity in entities:
        if entity.get("existing_page"):
            continue
        name = entity.get("name", "")
        page_content = entity.get("page_content", "")
        desc = entity.get("description", "")
        if not name:
            continue
        result = _create_page(
            wiki_root, template_dir, "entity", name,
            summary=desc, content=page_content, tags=tags,
        )
        if result:
            created_pages.append(f"entity: {result.name}")
            print(f"  Created entity: {result}")

    # Build related_pages and timeline from concepts for cascade updates
    new_concept_pages = [
        f"[[{c['name']}]] — {c.get('description', '')}"
        for c in concepts if c.get("is_new", True) and c.get("name")
    ]
    # Build timeline entry from source info
    timeline = []
    if title:
        timeline.append(f"{date.today().strftime('%Y.%m')}：《{title}》")

    # Load API config for content merge
    settings_path = Path.home() / ".claude" / "settings.json"
    api_config = load_api_config(settings_path)

    # 5. Cascade-update existing concept pages (with content merge)
    for concept in concepts:
        if concept.get("is_new", True):
            continue
        name = concept.get("name", "")
        page_content = concept.get("page_content", "")
        page_path = _find_existing_page(wiki_root, "concept", name)
        if page_path:
            changed = _cascade_update(
                page_path, source_wikilink, tags,
                related_pages=new_concept_pages,
                timeline_entries=timeline,
            )
            if changed:
                updated_pages.append(str(page_path))
                print(f"  Updated: {page_path}")
            # Content merge: generate incremental content via API
            if api_config and page_content and title:
                incremental = _call_merge_api(api_config, page_path.read_text(encoding="utf-8"), page_content, title)
                if incremental:
                    merged = _merge_page_content(page_path, incremental, title)
                    if merged:
                        print(f"  Merged content: {page_path}")

    # 6. Cascade-update existing entity pages
    for entity in entities:
        existing = entity.get("existing_page", "")
        if not existing:
            continue
        # Normalize backslashes for Windows compatibility
        existing = existing.replace("\\", "/")
        page_path = wiki_root / existing
        changed = _cascade_update(
            page_path, source_wikilink, tags,
            related_pages=new_concept_pages,
            timeline_entries=timeline,
        )
        if changed:
            updated_pages.append(str(page_path))
            print(f"  Updated: {page_path}")

    # 7. Update index.md and index-summary.md
    from update_index import add_entries, _SECTION_MAP, _generate_summary

    index_path = wiki_root / "wiki" / "index.md"
    if index_path.exists():
        index_content = index_path.read_text(encoding="utf-8")

        entries_map = {"source": [], "concept": [], "entity": [], "synthesis": []}
        if title:
            entries_map["source"].append(f"{source_wikilink} — {summary[:80]}")
        for concept in concepts:
            name = concept.get("name", "")
            desc = concept.get("description", "")
            if name:
                entries_map["concept"].append(f"[[{name}]] — {desc}")
        for entity in entities:
            name = entity.get("name", "")
            desc = entity.get("description", "")
            if name:
                entries_map["entity"].append(f"[[{name}]] — {desc}")

        for section_name, entries in entries_map.items():
            if entries:
                index_content = add_entries(index_content, section_name, entries)

        index_path.write_text(index_content, encoding="utf-8")
        print(f"  Updated: {index_path}")

        # Sync index-summary.md
        summary_path = wiki_root / "wiki" / "index-summary.md"
        summary_content = _generate_summary(index_content)
        summary_path.write_text(summary_content, encoding="utf-8")
        print(f"  Updated: {summary_path}")

    # Summary
    print(f"\nDone. Created {len(created_pages)} pages, updated {len(updated_pages)} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
