#!/usr/bin/env python3
"""
lint_wiki.py — Health check for an LLM Wiki.

Usage:
    python3 lint_wiki.py <wiki-root>

Example:
    python3 lint_wiki.py ~/wikis/ai-research

Checks:
  1. Dead wikilinks — [[Target]] where Target.md doesn't exist
  2. Orphan pages — wiki pages with no inbound links
  3. Missing index entries — wiki pages not listed in wiki/index.md
  4. Unlinked concepts — terms mentioned 3+ times but lacking their own page
  5. log/ shape — every file matches YYYY-MM-DD.md and has the right H1
  6. audit/ shape — every audit/*.md parses as a valid AuditEntry
  7. Audit targets — every open audit's `target` file must exist
  8. raw_path existence — source pages' raw_path must point to a real file
  9. Tag taxonomy — tags on wiki pages must appear in the CLAUDE.md taxonomy (if defined)
  10. Stale pages — pages with review_by date in the past
  11. Filename case — wiki page filenames must be all lowercase
  12. Source pages shouldn't have a sources field
  13. overview.md exists — wiki/overview.md must be present
  14. Inline wikilink density — pages with >= 80 words of body should have at least 2 inline wikilinks
  15. Non-ASCII filename — concept/entity pages should use Chinese filenames, not pure-ASCII
  16. Frontmatter sanitization — auto-fix code-fence wrappers, `frontmatter:` prefixes, invalid wikilink lists
  17. Duplicate index entries — same [[target]] appearing 2+ times in one index.md section
  18. Case-insensitive duplicate entries — [[PEAD效应]] and [[pead效应]] coexisting in same section
  19. Cross-directory slug collisions — same filename in different wiki subdirectories
  20. Thin pages — pages with fewer than 15 words of body content
  21. Non-seed empty sources — concept/entity pages with status != seed but sources empty

Exit codes:
  0 — no issues found
  1 — issues found (printed to stdout)
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def count_words(text: str) -> int:
    """Count words in mixed Chinese/English text.

    Chinese characters are counted individually (each hanzi = 1 word).
    English/ASCII tokens are counted after whitespace splitting (len > 1).
    """
    hanzi = len(re.findall(r'[\u4e00-\u9fff]', text))
    # Remove Chinese characters then count remaining whitespace-separated tokens
    remainder = re.sub(r'[\u4e00-\u9fff]', ' ', text)
    ascii_words = len([w for w in remainder.split() if len(w) > 1])
    return hanzi + ascii_words

# Ensure stdout handles Unicode on Windows (GBK console default)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
LOG_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_LIST_IN_FM_RE = re.compile(
    r"^(\s*[A-Za-z_][\w-]*\s*:\s*)(\[\[[^\]]+\]\](?:\s*,\s*\[\[[^\]]+\]\])+)\s*$",
    re.MULTILINE,
)

# Required audit frontmatter fields
AUDIT_REQUIRED_FIELDS = {
    "id", "target", "target_lines", "anchor_before", "anchor_text",
    "anchor_after", "severity", "author", "source", "created", "status",
}
VALID_SEVERITIES = {"info", "suggest", "warn", "error"}
VALID_STATUSES = {"open", "resolved"}
VALID_SOURCES = {"obsidian-plugin", "web-viewer", "manual"}


# ── Sanitize helpers (ported from llm_wiki's ingest-sanitize.ts) ────────────


def _strip_outer_code_fence(content: str) -> str:
    """Strip ```yaml/```md/```markdown/``` wrapper when it wraps the whole doc."""
    open_match = re.match(r"^```(?:yaml|md|markdown)?[ \t]*\r?\n", content)
    if not open_match:
        return content
    after_open = content[open_match.end():]
    # Closing fence: a final ``` on its own line, optionally followed by whitespace/newlines
    close_match = re.search(r"\r?\n```[ \t]*\r?\n?\s*$", after_open)
    if not close_match:
        return content
    return after_open[:close_match.start()] + "\n"


def _strip_frontmatter_key_prefix(content: str) -> str:
    """Strip a stray `frontmatter:` line before the real --- block."""
    m = re.match(r"^[ \t]*frontmatter\s*:\s*\r?\n(?=[ \t]*---\s*\r?\n)", content)
    if not m:
        return content
    return content[m.end():]


def _repair_wikilink_lists_in_frontmatter(content: str) -> str:
    """Fix `key: [[a]], [[b]]` inside the frontmatter block to valid YAML."""
    fm_match = re.match(r"^(---\s*\r?\n)([\s\S]*?)(\r?\n---\s*(?:\r?\n|$))", content)
    if not fm_match:
        return content

    open_delim, fm_body, close_delim = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    body = content[fm_match.end():]

    repaired_lines = []
    for line in fm_body.split("\n"):
        m = WIKILINK_LIST_IN_FM_RE.match(line)
        if m:
            prefix = m.group(1)
            items = ", ".join(
                f'"{s.strip()}"'
                for s in m.group(2).split(",")
                if s.strip()
            )
            repaired_lines.append(f"{prefix}[{items}]")
        else:
            repaired_lines.append(line)

    return open_delim + "\n".join(repaired_lines) + close_delim + body


def sanitize_frontmatter(content: str) -> str:
    """Clean up LLM-generated frontmatter before it hits disk.

    Fixes three recurring shapes:
      1. Whole page wrapped in ```yaml ... ``` code fence
      2. Stray `frontmatter:` key before the real --- block
      3. Invalid wikilink lists: `related: [[a]], [[b]]`
    """
    content = _strip_outer_code_fence(content)
    content = _strip_frontmatter_key_prefix(content)
    content = _repair_wikilink_lists_in_frontmatter(content)
    return content


def load_pages(wiki_dir: Path) -> dict[str, Path]:
    pages: dict[str, Path] = {}
    for p in wiki_dir.rglob("*.md"):
        pages[p.stem] = p
        pages[p.stem.lower()] = p
        rel = p.relative_to(wiki_dir)
        rel_str = str(rel.with_suffix(""))
        pages[rel_str] = p
        pages[rel_str.lower()] = p
    return pages


def extract_wikilinks(text: str) -> list[str]:
    return WIKILINK_RE.findall(text)


def parse_frontmatter(text: str) -> dict | None:
    """Minimal YAML-ish frontmatter parser. Handles the flat key:value fields
    and one-level lists/arrays actually used by audit files. Does not handle
    arbitrary YAML — intentional, to avoid a pyyaml dependency."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body = m.group(1)
    result: dict = {}
    i = 0
    lines = body.split("\n")
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        val = rest.strip()
        # Inline array: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                parts = [p.strip() for p in inner.split(",")]
                parsed: list = []
                for p in parts:
                    if p.isdigit() or (p.startswith("-") and p[1:].isdigit()):
                        parsed.append(int(p))
                    else:
                        parsed.append(p.strip('"').strip("'"))
                result[key] = parsed
        # Multiline list: key:\n  - value1\n  - value2
        elif val == "":
            items: list = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if next_line.lstrip().startswith("- ") and next_line.startswith(" "):
                    item = next_line.strip()[2:].strip()
                    item = item.strip('"').strip("'")
                    if item:
                        items.append(item)
                    j += 1
                else:
                    break
            if items:
                result[key] = items
                i = j
                continue
        elif val.startswith('"') and val.endswith('"'):
            result[key] = val[1:-1].replace("\\n", "\n").replace('\\"', '"')
        elif val.startswith("'") and val.endswith("'"):
            result[key] = val[1:-1]
        else:
            result[key] = val
        i += 1
    return result


