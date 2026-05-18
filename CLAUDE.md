# LLM Wiki Template

> A reusable template for building LLM Wiki knowledge bases.
> See `docs/superpowers/specs/2026-05-19-llm-wiki-design.md` for the full design spec.

## What This Is

A collection of scripts, templates, and a CLAUDE.md schema that together let you scaffold new LLM Wiki knowledge bases for any domain. Based on Karpathy's LLM Wiki pattern with extensions for multi-wiki management, format-guaranteed page creation, and bilingual support.

## Quick Start

```bash
# Scaffold a new wiki
python scripts/scaffold.py ~/my-wiki-investing "投资知识库"

# Enter the wiki
cd ~/my-wiki-investing

# Initialize git
git init && git add -A && git commit -m "init: scaffold wiki"

# Open in Obsidian
# Open in Claude Code: claude
```

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scaffold.py` | Bootstrap new wiki | `python scripts/scaffold.py <path> "<title>"` |
| `create_page.py` | Create page with correct frontmatter | `python scripts/create_page.py <root> <type> "<title>" [options]` |
| `lint_wiki.py` | Health check (7 checks) | `python scripts/lint_wiki.py <root>` |
| `audit_review.py` | List/group audit feedback | `python scripts/audit_review.py <root> [--open|--resolved|--all]` |

## Templates

4 page templates in `_templates/`: source, concept, entity, comparison.

## Credits

- `scaffold.py` — modified from llm-wiki-skill
- `lint_wiki.py` — copied from llm-wiki-skill
- `audit_review.py` — copied from llm-wiki-skill
- Page templates — adapted from claude-obsidian
- Bilingual design — inspired by Chinese-LLM-Wiki
- Core pattern — Karpathy's llm-wiki