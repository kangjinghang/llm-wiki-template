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

# Ensure stdout/stderr handle Unicode on Windows (GBK console default)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from create_page import load_template, fill_template, fill_fm_field, type_to_dir
from slug_utils import slugify, derive_slug
from extract_knowledge import load_api_config
from merge_frontmatter import (
    parse_frontmatter, merge_array_field,
    merge_related_pages_section, merge_timeline_entries,
)


def _auto_fix_wikilinks(text: str) -> str:
    """Fix common wikilink typos from LLM output.

    Handles: [[[ → [[, [[[" → [[, [[" → [[, ]] → ]], etc.
    """
    # Fix over-quoted wikilinks: [[["name"]] → [[name]]
    text = re.sub(r'\[\[\["([^"]+)"\]\]', r'[[\1]]', text)
    text = re.sub(r'\[\[\[([^\]]+?)\]\]\]', r'[[\1]]', text)
    text = re.sub(r'\[\["([^"]+)"\]\]', r'[[\1]]', text)
    # Fix plain triple brackets
    text = text.replace("[[[", "[[").replace("]]]", "]]")
    return text


def normalize_wikilink_slugs(text: str) -> str:
    """Normalize wikilink targets to match slugify conventions.

    Converts [[Foo Bar]] → [[foo-bar]], [[修正2.0]] → [[修正2-0]].
    Preserves alias syntax: [[Slug|Display]] → [[slug|Display]].
    This prevents dead links caused by LLM using dots/spaces instead of hyphens.
    """
    def _normalize_target(m):
        inner = m.group(1)
        if "|" in inner:
            raw_target, display = inner.split("|", 1)
        else:
            raw_target = inner
            display = None

        normalized = slugify(raw_target.strip())
        if display:
            return f"[[{normalized}|{display}]]"
        return f"[[{normalized}]]"

    return re.sub(r'\[\[([^\]]+)\]\]', _normalize_target, text)


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
    sources: list[str] | None = None,
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

    # Fill sources (so new pages are never created with sources: [])
    if sources:
        parts = filled.split("---", 2)
        if len(parts) >= 3:
            raw_fm = parts[1]
            body_part = parts[2]
            raw_fm = merge_array_field(raw_fm, "sources", sources)
            filled = "---" + raw_fm + "---" + body_part

    # Replace body with content
    content = _auto_fix_wikilinks(content)
    content = normalize_wikilink_slugs(content)
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


def normalize_wikilinks(text: str, existing_pages: set[str]) -> str:
    """Normalize wikilinks to match actual page filenames (slug case).

    Converts [[Bollinger带]] → [[bollinger带]] when the file is bollinger带.md.
    Preserves alias syntax: [[Slug|Display]] → [[slug|Display]].
    Leaves links to non-existent pages unchanged.
    """
    # Build lookup: lowercase slug → actual stem
    slug_to_stem = {stem.lower(): stem for stem in existing_pages}

    def _normalize(m):
        inner = m.group(1)
        if "|" in inner:
            slug, display = inner.split("|", 1)
        else:
            slug = inner
            display = None

        slug_stripped = slug.strip()
        # Use slugify for consistent comparison
        slugified = slugify(slug_stripped)

        # Find the actual stem that matches
        if slugified in slug_to_stem and slug_stripped != slug_to_stem[slugified]:
            actual = slug_to_stem[slugified]
            if display:
                return f"[[{actual}|{display}]]"
            return f"[[{actual}]]"
        return m.group(0)

    result = re.sub(r'\[\[([^\]]+)\]\]', _normalize, text)
    return result


def fix_dead_wikilinks(wiki_dir: str, page_paths: list[str]) -> int:
    """Remove brackets from wikilinks pointing to non-existent pages.

    Args:
        wiki_dir: Path to the wiki/ directory.
        page_paths: List of page file paths to scan.

    Returns:
        Number of dead wikilinks fixed.
    """
    wiki_path = Path(wiki_dir)
    existing_pages = {p.stem for p in wiki_path.rglob("*.md")}

    fixed_count = 0
    for page_str in page_paths:
        page_path = Path(page_str)
        if not page_path.exists():
            continue
        text = page_path.read_text(encoding="utf-8")

        # First normalize case
        text_norm = normalize_wikilinks(text, existing_pages)

        # Then strip dead links
        def _replace_dead(m):
            nonlocal fixed_count
            target = m.group(1)
            slug = target.split("|")[0].strip() if "|" in target else target.strip()
            if slug in existing_pages or slug.lower() in existing_pages:
                return m.group(0)
            fixed_count += 1
            return target

        new_text = re.sub(r'\[\[([^\]]+)\]\]', _replace_dead, text_norm)
        if new_text != text:
            page_path.write_text(new_text, encoding="utf-8")
            print(f"  Fixed dead wikilinks: {page_path.name}")
    if fixed_count:
        print(f"  Fixed {fixed_count} dead wikilinks across {len(page_paths)} pages")
    return fixed_count