def load_tag_taxonomy(root_path: Path) -> set[str] | None:
    """Load the tag taxonomy from CLAUDE.md. Returns None if no taxonomy found."""
    for schema_name in ("CLAUDE.md", "_schema/CLAUDE.md", "SCHEMA.md"):
        schema_path = root_path / schema_name
        if not schema_path.exists():
            continue
        text = schema_path.read_text(encoding="utf-8")
        in_taxonomy = False
        tags: set[str] = set()
        for line in text.split("\n"):
            stripped = line.strip()
            if "tag taxonomy" in stripped.lower():
                in_taxonomy = True
                continue
            if in_taxonomy and stripped.startswith("## ") and "tag" not in stripped.lower():
                if tags:
                    return tags
                continue
            if in_taxonomy and stripped.startswith("- **"):
                import re as _re
                m = _re.match(r"-\s+\*\*[^*]+\*\*:\s*(.+)", stripped)
                if m:
                    for tag in m.group(1).split(","):
                        t = tag.strip().rstrip(",")
                        if t:
                            tags.add(t.lower())
            elif in_taxonomy and stripped.startswith("- ") and not stripped.startswith("- [") and not stripped.startswith("- **"):
                tag = stripped[2:].strip().rstrip(",")
                if tag and not tag.startswith("*") and not tag.startswith("["):
                    tags.add(tag.lower())
        if tags:
            return tags
    return None


