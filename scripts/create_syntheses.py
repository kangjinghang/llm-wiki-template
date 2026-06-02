#!/usr/bin/env python3
"""
create_syntheses.py — Create synthesis pages from suggest_syntheses candidates.

Reads source page content for each candidate, calls the LLM API to generate
a cross-source synthesis, and writes pages using the synthesis template.

Usage:
    python scripts/create_syntheses.py <wiki-root> [options]

Options:
    --dry-run         Show what would be created without writing files
    --limit N         Process at most N candidates (default: 10)
    --min-sources N   Minimum source count (default: 3)
    --stem STEM       Process only the candidate matching this stem
    --skip-existing   Skip candidates that already have a synthesis page

Exit codes:
    0 — success
    1 — error
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from extract_knowledge import load_api_config
from suggest_syntheses import (
    build_concept_source_map,
    find_synthesis_candidates,
    load_existing_syntheses,
)


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM_PROMPT = """你是一个量化投资知识架构师。你的任务是根据多个来源页面的内容，生成一篇综合分析（synthesis）页面。

要求：
1. 用中文撰写，技术术语保留英文
2. 必须包含所有指定节标题
3. 在正文中使用 [[wikilink]] 引用来源页面和相关概念/实体
4. 使用 Mermaid 语法画图，KaTeX 写公式
5. 找出不同来源之间的分歧和矛盾
6. 提出开放性问题
7. 输出纯 markdown 内容（不要代码块包裹），从第一个 ## 开始
8. 不要写 frontmatter，只写正文
"""

SYNTHESIS_USER_TEMPLATE = """请为以下主题创建综合分析页面：

## 主题
- 名称：{title}
- 类型：{page_type}
- 相关标签：{tags}

## 需要综合的来源页面（共 {source_count} 个）

{source_contents}

## 要求的节结构

## Overview / 概述
这个综合分析解决什么问题？为什么需要把上述来源放在一起看？

## Key Findings / 核心发现
从多个来源中提炼的核心发现，每个发现标注来源 [[wikilink]]

## Tensions and Contradictions / 分歧与矛盾
不同来源之间的分歧点

## Emerging Thesis / 初步结论
基于现有证据的初步结论（标明哪些是试探性的）

## Related Pages / 关联页面
- [[]] — 关联说明

## Sources / 来源
- [[wikilink]] 列表

## Open Questions / 未解问题
- 哪些问题需要更多数据/研究来回答？

