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
                processed.add(m.group(1).strip().strip('"').strip("'"))

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


def load_api_config(settings_path: Path) -> dict | None:
    """Load API config from ~/.claude/settings.json.

    Returns dict with api_key, base_url, model or None on failure.
    """
    if not settings_path.exists():
        return None
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    env = data.get("env", {})
    api_key = env.get("ANTHROPIC_AUTH_TOKEN")
    base_url = env.get("ANTHROPIC_BASE_URL")
    model = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if not api_key or not base_url or not model:
        return None
    return {"api_key": api_key, "base_url": base_url, "model": model}


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
  "concepts": [
    {{
      "name": "Concept name",
      "description": "One-sentence description with key information from the article",
      "is_new": true
    }}
  ],
  "entities": [
    {{
      "name": "Entity name",
      "type": "entity_type (e.g. person, organization, tool, dataset)",
      "description": "One-sentence description",
      "existing_page": "wiki/entities/xxx.md or null if new"
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
- The "description" fields should be informative enough that a reader can decide whether to consult the original article"""


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
        print(f"ERROR: Could not load API config from {settings_path}", file=sys.stderr)
        print("Ensure settings.json has env.ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, ANTHROPIC_DEFAULT_OPUS_MODEL", file=sys.stderr)
        return 1

    # Read inputs
    article_text = raw_path.read_text(encoding="utf-8")
    claude_md_path = wiki_root / "CLAUDE.md"
    claude_md = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    claude_md_rules = extract_claude_md_sections(claude_md)

    index_path = wiki_root / "wiki" / "index.md"
    wiki_index = index_path.read_text(encoding="utf-8") if index_path.exists() else "(no index.md found)"

    # Build prompt
    system_prompt = "你是一个知识架构师。阅读以下文章，根据 wiki 规则提取结构化信息。输出纯 JSON，不要 markdown 代码块包裹。"
    user_message = build_extraction_prompt(claude_md_rules, wiki_index, article_text)

    # Call API
    print(f"Calling LLM API ({config['model']})...", file=sys.stderr)

    api_url = config["base_url"].rstrip("/") + "/v1/messages"
    request_body = json.dumps({
        "model": config["model"],
        "max_tokens": 4096,
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

    print(f"Extracted: {output_path}")
    print(f"  Concepts: {len(result.get('concepts', []))}")
    print(f"  Entities: {len(result.get('entities', []))}")
    print(f"  Tags: {result.get('tags', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
