# llm-wiki-template

License: MIT — see [LICENSE](LICENSE)

A reusable template for building personal knowledge bases using LLMs.

Based on [Karpathy's llm-wiki pattern](https://github.com/karpathy/llm-wiki) with extensions for multi-wiki management, format-guaranteed page creation, and bilingual (zh/en) support.

The core idea: instead of retrieving from raw documents at query time (RAG), the LLM incrementally builds and maintains a persistent wiki — a structured, interlinked collection of markdown files. Knowledge is compiled once and kept current, not re-derived on every query. See `_schema/CLAUDE.md` for what a wiki instance looks like from the LLM's perspective.

## Requirements

- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (or any LLM agent that reads a schema file)
- [Obsidian](https://obsidian.md) (optional but recommended for browsing the wiki)

## Quick Start

```bash
# 1. Clone this template
git clone https://github.com/kangjinghang/llm-wiki-template
cd llm-wiki-template

# 2. Scaffold a new wiki
python scripts/scaffold.py ~/wikis/my-topic "My Topic"

# 3. Enter the wiki and initialize git
cd ~/wikis/my-topic
git init && git add -A && git commit -m "init: scaffold wiki"

# 4. Open in Claude Code
claude

# 5. Start ingesting sources
# Drop a file into raw/ and tell the agent: "ingest raw/articles/my-article.md"
```

After scaffolding, your wiki directory looks like this:

```
my-topic/
├── CLAUDE.md            ← schema: tells the LLM how to operate the wiki
├── hot.md               ← session cache: read first on every session
├── questions.md         ← open research questions
├── raw/                 ← your source documents (immutable)
│   ├── articles/
│   ├── papers/
│   ├── notes/
│   └── archive/
├── wiki/                ← LLM-generated markdown (the wiki itself)
│   ├── index.md
│   ├── overview.md
│   ├── sources/
│   ├── concepts/
│   ├── entities/
│   ├── syntheses/
│   └── meta/
├── log/                 ← append-only operation log
├── audit/               ← user feedback for correcting wiki errors
│   └── resolved/
├── scripts/             ← copied from this template repo
└── _templates/          ← copied from this template repo
```

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scaffold.py` | Bootstrap a new wiki | `python scripts/scaffold.py <path> "<title>"` |
| `create_page.py` | Create a wiki page with correct frontmatter | `python scripts/create_page.py <root> <type> "<title>" [options]` |
| `lint_wiki.py` | Health check (14 structural checks) | `python scripts/lint_wiki.py <root>` |
| `audit_review.py` | List and group open audit feedback | `python scripts/audit_review.py <root> [--open\|--resolved\|--all]` |

### create_page.py options

```bash
# Create a concept page
python scripts/create_page.py . concept "Attention Mechanism" --tags "AI,Deep-Learning"

# Create a source summary page (--raw-path links to the original file in raw/)
python scripts/create_page.py . source "Transformer Paper" --raw-path "raw/papers/attention.md"

# Create an entity page
python scripts/create_page.py . entity "OpenAI" --tags "AI,Company"

# Create a synthesis/comparison
python scripts/create_page.py . synthesis "Transformer vs RNN"
python scripts/create_page.py . comparison "BERT vs GPT"

# Create a source page with SHA256 hash of the raw file
python scripts/create_page.py . source "Transformer Paper" --raw-path "raw/papers/attention.md" --compute-hash
```

### lint_wiki.py checks

1. Dead wikilinks — `[[Target]]` where `Target.md` doesn't exist
2. Orphan pages — wiki pages with no inbound links
3. Missing index entries — wiki pages not listed in `wiki/index.md`
4. Unlinked concepts — terms linked 3+ times but lacking their own page
5. Log shape — every file matches `YYYY-MM-DD.md` with correct H1
6. Audit shape — every `audit/*.md` has valid YAML frontmatter
7. Audit targets — every open audit's `target` file exists
8. raw_path existence — source pages' `raw_path` must point to a real file
9. Tag taxonomy — tags must be declared in CLAUDE.md before use
10. Stale pages — pages with `review_by` date in the past
11. Filename case — wiki page filenames must be all lowercase
12. overview.md existence — wiki must have a narrative overview page
13. Inline wikilink density — pages with ≥50 words of body content must have at least 1 inline `[[wikilink]]`

## Page Templates

Five templates in `_templates/`: `source`, `concept`, `entity`, `synthesis`, `comparison`. Each generates a page with YAML frontmatter and bilingual section headings. The templates are designed for bilingual wikis (English technical terms, Chinese or English body text — your choice).

## The Schema

`_schema/CLAUDE.md` shows exactly what the generated wiki schema looks like. It defines the LLM's role, the four operations (Ingest, Query, Lint, Audit), naming conventions, and writing style. When you scaffold a new wiki, a copy of this schema is placed at the wiki root as `CLAUDE.md` and customized with your topic title.

Read `_schema/CLAUDE.md` before your first ingest to understand what the agent will do.

## Workflow

**Ingest** — drop a source into `raw/` and tell the agent to process it. A single source typically touches 10–15 wiki pages (source summary + updated concept/entity pages + index + log).

**Query** — ask questions; the agent reads `index.md` first, drills into relevant pages, and answers with `[[page]]` citations. Good answers can be saved back as new synthesis pages.

**Lint** — run `lint_wiki.py` periodically to catch structural issues. The agent generates a report and waits for your confirmation before making changes.

**Audit** — when you spot a factual error in the wiki, drop a note in `audit/`. The agent checks it against the raw source, fixes the wiki, and moves the note to `audit/resolved/`.

## Development

Requirements: Python 3.10+, [pytest](https://pytest.org).

```bash
pip install pytest
pytest -q
```

CI runs pytest on push/PR via `.github/workflows/ci.yml`.

## Credits

- Core pattern — [Karpathy's llm-wiki](https://github.com/karpathy/llm-wiki)
- Page templates — adapted from claude-obsidian