def fill_missing_raw_path(source_page: Path, raw_path: str | None, wiki_root: Path) -> bool:
    """Fill empty raw_path on an existing source page and add raw_hash.

    Returns True if the page was updated, False otherwise.
    """
    if not raw_path or not source_page.exists():
        return False

    text = source_page.read_text(encoding="utf-8")
    if not re.search(r'^raw_path:\s*""?\s*$', text, re.MULTILINE):
        return False

    text = re.sub(r'^raw_path:\s*".*"$', f'raw_path: "{raw_path}"', text, count=1, flags=re.MULTILINE)
    if "raw_hash:" not in text:
        raw_full = wiki_root / raw_path
        if raw_full.exists():
            raw_hash = hashlib.sha256(raw_full.read_bytes()).hexdigest()
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = "---" + parts[1].rstrip() + f'\nraw_hash: "{raw_hash}"\n---' + parts[2]

    source_page.write_text(text, encoding="utf-8")
    print(f"  Fixed raw_path: {source_page.name}")
    return True


def find_raw_path_for_extract(wiki_root: Path, extract_path: str | Path) -> str | None:
    """Find the raw article path corresponding to an extract JSON file.

    The extract filename is extract-{derive_slug}.json where derive_slug
    strips [timestamp] prefix from the raw article filename.
    """
    extract_stem = Path(extract_path).stem
    if not extract_stem.startswith("extract-"):
        return None

    slug = extract_stem[8:]  # Remove "extract-" prefix
    raw_dir = wiki_root / "raw" / "articles"
    if not raw_dir.exists():
        return None

    for article in sorted(raw_dir.glob("*.md")):
        article_slug = derive_slug(f"raw/articles/{article.name}")
        if article_slug == slug:
            return f"raw/articles/{article.name}"

    return None


def build_index_entries(
    title: str,
    concepts: list[dict],
    entities: list[dict],
    summary: str,
) -> dict[str, list[str]]:
    """Build index entry strings with slugified wikilink targets.

    Returns a dict with keys "source", "concept", "entity", "synthesis"
    mapping to lists of entry strings like "[[slug]] — description".
    """
    entries_map: dict[str, list[str]] = {"source": [], "concept": [], "entity": [], "synthesis": []}

    if title:
        source_slug = slugify(title)
        entries_map["source"].append(f"[[{source_slug}]] — {summary[:80]}")

    for concept in concepts:
        name = concept.get("name", "")
        desc = concept.get("description", "")
        if name:
            entries_map["concept"].append(f"[[{slugify(name)}]] — {desc}")

    for entity in entities:
        name = entity.get("name", "")
        desc = entity.get("description", "")
        if name:
            entries_map["entity"].append(f"[[{slugify(name)}]] — {desc}")

    return entries_map


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

    # 1. Determine raw_path from extract filename (robust against title special chars)
    raw_path = find_raw_path_for_extract(wiki_root, extract_path)

    # 2. Create source page
    source_content = data.get("source_content", "")
    source_slug = slugify(title) if title else ""
    source_path = wiki_root / "wiki" / "sources" / f"{source_slug}.md" if source_slug else None

    if title and source_content:
        result = _create_page(
            wiki_root, template_dir, "source", title,
            summary=summary, content=source_content,
            raw_path=raw_path, compute_hash=True,
        )
        if result:
            created_pages.append(f"source: {result.name}")
            print(f"  Created source: {result}")

    # Fix raw_path on existing source page if empty
    if source_path and raw_path:
        fill_missing_raw_path(source_path, raw_path, wiki_root)

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
            sources=[source_wikilink],
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
            sources=[source_wikilink],
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

        entries_map = build_index_entries(title, concepts, entities, summary)

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

    # 8. Fix dead wikilinks in newly created/updated pages
    wiki_dir = wiki_root / "wiki"
    all_touched = list(dict.fromkeys(
        [str(Path(p)) for p in
         [wiki_root / c.split(": ", 1)[-1] for c in created_pages if ": " in c] +
         [wiki_root / u for u in updated_pages]]
    ))
    fix_dead_wikilinks(str(wiki_dir), all_touched)

    # Summary
    print(f"\nDone. Created {len(created_pages)} pages, updated {len(updated_pages)} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
