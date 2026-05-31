#!/usr/bin/env python3
"""
extract_knowledge.py — Extract concepts/entities/relations from an article via LLM API.

Calls the LLM API independently (outside the Claude Code conversation) to extract
structured knowledge from a raw article. This avoids loading the full article text
into the conversation context.

Usage:
    python3 extract_knowledge.py <wiki-root> <raw-article-path>

Output: wiki/meta/extract-<slug>.json

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
from pathlib import Path


def resolve_article_path(wiki_root: Path, *, use_next: bool = False, raw_article: str = "") -> str | None:
    """Resolve which article to process.

    If use_next=True, find the first unprocessed article (no source page).
    Otherwise return the explicit raw_article path.
    Returns None if no unprocessed article found.
    """
    if not use_next:
        return raw_article

    raw_dir = wiki_root / "raw" / "articles"
    sources_dir = wiki_root / "wiki" / "sources"

    if not raw_dir.exists():
        return None

    # Collect processed raw_paths from source page frontmatters
    processed = set()
    if sources_dir.exists():
        for source_file in sources_dir.glob("*.md"):
            text = source_file.read_text(encoding="utf-8")
            m = re.search(r"^raw_path:\s*(.+)$", text, re.MULTILINE)
            if m:
                # Normalize to forward slashes for cross-platform comparison
                processed.add(m.group(1).strip().strip('"').strip("'").replace("\\", "/"))

    # Find first unprocessed article
    for article in sorted(raw_dir.glob("*.md")):
        rel_path = f"raw/articles/{article.name}"
        if rel_path not in processed:
            return rel_path

    return None


def derive_slug(raw_path: str) -> str:
    """Derive a URL-safe slug from the raw article filename.

    Strips [timestamp] prefix and .md extension, lowercases.
    """
    name = Path(raw_path).stem
    # Remove [YYYYMMDDHHMM] prefix
    name = re.sub(r"^\[\d+\]", "", name)
    return name.lower()


def _first(*values: str | None) -> str | None:
    """Return the first non-empty value."""
    return next((v for v in values if v), None)


def load_api_config(settings_path: Path) -> dict | None:
    """Load API config from environment variables, falling back to settings.json.

    Resolution order for each field (first non-empty wins):
      1. Process environment variables (primary + common aliases)
      2. ~/.claude/settings.json → env section

    Supported env var names:
      api_key:  ANTHROPIC_AUTH_TOKEN, ANTHROPIC_API_KEY
      base_url: ANTHROPIC_BASE_URL
      model:    ANTHROPIC_DEFAULT_OPUS_MODEL, ANTHROPIC_MODEL

    Returns dict with api_key, base_url, model or None on failure.
    """
    file_env: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            file_env = data.get("env", {})
        except (json.JSONDecodeError, OSError):
            pass

    api_key = _first(
        os.environ.get("ANTHROPIC_AUTH_TOKEN"),
        os.environ.get("ANTHROPIC_API_KEY"),
        file_env.get("ANTHROPIC_AUTH_TOKEN"),
        file_env.get("ANTHROPIC_API_KEY"),
    )
    base_url = _first(
        os.environ.get("ANTHROPIC_BASE_URL"),
        file_env.get("ANTHROPIC_BASE_URL"),
    )
    model = _first(
        os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        os.environ.get("ANTHROPIC_MODEL"),
        file_env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        file_env.get("ANTHROPIC_MODEL"),
    )

    if not api_key or not base_url or not model:
        return None
    return {"api_key": api_key, "base_url": base_url, "model": model}


def extract_page_names(index_text: str) -> str:
    """Extract existing page names from index.md, grouped by category.

    Returns a compact summary (~5KB) instead of the full index (~107KB).
    The LLM only needs page names to determine is_new / existing_page.
    """
    categories: dict[str, list[str]] = {}
    current = None
    for line in index_text.splitlines():
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            current = header.group(1).strip()
            if current not in categories:
                categories[current] = []
        elif current:
            for name in re.findall(r"\[\[([^\]]+)\]\]", line):
                categories[current].append(name)

    parts = []
    for cat in ("Sources", "Concepts", "Entities"):
        names = categories.get(cat)
        if names:
            parts.append(f"## 已有 {cat}\n" + "\n".join(f"- [[{n}]]" for n in names))

    return "\n\n".join(parts) if parts else "(empty wiki)"


# Sections to extract from CLAUDE.md (in order)
_CLAUDE_MD_SECTIONS = [
    "Naming Conventions",
    "Page Status Lifecycle",
    "Page Thresholds",
    "Tag Taxonomy",
    "Writing Style",
]


def extract_claude_md_sections(claude_md: str) -> str:
    """Extract relevant sections from CLAUDE.md for the extraction prompt.

    Extracts sections between ## headers, stopping at the next ## header
    that is NOT in our desired list.
    """
    lines = claude_md.split("\n")
    sections = {}
    current_header = None
    current_lines = []

    for line in lines:
        header_match = re.match(r"^## (.+)$", line)
        if header_match:
            # Save previous section
            if current_header:
                sections[current_header] = "\n".join(current_lines)
            current_header = header_match.group(1).strip()
            current_lines = [line]
        elif current_header:
            current_lines.append(line)

    # Save last section
    if current_header:
        sections[current_header] = "\n".join(current_lines)

    # Collect only desired sections in order
    result_parts = []
    for section_name in _CLAUDE_MD_SECTIONS:
        if section_name in sections:
            result_parts.append(sections[section_name])

    return "\n\n".join(result_parts)


def build_extraction_prompt(claude_md_rules: str, wiki_index: str, article_text: str) -> str:
    """Build the user message for the extraction API call."""
    return f"""## Wiki Rules

