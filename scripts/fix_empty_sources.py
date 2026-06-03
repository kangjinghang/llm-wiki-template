#!/usr/bin/env python3
"""Fix empty sources on non-seed concept/entity pages.

Strategy:
1. Reverse-index source page wikilinks (source -> concept/entity)
2. Map extract JSONs to source pages via title matching, then extract concept/entity names
3. Scan concept/entity page bodies for wikilinks to source pages
4. Keyword search for remaining unfixable pages

Usage:
    python scripts/fix_empty_sources.py <wiki-root>
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_frontmatter import parse_frontmatter, _extract_existing_list_items, merge_array_field

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def slugify(text: str) -> str:
    """Slugify text for matching."""
    s = text.strip().lower()
    s = re.sub(r'[：:—\-–、，。？！“”‘’（）()\[\]【】《》·\.\?\!\,\;]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'[^\w一-鿿-]', '', s)
    return s


def fix_frontmatter_blanks(wiki_root: Path) -> int:
    """Fix pages with extra blank lines after the opening --- delimiter."""
    fixed = 0
    for d in ("wiki/concepts", "wiki/entities", "wiki/sources", "wiki/syntheses"):
        full_dir = wiki_root / d
        if not full_dir.is_dir():
            continue
        for f in full_dir.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            new_text = re.sub(r"^---\n\n+", "---\n", text)
            if new_text != text:
                f.write_text(new_text, encoding="utf-8")
                fixed += 1
    return fixed


def build_wikilink_reverse_map(wiki_root: Path) -> dict[str, set[str]]:
    """Build reverse map from source page wikilinks."""
    concept_pages: dict[str, str] = {}
    for d in ("wiki/concepts", "wiki/entities"):
        full_dir = wiki_root / d
        if not full_dir.is_dir():
            continue
        for f in full_dir.glob("*.md"):
            concept_pages[f.stem] = str(Path(d) / f.name)

    reverse_map: dict[str, set[str]] = {}
    sources_dir = wiki_root / "wiki" / "sources"
    for f in sources_dir.glob("*.md"):
        source_name = f.stem
        content = f.read_text(encoding="utf-8")
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        for link in links:
            link = link.split("|")[0].strip()
            if link in concept_pages:
                fp = concept_pages[link]
                reverse_map.setdefault(fp, set()).add(source_name)
    return reverse_map


def build_extract_reverse_map(wiki_root: Path) -> dict[str, set[str]]:
    """Build reverse map from extract JSON files."""
    name_to_file: dict[str, str] = {}
    for d in ("wiki/concepts", "wiki/entities"):
        full_dir = wiki_root / d
        if not full_dir.is_dir():
            continue
        for f in full_dir.glob("*.md"):
            name_to_file[f.stem] = str(Path(d) / f.name)

    source_title_map: dict[str, str] = {}
    sources_dir = wiki_root / "wiki" / "sources"
    for f in sorted(sources_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm, _, _ = parse_frontmatter(text)
        if fm:
            title = fm.get("title", "").strip('"').strip("'")
            title_slug = slugify(title)
            source_title_map[title_slug] = f.stem

    reverse_map: dict[str, set[str]] = {}
    meta_dir = wiki_root / "wiki" / "meta"
    for ef in meta_dir.glob("extract-*.json"):
        data = json.loads(ef.read_text(encoding="utf-8"))
        title = data.get("title", "")
        title_slug = slugify(title)
        source_match = source_title_map.get(title_slug)
        if not source_match:
            continue

        for item_list in (data.get("concepts", []), data.get("entities", [])):
            for item in item_list:
                name = item.get("name", "")
                name_slug = slugify(name)
                if name_slug in name_to_file:
                    fp = name_to_file[name_slug]
                    reverse_map.setdefault(fp, set()).add(source_match)

    return reverse_map


def build_body_wikilink_map(wiki_root: Path) -> dict[str, set[str]]:
    """Build map by scanning concept/entity page bodies for source page wikilinks."""
    source_names = {f.stem for f in (wiki_root / "wiki" / "sources").glob("*.md")}

    body_map: dict[str, set[str]] = {}
    for d in ("wiki/concepts", "wiki/entities"):
        full_dir = wiki_root / d
        if not full_dir.is_dir():
            continue
        for f in full_dir.glob("*.md"):
            rel_path = str(Path(d) / f.name)
            text = f.read_text(encoding="utf-8")

            # Only scan body (after frontmatter)
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            body = parts[2]

            links = re.findall(r"\[\[([^\]]+)\]\]", body)
            found_sources: set[str] = set()
            for link in links:
                link = link.split("|")[0].strip()
                if link in source_names:
                    found_sources.add(link)

            if found_sources:
                body_map[rel_path] = found_sources

    return body_map


def build_keyword_reverse_map(
    wiki_root: Path, remaining_pages: list[str],
) -> dict[str, set[str]]:
    """Build map by searching source page bodies for page titles/keywords."""
    sources_dir = wiki_root / "wiki" / "sources"
    sources: dict[str, str] = {}
    for f in sources_dir.glob("*.md"):
        sources[f.stem] = f.read_text(encoding="utf-8")

    reverse_map: dict[str, set[str]] = {}
    for rel_path in remaining_pages:
        full_path = wiki_root / rel_path
        text = full_path.read_text(encoding="utf-8")

        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        raw_fm = parts[1]
        title_match = re.search(r'^title:\s*"?([^"\n]+)"?', raw_fm, re.MULTILINE)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        # Skip very generic titles (too many matches)
        generic = {"因子", "债券", "打新"}
        if title in generic:
            continue

        # Search source bodies for exact title match
        matches: set[str] = set()
        for sname, content in sources.items():
            if re.search(re.escape(title), content, re.IGNORECASE):
                matches.add(sname)

        # If no exact match, try splitting title into parts
        if not matches:
            title_parts = re.split(
                r'(?<=[一-鿿])(?=[A-Za-z])|(?<=[A-Za-z])(?=[一-鿿])|[·\-—]',
                title,
            )
            title_parts = [p.strip() for p in title_parts if len(p.strip()) >= 2]
            for sname, content in sources.items():
                for part in title_parts:
                    if re.search(re.escape(part), content, re.IGNORECASE):
                        matches.add(sname)
                        break

        if matches:
            reverse_map[rel_path] = matches

    return reverse_map


def _inject_sources(raw_fm: str, source_names: list[str]) -> str:
    """Inject sources into frontmatter, creating the field if needed."""
    new_sources = [f"[[{s}]]" for s in source_names]
    has_sources_field = bool(re.search(r"^sources:", raw_fm, re.MULTILINE))
    if has_sources_field:
        return merge_array_field(raw_fm, "sources", new_sources)
    # Inject sources field before 'origin:' or at end
    sources_block = "sources:\n" + "\n".join(f'  - "{s}"' for s in new_sources)
    if "origin:" in raw_fm:
        return re.sub(r"(\norigin:)", f"\n{sources_block}\\1", raw_fm)
    return raw_fm.rstrip() + "\n" + sources_block


def main(wiki_root: str) -> None:
    wiki_root = Path(wiki_root).resolve()

    # Step 0: Fix malformed frontmatter
    fm_fixed = fix_frontmatter_blanks(wiki_root)
    if fm_fixed:
        print(f"Fixed frontmatter blanks in {fm_fixed} pages")

    # Build all reverse maps (strategies 1-3)
    wikilink_map = build_wikilink_reverse_map(wiki_root)
    extract_map = build_extract_reverse_map(wiki_root)
    body_map = build_body_wikilink_map(wiki_root)

    # Merge: combine all sources
    combined: dict[str, set[str]] = {}
    for src_map in (wikilink_map, extract_map, body_map):
        for fp, sources in src_map.items():
            combined.setdefault(fp, set()).update(sources)

    # First pass: fix what we can with strategies 1-3
    fixed = 0
    skipped_has_sources = 0
    skipped_seed = 0
    unfixable: list[str] = []

    for d in ("wiki/concepts", "wiki/entities"):
        full_dir = wiki_root / d
        if not full_dir.is_dir():
            continue
        for f in sorted(full_dir.glob("*.md")):
            rel_path = str(Path(d) / f.name)
            text = f.read_text(encoding="utf-8")

            fm, body, raw_fm = parse_frontmatter(text)
            if fm is None:
                continue

            existing_sources = _extract_existing_list_items(raw_fm, "sources")
            status = fm.get("status", "seed")

            if status == "seed":
                skipped_seed += 1
                continue

            if existing_sources:
                skipped_has_sources += 1
                continue

            if rel_path not in combined:
                unfixable.append(rel_path)
                continue

            source_names = sorted(combined[rel_path])
            new_raw_fm = _inject_sources(raw_fm, source_names)
            new_content = f"---\n{new_raw_fm}\n---{body}"

            f.write_text(new_content, encoding="utf-8")
            fixed += 1

    print(f"Fixed (strategies 1-3): {fixed}")

    # Second pass: keyword search for remaining unfixable
    if unfixable:
        keyword_map = build_keyword_reverse_map(wiki_root, unfixable)
        kw_fixed = 0
        still_unfixable: list[str] = []

        for rel_path in unfixable:
            if rel_path not in keyword_map:
                still_unfixable.append(rel_path)
                continue

            full_path = wiki_root / rel_path
            text = full_path.read_text(encoding="utf-8")

            fm, body, raw_fm = parse_frontmatter(text)
            if fm is None:
                still_unfixable.append(rel_path)
                continue

            source_names = sorted(keyword_map[rel_path])
            new_raw_fm = _inject_sources(raw_fm, source_names)
            new_content = f"---\n{new_raw_fm}\n---{body}"

            full_path.write_text(new_content, encoding="utf-8")
            kw_fixed += 1

        print(f"Fixed (keyword strategy): {kw_fixed}")
        unfixable = still_unfixable

    print(f"Skipped (already have sources): {skipped_has_sources}")
    print(f"Skipped (seed status): {skipped_seed}")
    print(f"Remaining unfixable: {len(unfixable)}")
    if unfixable:
        print("\nUnfixable pages:")
        for p in unfixable:
            print(f"  {p}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_empty_sources.py <wiki-root>")
        sys.exit(1)
    main(sys.argv[1])