## Notes / 笔记
（留空即可）
"""


def read_source_pages(wiki_dir: Path, source_stems: list[str]) -> str:
    """Read and concatenate source page content for the prompt.

    Truncates each source to ~2000 chars to stay within context limits.
    """
    sources_dir = wiki_dir / "sources"
    chunks: list[str] = []
    max_chars = 2000

    for stem in source_stems:
        # Try exact filename match
        source_file = sources_dir / f"{stem}.md"
        if not source_file.exists():
            # Try case-insensitive match (macOS)
            for f in sources_dir.glob("*.md"):
                if f.stem.lower() == stem.lower():
                    source_file = f
                    break

        if not source_file.exists():
            chunks.append(f"### Source: {stem}\n[页面不存在]\n")
            continue

        text = source_file.read_text(encoding="utf-8")
        # Strip frontmatter
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
        body = body.strip()

        if len(body) > max_chars:
            body = body[:max_chars] + "\n...[已截断]"
        chunks.append(f"### Source: {stem}\n{body}\n")

    return "\n\n".join(chunks)


def call_llm_for_synthesis(
    config: dict,
    title: str,
    page_type: str,
    tags: list[str],
    source_count: int,
    source_contents: str,
) -> str | None:
    """Call the LLM API to generate synthesis body content.

    Returns the markdown body text, or None on failure.
    """
    user_message = SYNTHESIS_USER_TEMPLATE.format(
        title=title,
        page_type=page_type,
        tags=", ".join(tags[:10]),
        source_count=source_count,
        source_contents=source_contents,
    )

    api_url = config["base_url"].rstrip("/") + "/v1/messages"
    request_body = json.dumps({
        "model": config["model"],
        "max_tokens": 4096,
        "temperature": 0.3,
        "system": SYNTHESIS_SYSTEM_PROMPT,
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

    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            if attempt == 0:
                print(f"  WARNING: API call failed: {e}", file=sys.stderr)
                print("  Retrying...", file=sys.stderr)
            else:
                print(f"  ERROR: API call failed after retry: {e}", file=sys.stderr)
                return None

    response_text = ""
    for block in resp_data.get("content", []):
        if block.get("type") == "text":
            response_text += block.get("text", "")

    return response_text.strip() if response_text.strip() else None


# ---------------------------------------------------------------------------
# Page writing
# ---------------------------------------------------------------------------

def build_frontmatter(
    title: str,
    sources: list[str],
    tags: list[str],
) -> str:
    """Build YAML frontmatter for a synthesis page."""
    today = date.today().isoformat()
    sources_yaml = "\n".join(f'  - "[[{s}]]"' for s in sources)
    tags_str = ", ".join(tags[:10])

    return (
        "---\n"
        f'title: "{title}"\n'
        f'title_zh: "{title}"\n'
        "type: synthesis\n"
        f'summary: ""\n'  # Filled by LLM or left for manual edit
        f"tags: [{tags_str}]\n"
        f"sources:\n{sources_yaml}\n"
        "origin: agent-compiled\n"
        "status: seed\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        'review_by: ""\n'
        "---\n"
    )


def extract_summary(body: str) -> str:
    """Extract a one-line summary from the Overview section."""
    # Look for the first paragraph after ## Overview
    m = re.search(r"## Overview.*?\n\n(.+?)(?:\n\n|\n##)", body, re.DOTALL)
    if m:
        summary = m.group(1).strip()
        # Truncate to ~120 chars
        if len(summary) > 120:
            summary = summary[:117] + "..."
        return summary
    return ""


def write_synthesis_page(
    wiki_dir: Path,
    slug: str,
    title: str,
    sources: list[str],
    tags: list[str],
    body: str,
    dry_run: bool = False,
) -> Path:
    """Write a complete synthesis page to disk.

    Returns the path where the page was (or would be) written.
    """
    syn_dir = wiki_dir / "syntheses"
    filepath = syn_dir / f"{slug}.md"

    # Extract summary from body and update frontmatter
    summary = extract_summary(body)
    fm = build_frontmatter(title, sources, tags)
    if summary:
        fm = fm.replace('summary: ""', f'summary: "{summary}"')

    # Ensure body starts with # Title
    if not body.startswith("# "):
        body = f"# {title}\n\n{body}"

    # Deduplicate Notes heading if LLM generated it
    notes_pattern = r"(## Notes / 笔记\s*\n)+"
    body = re.sub(notes_pattern, "## Notes / 笔记\n", body)

    # Append human notes block if missing
    if "<!-- human:start -->" not in body:
        body += "\n\n## Notes / 笔记\n\n<!-- human:start -->\n<!-- human:end -->\n"

    content = fm + "\n" + body + "\n"

    if dry_run:
        print(f"  [DRY RUN] Would write: {filepath}")
        print(f"  Frontmatter summary: {summary or '(empty)'}")
        print(f"  Body length: {len(body)} chars")
        return filepath

    syn_dir.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create synthesis pages from suggest_syntheses candidates."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without writing files")
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum candidates to process (default: 10)")
    parser.add_argument("--min-sources", type=int, default=3,
                        help="Minimum source count (default: 3)")
    parser.add_argument("--stem", type=str, default=None,
                        help="Process only the candidate matching this stem")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip candidates that already have a synthesis page")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    if not wiki_root.exists():
        print(f"ERROR: {wiki_root} not found", file=sys.stderr)
        return 1

    wiki_dir = wiki_root / "wiki"

    # Load API config
    settings_path = Path.home() / ".claude" / "settings.json"
    config = load_api_config(settings_path)
    if config is None:
        print("ERROR: Could not load API config. Check environment variables.", file=sys.stderr)
        return 1

    # Get candidates
    existing = load_existing_syntheses(wiki_dir)
    concept_map = build_concept_source_map(wiki_dir)
    candidates = find_synthesis_candidates(concept_map, existing, args.min_sources)

    # Filter by stem if specified
    if args.stem:
        candidates = [c for c in candidates if c["stem"] == args.stem]
        if not candidates:
            print(f"ERROR: No candidate found for stem '{args.stem}'", file=sys.stderr)
            return 1

    # Filter existing
    if args.skip_existing:
        before = len(candidates)
        candidates = [c for c in candidates if c["suggested_slug"] not in existing]
        print(f"Skipped {before - len(candidates)} existing synthesis pages", file=sys.stderr)

    # Limit
    candidates = candidates[:args.limit]

    if not candidates:
        print("No candidates to process.", file=sys.stderr)
        return 0

    print(f"Processing {len(candidates)} synthesis candidates...")
    print(f"API model: {config['model']}")
    print()

    created = 0
    failed = 0

    for i, cand in enumerate(candidates, 1):
        slug = cand["suggested_slug"]
        title = cand["title"]
        source_stems = cand["sources"]
        tags = cand["tags"]
        source_count = cand["source_count"]
        page_type = cand["type"]

        print(f"[{i}/{len(candidates)}] {title}")
        print(f"  Slug: {slug}")
        print(f"  Sources: {source_count}")

        # Skip if already exists
        if (wiki_dir / "syntheses" / f"{slug}.md").exists():
            print(f"  SKIP: already exists")
            print()
            continue

        # Read source page content
        # For candidates with many sources, take top 10 by reading order
        read_stems = source_stems[:10] if len(source_stems) > 10 else source_stems
        source_contents = read_source_pages(wiki_dir, read_stems)

        if args.dry_run:
            # In dry-run, write a placeholder
            body = f"# {title}\n\n[DRY RUN placeholder — would call LLM to generate synthesis]"
            write_synthesis_page(wiki_dir, slug, title, source_stems, tags, body, dry_run=True)
            created += 1
            print()
            continue

        # Call LLM
        print(f"  Calling LLM ({len(read_stems)} sources)...", end="", file=sys.stderr)
        body = call_llm_for_synthesis(
            config, title, page_type, tags, source_count, source_contents,
        )
        print(" done", file=sys.stderr)

        if body is None:
            print(f"  FAILED: LLM returned empty response")
            failed += 1
            print()
            continue

        # Write page
        path = write_synthesis_page(wiki_dir, slug, title, source_stems, tags, body)
        summary = extract_summary(body)
        print(f"  WROTE: {path}")
        print(f"  Summary: {summary[:80]}...")
        print(f"  Body: {len(body)} chars")
        created += 1
        print()

    # Summary
    print("---")
    print(f"Created: {created}")
    print(f"Failed:  {failed}")
    print(f"Skipped: {len(candidates) - created - failed}")
    if created > 0 and not args.dry_run:
        print(f"\nNext: python scripts/lint_wiki.py {args.wiki_root}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