{claude_md_rules}

## Current Wiki Index

{wiki_index}

## Source Article

{article_text}

## Output Format

Output a single JSON object with this exact structure. Do NOT wrap in markdown code blocks.

{{
  "title": "Article title",
  "summary": "2-3 sentence summary of the article",
  "source_content": "Structured summary of the article for the source page, using markdown sections like ## 核心内容, ## 关键发现, ## 相关概念 with [[wikilinks]]",
  "concepts": [
    {{
      "name": "Concept name",
      "description": "One-sentence description for index.md",
      "is_new": true,
      "page_content": "Full wiki page content in markdown with sections like ## 定义, ## 方法/机制, ## 相关概念 (with [[wikilinks]]), ## 来源 (with [[wikilinks]] to source page). 200-500 words."
    }}
  ],
  "entities": [
    {{
      "name": "Entity name",
      "type": "entity_type (e.g. person, organization, tool, dataset)",
      "description": "One-sentence description for index.md",
      "existing_page": "wiki/entities/xxx.md or null if new",
      "page_content": "Full wiki page content in markdown. For organizations: ## 简介, ## 研究领域. For people: ## 简介, ## 代表作. Include ## 来源 with [[wikilink]] to source page."
    }}
  ],
  "tags": ["tag1", "tag2"],
  "key_findings": ["Key finding 1", "Key finding 2"],
  "relations": [
    {{"from": "Entity", "to": "Concept", "type": "relationship type"}}
  ]
}}

Rules:
- Use the Page Thresholds to decide whether each concept/entity deserves a page
- Use the Tag Taxonomy for tags — only use tags listed there
- Check the Wiki Index to determine if a page already exists (set existing_page or is_new accordingly)
- Follow the Writing Style conventions for language
- The "description" fields should be informative enough that a reader can decide whether to consult the original article
- The "page_content" fields should be complete wiki pages with structured sections, [[wikilinks]] to related concepts/entities, and a ## 来源 section linking back to the source article
- The "source_content" should summarize the article's key contributions and link to the concepts/entities mentioned"""


