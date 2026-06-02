# LLM Wiki Template

> This is the template repository. If you're working inside a scaffolded wiki instance, read that wiki's own `CLAUDE.md` instead — this file only applies when you have the template repo itself open in Claude Code.

## What This Repo Is

A collection of scripts and templates for bootstrapping LLM Wiki knowledge bases. Based on Karpathy's llm-wiki pattern with extensions for format-guaranteed page creation, health checking, and audit feedback loops.

See `_schema/CLAUDE.md` for what a generated wiki instance looks like from the LLM's perspective.

## Your Job in This Repo

When working inside this template repo, your role is **template maintenance**, not wiki maintenance:

- Improve scripts in `scripts/` (scaffold, create_page, lint_wiki, audit_review)
- Improve page templates in `_templates/`
- Keep `_schema/CLAUDE.md` in sync with what `scaffold.py` actually generates
- Update `README.md` if the interface changes

## Key Constraint

`_schema/CLAUDE.md` is the single source of truth for the generated wiki schema. `scaffold.py` reads it at scaffold time to produce the wiki's `CLAUDE.md`. If you change the schema, change it in `_schema/CLAUDE.md` first — `scaffold.py` will pick it up automatically. Do not duplicate schema content inside `scaffold.py`'s inline fallback unless necessary.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold.py` | Bootstrap a new wiki — copies scripts + templates, generates CLAUDE.md from `_schema/` |
| `scripts/create_page.py` | Create a wiki page with correct frontmatter from a template |
| `scripts/create_pages_from_extract.py` | Combined page creation from extract JSON — handles source + concepts + entities + index in one call |
| `scripts/extract_knowledge.py` | Extract concepts/entities/relations from article via independent LLM API call |
| `scripts/merge_frontmatter.py` | Deterministically merge array fields (sources, tags, related) into page frontmatter |
| `scripts/ingest_finish.py` | Write ingest log entry and git commit |
| `scripts/lint_wiki.py` | 21-check health check for a wiki instance |
| `scripts/audit_review.py` | List and group open audit feedback by target file |
| `scripts/update_index.py` | Add deduplicated entries to wiki/index.md by section |
| `scripts/update_overview.py` | Insert a new ### section into wiki/overview.md |
| `scripts/slug_utils.py` | Shared slug generation (slugify, derive_slug) |
| `scripts/backfill_sources.py` | One-time backfill of empty sources fields via wikilink reverse inference |
| `scripts/suggest_syntheses.py` | Identify cross-source analysis opportunities (3+ sources per concept) |
| `scripts/promote_pages.py` | Promote page status based on content maturity (seed→developing→mature→evergreen) |

## Templates

`_templates/`: `source.md`, `concept.md`, `entity.md`, `synthesis.md`, `comparison.md`

All templates use `{date}` and `{title}` placeholders filled by `create_page.py`.
