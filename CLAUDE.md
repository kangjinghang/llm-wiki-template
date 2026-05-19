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
| `scripts/lint_wiki.py` | 7-check health check for a wiki instance |
| `scripts/audit_review.py` | List and group open audit feedback by target file |

## Templates

`_templates/`: `source.md`, `concept.md`, `entity.md`, `synthesis.md`, `comparison.md`

All templates use `{date}` and `{title}` placeholders filled by `create_page.py`.