def parse_llm_response(text: str) -> dict | None:
    """Parse LLM response text into a structured dict.

    Handles:
    - Clean JSON
    - JSON wrapped in ```json ... ```
    - Missing optional fields (filled with defaults)

    Returns None if text cannot be parsed as JSON.
    """
    text = text.strip()

    # Try to extract JSON from markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if md_match:
        text = md_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Fill missing fields with defaults
    data.setdefault("title", "")
    data.setdefault("summary", "")
    data.setdefault("concepts", [])
    data.setdefault("entities", [])
    data.setdefault("tags", [])
    data.setdefault("key_findings", [])
    data.setdefault("relations", [])
    data.setdefault("source_content", "")

    for item in data.get("concepts", []) + data.get("entities", []):
        item.setdefault("page_content", "")

    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract structured knowledge from an article via LLM API."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("raw_article", nargs="?", default=None,
                        help="Path to the raw article file (relative to wiki-root)")
    parser.add_argument("--next", action="store_true",
                        help="Auto-find and process the first unprocessed article")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()

    # Resolve which article to process
    use_next = args.next or args.raw_article is None
    rel_path = resolve_article_path(wiki_root, use_next=use_next, raw_article=args.raw_article or "")
    if rel_path is None:
        print("No unprocessed articles found.", file=sys.stderr)
        return 1

    raw_path = wiki_root / rel_path
    print(f"Processing: {rel_path}", file=sys.stderr)

    if not raw_path.exists():
        print(f"ERROR: Article not found: {raw_path}", file=sys.stderr)
        return 1

    # Load API config
    settings_path = Path.home() / ".claude" / "settings.json"
    config = load_api_config(settings_path)
    if config is None:
        print("ERROR: Could not load API config from any source.", file=sys.stderr)
        print("Configure one of:", file=sys.stderr)
        print("  (1) Environment variables: ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY),", file=sys.stderr)
        print("      ANTHROPIC_BASE_URL, ANTHROPIC_DEFAULT_OPUS_MODEL (or ANTHROPIC_MODEL)", file=sys.stderr)
        print(f"  (2) {settings_path} → env section with the same keys", file=sys.stderr)
        return 1

    # Read inputs
    article_text = raw_path.read_text(encoding="utf-8")
    claude_md_path = wiki_root / "CLAUDE.md"
    claude_md = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    claude_md_rules = extract_claude_md_sections(claude_md)

    index_path = wiki_root / "wiki" / "index.md"
    wiki_index_full = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    wiki_index = extract_page_names(wiki_index_full) if wiki_index_full else "(no index.md found)"

    # Build prompt
    system_prompt = "你是一个知识架构师。阅读以下文章，根据 wiki 规则提取结构化信息。输出纯 JSON，不要 markdown 代码块包裹。"
    user_message = build_extraction_prompt(claude_md_rules, wiki_index, article_text)

    # Call API
    print(f"Calling LLM API ({config['model']})...", file=sys.stderr)

    api_url = config["base_url"].rstrip("/") + "/v1/messages"
    request_body = json.dumps({
        "model": config["model"],
        "max_tokens": 8192,
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

    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            if attempt == 0:
                print(f"WARNING: API call failed: {e}", file=sys.stderr)
                print("Retrying...", file=sys.stderr)
            else:
                print(f"ERROR: API call failed after retry: {e}", file=sys.stderr)
                return 1

    # Extract text from response
    response_text = ""
    for block in resp_data.get("content", []):
        if block.get("type") == "text":
            response_text += block.get("text", "")

    if not response_text.strip():
        print("ERROR: API returned empty response", file=sys.stderr)
        return 1

    # Parse response
    result = parse_llm_response(response_text)
    if result is None:
        print("ERROR: Could not parse API response as JSON", file=sys.stderr)
        print(f"Response: {response_text[:500]}", file=sys.stderr)
        return 1

    # Write output
    slug = derive_slug(rel_path)
    meta_dir = wiki_root / "wiki" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    output_path = meta_dir / f"extract-{slug}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write marker file so LLM can reliably find the extract path (avoids garbled Bash output)
    rel_extract = f"wiki/meta/extract-{slug}.json"
    (meta_dir / ".last-extract").write_text(rel_extract, encoding="utf-8")

    print(f"Extracted: {output_path}")
    print(f"  Concepts: {len(result.get('concepts', []))}")
    print(f"  Entities: {len(result.get('entities', []))}")
    print(f"  Tags: {result.get('tags', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