def lint(root: str) -> int:
    root_path = Path(root)
    wiki_path = root_path / "wiki"
    log_path = root_path / "log"
    audit_path = root_path / "audit"

    if not wiki_path.exists():
        print(f"ERROR: wiki/ directory not found at {wiki_path}", file=sys.stderr)
        return 1

    pages = load_pages(wiki_path)
    all_wiki_files = list(wiki_path.rglob("*.md"))
    index_path = wiki_path / "index.md"

    issues = 0
    inbound: dict[str, list[str]] = defaultdict(list)

    # ── Pass 1: dead wikilinks ──────────────────────────────────────────────
    dead_links: list[tuple[str, str]] = []
    for md_file in all_wiki_files:
        text = md_file.read_text(encoding="utf-8")
        for link in extract_wikilinks(text):
            link = link.strip()
            if (link not in pages and link.lower() not in pages
                    and Path(link).stem not in pages and Path(link).stem.lower() not in pages):
                dead_links.append((str(md_file.relative_to(root_path)), link))
            else:
                target = (pages.get(link) or pages.get(link.lower())
                          or pages.get(Path(link).stem) or pages.get(Path(link).stem.lower()))
                if target:
                    inbound[target.stem].append(md_file.stem)

    if dead_links:
        print(f"\n🔴 Dead wikilinks ({len(dead_links)}):")
        for source, link in dead_links:
            print(f"   {source} → [[{link}]]")
        issues += len(dead_links)
    else:
        print("✅ No dead wikilinks")

    # ── Pass 2: orphan pages ────────────────────────────────────────────────
    skip_orphan = {"index", "overview", "index-summary"}
    orphans = [
        p for p in all_wiki_files
        if p.stem not in inbound and p.stem not in skip_orphan
        and p.parent != wiki_path  # skip index.md, overview.md at root
    ]
    if orphans:
        print(f"\n🟡 Orphan pages ({len(orphans)}) — no inbound wikilinks:")
        for p in orphans:
            print(f"   {p.relative_to(root_path)}")
        issues += len(orphans)
    else:
        print("✅ No orphan pages")

    # ── Pass 3: missing index entries ───────────────────────────────────────
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        overview_path = wiki_path / "overview.md"
        summary_path = wiki_path / "index-summary.md"
        not_in_index = [
            p for p in all_wiki_files
            if p != index_path
            and p != overview_path
            and p != summary_path
            and f"[[{p.stem}]]" not in index_text
            and f"[[{p.stem}|" not in index_text
            and str(p.relative_to(wiki_path).with_suffix("")) not in index_text
        ]
        if not_in_index:
            print(f"\n🟡 Pages missing from index.md ({len(not_in_index)}):")
            for p in not_in_index:
                print(f"   {p.relative_to(root_path)}")
            issues += len(not_in_index)
        else:
            print("✅ All pages in index.md")
    else:
        print("⚠️  wiki/index.md not found — skipping index check")

    # ── Pass 4: unlinked concepts ───────────────────────────────────────────
    all_text = " ".join(p.read_text(encoding="utf-8") for p in all_wiki_files)
    all_links = WIKILINK_RE.findall(all_text)
    link_counts: dict[str, int] = defaultdict(int)
    for link in all_links:
        link_counts[link.strip()] += 1

    missing_pages = [
        (link, count) for link, count in link_counts.items()
        if count >= 3 and link not in pages and link.lower() not in pages
        and Path(link).stem not in pages and Path(link).stem.lower() not in pages
    ]
    if missing_pages:
        print(f"\n🟡 Frequently linked but no page ({len(missing_pages)}):")
        for link, count in sorted(missing_pages, key=lambda x: -x[1]):
            print(f"   [[{link}]] — mentioned {count}x")
        issues += len(missing_pages)
    else:
        print("✅ No frequently-linked missing pages")

    # ── Pass 5: log/ shape ───────────────────────────────────────────────────
    if log_path.exists() and log_path.is_dir():
        log_issues: list[str] = []
        for p in sorted(log_path.iterdir()):
            if p.is_dir():
                continue
            if p.name == ".gitkeep":
                continue
            m = LOG_FILENAME_RE.match(p.name)
            if not m:
                log_issues.append(f"   {p.relative_to(root_path)} — filename doesn't match YYYY-MM-DD.md")
                continue
            y, mo, d = m.groups()
            iso = f"{y}-{mo}-{d}"
            first_line = p.read_text(encoding="utf-8").splitlines()[:1]
            if not first_line or first_line[0].strip() != f"# {iso}":
                log_issues.append(f"   {p.relative_to(root_path)} — expected H1 '# {iso}'")
        if log_issues:
            print(f"\n🟡 log/ shape issues ({len(log_issues)}):")
            for s in log_issues:
                print(s)
            issues += len(log_issues)
        else:
            print("✅ log/ shape OK")
    else:
        print("⚠️  log/ directory not found — skipping log shape check")

    # ── Pass 6: audit/ shape ─────────────────────────────────────────────────
    audit_targets_to_check: list[tuple[str, str]] = []  # (audit_id, target)
    if audit_path.exists() and audit_path.is_dir():
        audit_files = [
            p for p in audit_path.rglob("*.md") if p.name != ".gitkeep"
        ]
        audit_issues: list[str] = []
        for p in audit_files:
            text = p.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            rel = p.relative_to(root_path)
            if fm is None:
                audit_issues.append(f"   {rel} — missing YAML frontmatter")
                continue
            missing = AUDIT_REQUIRED_FIELDS - set(fm.keys())
            if missing:
                audit_issues.append(
                    f"   {rel} — missing fields: {', '.join(sorted(missing))}"
                )
                continue
            if fm["severity"] not in VALID_SEVERITIES:
                audit_issues.append(
                    f"   {rel} — invalid severity '{fm['severity']}' (expected {sorted(VALID_SEVERITIES)})"
                )
            if fm["source"] not in VALID_SOURCES:
                audit_issues.append(
                    f"   {rel} — invalid source '{fm['source']}'"
                )
            expected_status = "resolved" if "resolved" in p.parts else "open"
            if fm["status"] != expected_status:
                audit_issues.append(
                    f"   {rel} — status '{fm['status']}' doesn't match directory (expected '{expected_status}')"
                )
            if fm["status"] == "open":
                audit_targets_to_check.append((fm["id"], fm["target"]))

        if audit_issues:
            print(f"\n🔴 audit/ shape issues ({len(audit_issues)}):")
            for s in audit_issues:
                print(s)
            issues += len(audit_issues)
        else:
            print(f"✅ audit/ shape OK ({len(audit_files)} files)")
    else:
        print("⚠️  audit/ directory not found — skipping audit shape check")

    # ── Pass 7: audit targets exist ──────────────────────────────────────────
    missing_targets: list[tuple[str, str]] = []
    for audit_id, target in audit_targets_to_check:
        target_path = root_path / target
        # Audit target paths are relative to wiki-root but typically point
        # at files under wiki/. Check both locations.
        if not target_path.exists():
            alt = wiki_path / target
            if not alt.exists():
                missing_targets.append((audit_id, target))
    if missing_targets:
        print(f"\n🔴 Open audits with missing target files ({len(missing_targets)}):")
        for audit_id, target in missing_targets:
            print(f"   {audit_id} → {target}")
        issues += len(missing_targets)
    elif audit_targets_to_check:
        print("✅ All open-audit targets exist")

    # ── Pass 8: raw_path existence + hash auto-fix ────────────────────────
    import hashlib as _hashlib
    missing_raw: list[tuple[str, str]] = []
    hash_fixed: list[str] = []
    for md_file in all_wiki_files:
        text = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm and fm.get("raw_path"):
            raw_rel = fm["raw_path"].strip('"').strip("'")
            if raw_rel:
                raw_full = root_path / raw_rel
                if not raw_full.exists():
                    missing_raw.append(
                        (str(md_file.relative_to(root_path)), raw_rel)
                    )
                elif fm.get("raw_hash"):
                    stored_hash = str(fm["raw_hash"]).strip('"').strip("'")
                    actual_hash = _hashlib.sha256(raw_full.read_bytes()).hexdigest()
                    if stored_hash and stored_hash != actual_hash:
                        new_text = text.replace(stored_hash, actual_hash)
                        md_file.write_text(new_text, encoding="utf-8")
                        hash_fixed.append(str(md_file.relative_to(root_path)))
    if missing_raw:
        print(f"\n🟡 Source pages with missing raw_path ({len(missing_raw)}):")
        for page, raw in missing_raw:
            print(f"   {page} → {raw}")
        issues += len(missing_raw)
    else:
        print("✅ All source raw_path references exist")
    if hash_fixed:
        print(f"\n🔧 Auto-fixed raw_hash ({len(hash_fixed)}):")
        for page in hash_fixed:
            print(f"   {page}")
    else:
        print("✅ All raw_hash values match current source files")
    # Check: source pages with raw_path but missing raw_hash
    missing_hash: list[str] = []
    for md_file in all_wiki_files:
        text = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm and fm.get("raw_path") and not fm.get("raw_hash"):
            raw_rel = fm["raw_path"].strip('"').strip("'")
            if raw_rel:
                missing_hash.append(str(md_file.relative_to(root_path)))
    if missing_hash:
        print(f"\n🟡 Source pages missing raw_hash ({len(missing_hash)}):")
        for page in missing_hash:
            print(f"   {page}")
        issues += len(missing_hash)

    # ── Pass 9: tag taxonomy ──────────────────────────────────────────────
    taxonomy = load_tag_taxonomy(root_path)
    if taxonomy:
        invalid_tags: list[tuple[str, str]] = []
        for md_file in all_wiki_files:
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm and fm.get("tags"):
                tags_val = fm["tags"]
                if isinstance(tags_val, list):
                    page_tags = [str(t).lower().strip() for t in tags_val]
                else:
                    page_tags = [str(tags_val).lower().strip()]
                for tag in page_tags:
                    if tag and tag not in taxonomy:
                        invalid_tags.append(
                            (str(md_file.relative_to(root_path)), tag)
                        )
        if invalid_tags:
            print(f"\n🟡 Tags not in taxonomy ({len(invalid_tags)}):")
            for page, tag in invalid_tags:
                print(f'   {page}: "{tag}"')
            issues += len(invalid_tags)
        else:
            print("✅ All tags are in the taxonomy")
    else:
        print("⚠️  No tag taxonomy found in CLAUDE.md — skipping tag check")

    # ── Pass 10: stale pages (review_by) ──────────────────────────────────
    from datetime import date as _date
    today = _date.today()
    stale_pages: list[tuple[str, str]] = []
    for md_file in all_wiki_files:
        text = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm and fm.get("review_by"):
            review_date_str = str(fm["review_by"]).strip().strip('"').strip("'")
            if review_date_str:
                try:
                    review_date = _date.fromisoformat(review_date_str)
                    if review_date < today:
                        stale_pages.append(
                            (str(md_file.relative_to(root_path)), review_date_str)
                        )
                except ValueError:
                    pass
    if stale_pages:
        print(f"\n🟡 Pages past review date ({len(stale_pages)}):")
        for page, review_date in stale_pages:
            print(f"   {page} — review_by: {review_date}")
        issues += len(stale_pages)
    else:
        print("✅ No pages past review date")

    # ── Pass 11: filename case ────────────────────────────────────────────
    uppercase_names: list[str] = []
    for md_file in all_wiki_files:
        if md_file.stem != md_file.stem.lower():
            uppercase_names.append(str(md_file.relative_to(root_path)))
    if uppercase_names:
        print(f"\n🟡 Uppercase filenames ({len(uppercase_names)}):")
        for name in uppercase_names:
            print(f"   {name}")
        issues += len(uppercase_names)
    else:
        print("✅ All filenames are lowercase")

    # ── Pass 12: source pages should not have sources field ────────────────
    source_with_sources: list[str] = []
    for md_file in all_wiki_files:
        if md_file.parent.name == "sources":
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm and fm.get("sources") is not None:
                source_with_sources.append(str(md_file.relative_to(root_path)))
    if source_with_sources:
        print(f"\n🟡 Source pages with sources field ({len(source_with_sources)}):")
        for page in source_with_sources:
            print(f"   {page}")
        issues += len(source_with_sources)
    else:
        print("✅ No source pages with sources field")

    # ── Pass 13: overview.md exists ─────────────────────────────────
    overview_path = wiki_path / "overview.md"
    if not overview_path.exists():
        print("❌ wiki/overview.md is missing — run scaffold to create it, then update during ingest")
        issues += 1
    else:
        print("✅ overview.md exists")

    # ── Pass 14: Inline wikilink density ─────────────────────────────
    # Pages with >= 80 words of body content should have at least 2 inline [[wikilink]]s
    # in their body (outside of Related Pages / Sources sections and frontmatter).
    low_density: list[tuple[str, int, int]] = []
    for md_file in all_wiki_files:
        if md_file.name in ("index.md", "overview.md"):
            continue
        rel = str(md_file.relative_to(wiki_path))
        parts = md_file.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        body = parts[2]
        # Strip Related Pages, Sources, Open Questions sections and human blocks
        body_clean = re.sub(
            r"## (Related Pages|Sources|Open Questions).*?(?=## |$)",
            "", body, flags=re.DOTALL,
        )
        body_clean = re.sub(r"<!-- human:start -->.*?<!-- human:end -->", "", body_clean, flags=re.DOTALL)
        # Count words (handles Chinese chars individually)
        words = count_words(body_clean)
        if words < 80:
            continue
        # Count inline wikilinks in the cleaned body
        inline_links = re.findall(r"\[\[([^\]]+)\]\]", body_clean)
        inline_link_count = len(inline_links)
        if inline_link_count < 2:
            low_density.append((rel, words, inline_link_count))
    if low_density:
        print(f"\n⚠️  {len(low_density)} page(s) with fewer than 2 inline wikilinks in body (>= 80 words):")
        for path, wc, lc in low_density:
            print(f"   {path} ({wc} words, {lc} inline links)")
        issues += len(low_density)
    else:
        print("✅ All pages with substantial body content have inline wikilinks")

    # ── Pass 15: Non-ASCII filename for concept/entity pages ──────────
    # Concept and entity pages should use Chinese filenames, not pure-ASCII English.
    # Source pages are exempt (raw article titles may be English).
    ascii_names: list[str] = []
    for md_file in all_wiki_files:
        rel = str(md_file.relative_to(wiki_path))
        parts = rel.replace("\\", "/").split("/")
        if len(parts) < 2:
            continue
        subdir = parts[0]  # concepts, entities, sources, etc.
        if subdir not in ("concepts", "entities"):
            continue
        stem = md_file.stem
        # Pure ASCII = all characters are in range 0-127
        if stem.isascii() and stem:
            ascii_names.append(rel)
    if ascii_names:
        print(f"\n⚠️  {len(ascii_names)} concept/entity page(s) with pure-ASCII (English) filenames:")
        for name in ascii_names:
            print(f"   {name} — use Chinese filename instead")
        issues += len(ascii_names)
    else:
        print("✅ All concept/entity pages have non-ASCII (Chinese) filenames")

    # ── Pass 16: frontmatter sanitization (auto-fix) ─────────────────────
    sanitize_fixed: list[tuple[str, str]] = []
    for md_file in all_wiki_files:
        if md_file.name in ("index.md", "overview.md"):
            continue
        text = md_file.read_text(encoding="utf-8")
        cleaned = sanitize_frontmatter(text)
        if cleaned != text:
            rel = str(md_file.relative_to(root_path))
            # Identify which fixes applied
            fixes: list[str] = []
            if _strip_outer_code_fence(text) != text:
                fixes.append("code-fence wrapper")
            after_fence = _strip_outer_code_fence(text)
            if _strip_frontmatter_key_prefix(after_fence) != after_fence:
                fixes.append("frontmatter: prefix")
            if _repair_wikilink_lists_in_frontmatter(after_fence) != after_fence:
                fixes.append("wikilink list format")
            md_file.write_text(cleaned, encoding="utf-8")
            sanitize_fixed.append((rel, ", ".join(fixes)))
    if sanitize_fixed:
        print(f"\n🔧 Auto-fixed frontmatter ({len(sanitize_fixed)}):")
        for path, fix in sanitize_fixed:
            print(f"   {path} — {fix}")
    else:
        print("✅ No frontmatter sanitization issues")

    # ── Pass 17: duplicate index entries (exact match per section) ────────
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        # Split index into sections by ## headings
        section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        section_starts = [(m.group(1).strip(), m.start()) for m in section_pattern.finditer(index_text)]
        dup_index_issues: list[tuple[str, str, int]] = []  # (section, target, count)
        for si, (sec_name, sec_start) in enumerate(section_starts):
            sec_end = section_starts[si + 1][1] if si + 1 < len(section_starts) else len(index_text)
            sec_body = index_text[sec_start:sec_end]
            targets_in_sec = re.findall(r"-\s*\[\[([^\]|]+)", sec_body)
            from collections import Counter as _Counter
            for target, cnt in _Counter(targets_in_sec).items():
                if cnt > 1:
                    dup_index_issues.append((sec_name, target, cnt))
        if dup_index_issues:
            print(f"\n🟡 Duplicate index entries ({len(dup_index_issues)}):")
            for sec, target, cnt in dup_index_issues:
                print(f"   ## {sec}: [[{target}]] ×{cnt}")
            issues += len(dup_index_issues)
        else:
            print("✅ No duplicate index entries")
    else:
        print("⚠️  wiki/index.md not found — skipping duplicate index check")

    # ── Pass 18: case-insensitive duplicate index entries ─────────────────
    # On macOS (APFS) and Windows (NTFS), [[PEAD效应]] and [[pead效应]] point to
    # the SAME file. This check catches index.md entries that differ only in case.
    # IMPORTANT: Fix by deduplicating index.md ONLY. Do NOT delete files — they
    # are the same inode on case-insensitive filesystems.
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        section_pattern2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        section_starts2 = [(m.group(1).strip(), m.start()) for m in section_pattern2.finditer(index_text)]
        case_dup_issues: list[tuple[str, list[str]]] = []  # (section, [variants])
        for si, (sec_name, sec_start) in enumerate(section_starts2):
            sec_end = section_starts2[si + 1][1] if si + 1 < len(section_starts2) else len(index_text)
            sec_body = index_text[sec_start:sec_end]
            targets = re.findall(r"-\s*\[\[([^\]|]+)", sec_body)
            lower_map: dict[str, list[str]] = defaultdict(list)
            for t in targets:
                lower_map[t.lower()].append(t)
            for _low, variants in lower_map.items():
                unique_variants = list(set(variants))
                if len(unique_variants) > 1:
                    case_dup_issues.append((sec_name, unique_variants))
        if case_dup_issues:
            print(f"\n🟡 Case-insensitive duplicate index entries ({len(case_dup_issues)}):")
            print("   ⚠️  Fix: deduplicate index.md entries ONLY. Do NOT delete files (case-insensitive FS: macOS/Windows).", file=sys.stderr)
            for sec, variants in case_dup_issues:
                print(f"   ## {sec}: {' / '.join(variants)}")
            issues += len(case_dup_issues)
        else:
            print("✅ No case-insensitive duplicate index entries")
    else:
        print("⚠️  wiki/index.md not found — skipping case-insensitive duplicate check")

    # ── Pass 19: cross-directory slug collisions ──────────────────────────
    slug_dirs: dict[str, list[str]] = defaultdict(list)  # stem → [rel_paths]
    for md_file in all_wiki_files:
        rel = str(md_file.relative_to(wiki_path))
        parts = rel.replace("\\", "/").split("/")
        if len(parts) < 2:
            continue
        slug_dirs[md_file.stem].append(rel)
    cross_dir_collisions = {k: v for k, v in slug_dirs.items() if len(v) > 1}
    if cross_dir_collisions:
        print(f"\n🟡 Cross-directory slug collisions ({len(cross_dir_collisions)}):")
        for stem, paths in cross_dir_collisions.items():
            print(f"   {stem}: {' vs '.join(paths)}")
        issues += len(cross_dir_collisions)
    else:
        print("✅ No cross-directory slug collisions")

    # ── Pass 20: thin pages (< 15 words of body) ─────────────────────────
    thin_pages: list[tuple[str, int]] = []  # (rel_path, word_count)
    for md_file in all_wiki_files:
        if md_file.name in ("index.md", "overview.md", "index-summary.md"):
            continue
        text = md_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        body = parts[2].strip()
        wc = count_words(body)
        if wc < 15:
            rel = str(md_file.relative_to(root_path))
            thin_pages.append((rel, wc))
    if thin_pages:
        print(f"\n🟡 Thin pages (< 15 words of body, {len(thin_pages)}):")
        for path, wc in thin_pages:
            print(f"   {path} ({wc} words)")
        issues += len(thin_pages)
    else:
        print("✅ No thin pages")

    # ── Pass 21: non-seed pages with empty sources ───────────────────────────
    # Concept/entity pages with status != seed should have sources populated.
    # This catches pipeline regressions where _create_page() fails to pass sources.
    from merge_frontmatter import _extract_existing_list_items as _eli
    empty_sources_non_seed: list[tuple[str, str]] = []  # (rel_path, status)
    for md_file in all_wiki_files:
        rel = str(md_file.relative_to(wiki_path))
        parts = rel.replace("\\", "/").split("/")
        if len(parts) < 2:
            continue
        subdir = parts[0]
        if subdir not in ("concepts", "entities"):
            continue
        text = md_file.read_text(encoding="utf-8")
        text_parts = text.split("---", 2)
        if len(text_parts) < 3:
            continue
        raw_fm = text_parts[1]
        fm = parse_frontmatter(text)
        if fm is None:
            continue
        status = str(fm.get("status", "")).strip().strip('"').strip("'")
        if status in ("seed", ""):
            continue
        existing_items = _eli(raw_fm, "sources")
        if not existing_items:
            empty_sources_non_seed.append((str(md_file.relative_to(root_path)), status))
    if empty_sources_non_seed:
        print(f"\n🟡 Non-seed pages with empty sources ({len(empty_sources_non_seed)}):")
        for path, status in empty_sources_non_seed:
            print(f"   {path} (status: {status})")
        issues += len(empty_sources_non_seed)
    else:
        print("✅ No non-seed pages with empty sources")

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    if issues == 0:
        print("✅ Wiki is healthy — no issues found")
    else:
        print(f"⚠️  {issues} issue(s) found — review above and fix before next ingest")

    return 0 if issues == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(lint(sys.argv[1]))

