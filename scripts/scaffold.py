#!/usr/bin/env python3
"""
scaffold.py — Bootstrap a new LLM Wiki directory structure.

Usage:
    python3 scaffold.py <wiki-root> "<Topic Title>"

Example:
    python3 scaffold.py ~/wikis/ai-research "AI Research"

Creates a complete wiki directory with CLAUDE.md, scripts, templates,
and initial files (index.md, wiki/overview.md).
"""

import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path


def scaffold(root: str, title: str) -> None:
    root_path = Path(root).resolve()
    today = date.today()
    today_iso = today.isoformat()
    now_hm = datetime.now().strftime("%H:%M")

    if root_path.exists() and any(root_path.iterdir()):
        print(f"ERROR: {root} already exists and is not empty", file=sys.stderr)
        sys.exit(1)

    dirs = [
        "raw/articles",
        "raw/papers",
        "raw/notes",
        "raw/archive",
        "wiki/sources",
        "wiki/concepts",
        "wiki/entities",
        "wiki/syntheses",
        "wiki/meta",
        "log",
        "audit",
        "audit/resolved",
        "scripts",
        "_templates",
        ".claude/commands",
    ]

    for d in dirs:
        (root_path / d).mkdir(parents=True, exist_ok=True)
    print(f"Created directory tree under {root}/")

    # .gitkeep for empty dirs
    _write(root_path, "audit/.gitkeep", "")
    _write(root_path, "audit/resolved/.gitkeep", "")

    # Copy scripts from template repo
    script_src = Path(__file__).resolve().parent
    for script_name in [
        "scaffold.py", "create_page.py", "lint_wiki.py", "audit_review.py",
        "extract_knowledge.py", "merge_frontmatter.py", "ingest_finish.py",
    ]:
        src = script_src / script_name
        if src.exists():
            shutil.copy2(src, root_path / "scripts" / script_name)

    # Copy templates from template repo
    template_src = Path(__file__).resolve().parent.parent / "_templates"
    if template_src.exists():
        for tmpl in template_src.glob("*.md"):
            shutil.copy2(tmpl, root_path / "_templates" / tmpl.name)

    print("Copied scripts and templates")

    # .gitignore (keep .claude/commands/ tracked but ignore the rest)
    gitignore = """.obsidian/
.claude/*
!.claude/commands/
*.tmp
"""
    _write(root_path, ".gitignore", gitignore)

    # Slash commands for Claude Code
    _write(root_path, ".claude/commands/ingest.md", f"""Ingest a source file into the wiki.

**If $ARGUMENTS is provided:** ingest that specific file (e.g. `/ingest raw/articles/my-file.md`).

**If no arguments:** find unprocessed raw files automatically:

1. List all files in `raw/articles/`, `raw/papers/`, `raw/notes/` (not `raw/archive/`)
2. Read each existing source page in `wiki/sources/` and collect their `raw_path` frontmatter values
3. Show the user the list of unprocessed files (raw files NOT referenced by any source page)
4. If only one unprocessed file exists, proceed with it. If multiple, ask the user which to ingest first.

Then follow the ingest workflow defined in CLAUDE.md — execute immediately without pausing for confirmation:
1. Read the source file in full
2. Create source summary page with `--raw-path` AND `--compute-hash`, concept/entity pages, cascade updates
3. Update wiki/index.md, log/{{date}}.md, wiki/overview.md
4. Briefly report what was done
""")
    _write(root_path, ".claude/commands/query.md", f"""Answer the following question using the wiki: $ARGUMENTS

Follow the query workflow defined in CLAUDE.md:
1. Read wiki/index.md first to orient
2. Read wiki/index.md to find relevant pages
3. Drill into specific pages for details
4. Synthesize an answer with [[page-name]] citations
5. If the answer is worth preserving, suggest filing it back as a synthesis page
""")
    _write(root_path, ".claude/commands/lint.md", f"""Run a full lint check on the wiki and report results.

```
python scripts/lint_wiki.py .
```

Review the output. If there are issues, propose fixes and wait for confirmation before making changes.
""")
    _write(root_path, ".claude/commands/audit.md", f"""Process open audit feedback in the wiki.

If $ARGUMENTS is provided, focus on that specific audit file. Otherwise process all open audits.

Follow the audit workflow defined in CLAUDE.md:
1. Run `python scripts/audit_review.py . --open` to see pending feedback
2. Read each audit item and check the correction against the original raw/ source
3. Fix the wiki page and any related pages
4. Move the processed audit file to audit/resolved/
5. Log the correction in log/{{date}}.md
""")
    print("Created slash commands (.claude/commands/)")

    # CLAUDE.md — generated from _schema/CLAUDE.md if available, else inline
    schema_src = Path(__file__).resolve().parent.parent / "_schema" / "CLAUDE.md"
    if schema_src.exists():
        claude_md = schema_src.read_text(encoding="utf-8")
        # Replace the placeholder title
        claude_md = claude_md.replace("{{Topic Title}}", title)
        # Remove the template-repo preamble line (the second > line explaining this is a template)
        lines = claude_md.splitlines()
        cleaned = []
        skip_next_blank = False
        for line in lines:
            if "generated by `scaffold.py`" in line or "Edit it freely" in line:
                skip_next_blank = True
                continue
            if skip_next_blank and line.strip() == ">":
                skip_next_blank = False
                continue
            skip_next_blank = False
            cleaned.append(line)
        claude_md = "\n".join(cleaned)
    else:
        print("ERROR: _schema/CLAUDE.md not found — cannot generate wiki schema", file=sys.stderr)
        sys.exit(1)

    _write(root_path, "CLAUDE.md", claude_md)
    print("Created CLAUDE.md")

    # wiki/index.md
    index_md = f"""# Index — {title}

> One-sentence scope of the wiki.

## Sources

*(none yet)*

## Concepts

*(none yet)*

## Entities

*(none yet)*

## Syntheses

*(none yet)*

## Active Threads

*(none yet)*

## Open Questions

*(none yet)*
"""
    _write(root_path, "wiki/index.md", index_md)
    print("Created wiki/index.md")

    # --- wiki/overview.md ---
    overview = root_path / "wiki" / "overview.md"
    overview.write_text(
        f"# {title} 知识库概览\n\n"
        f"> 这篇概览在每次 ingest 后自动更新，将整个知识库的核心发现串联为一篇连贯叙事。\n\n"
        f"## 核心主题\n\n"
        f"<!-- 叙述本知识库关注的 2-3 个核心研究方向 -->\n\n"
        f"## 关键发现\n\n"
        f"<!-- 按 Source 归纳最重要的结论 -->\n\n"
        f"## 开放问题\n\n"
        f"<!-- 从 wiki/index.md Open Questions 汇总 -->\n",
        encoding="utf-8",
    )
    print(f"  Created {overview}")

    # log/<today>.md
    log_md = f"""# {today_iso}

## [{now_hm}] scaffold | Initialized {title} knowledge base
- Created directory tree (raw/, wiki/, log/, audit/, scripts/, _templates/)
- Created CLAUDE.md schema
- Created wiki/index.md, wiki/overview.md
- Copied scripts and templates
"""
    _write(root_path, f"log/{today_iso}.md", log_md)
    print(f"Created log/{today_iso}.md")

    print(f"""
Done. Wiki scaffolded at: {root}/

Next steps:
  1. cd {root} && git init && git add -A && git commit -m "init: scaffold {title} wiki"
  2. Open the directory in Obsidian
  3. Add sources to raw/ (use Obsidian Web Clipper for web articles)
  4. Open Claude Code in this directory and say "ingest raw/articles/<file>.md"
  5. Run lint:  python scripts/lint_wiki.py .
""")


def _write(root: Path, path: str, content: str) -> None:
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    scaffold(sys.argv[1], sys.argv[2])
