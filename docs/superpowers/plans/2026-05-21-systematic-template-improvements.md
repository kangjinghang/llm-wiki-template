# Systematic Template Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrative overview layer and inline wikilink writing guidance to the wiki template, addressing the two systematic gaps identified from comparing our template-built wiki with an LLM-Wiki tool-built wiki.

**Architecture:** Two changes — (1) add an `overview.md` template + scaffold generation + ingest update rule + lint check, (2) add inline wikilink density rule to the Writing Style section of the schema. Both are template-level changes that propagate to all scaffolded wikis.

**Tech Stack:** Python 3.10+, pytest, existing scripts (scaffold.py, lint_wiki.py)

---

### Task 1: Add overview.md template

**Files:**
- Create: `_templates/overview.md`
- Modify: `_schema/CLAUDE.md` (Ingest section, step 9 → step 10, add overview update step)
- Modify: `scripts/scaffold.py` (generate `wiki/overview.md` in scaffolded wikis)

- [ ] **Step 1: Create `_templates/overview.md`**

```markdown
---
title: "{topic} 知识库概览"
type: overview
summary: ""
tags: []
origin: agent-compiled
status: seed
created: {date}
updated: {date}
review_by: ""
---

# {topic} 知识库概览

> 这篇概览在每次 ingest 后自动更新，将整个知识库的核心发现串联为一篇连贯叙事。

## 核心主题

<!-- 叙述本知识库关注的 2-3 个核心研究方向 -->

## 关键发现

<!-- 按 Source 归纳最重要的结论，每个结论用 [[wikilink]] 引用相关概念页 -->

## 开放问题

<!-- 从 questions.md 和各页面的 Claims to Verify 汇总 -->

<!-- human:start -->
## 个人笔记

<!-- 在此添加你自己的思考 -->
<!-- human:end -->
```

- [ ] **Step 2: Modify `_schema/CLAUDE.md` Ingest workflow**

In the Phase 2 section, after step 9 (Update `hot.md`), add a new step 10:

```markdown
10. Update `wiki/overview.md` — revise the narrative overview to reflect new content. Ensure every new concept is mentioned in context with `[[wikilink]]`. This is NOT a table of contents — it's a synthetic narrative that a reader can read top-to-bottom to understand the entire knowledge base.
```

Also add to the Writing Style section (after "Managed blocks" bullet):

```markdown
- **Inline wikilinks**: The first mention of any concept, entity, or source that has its own wiki page MUST be a `[[wikilink]]` embedded in the prose — not just listed in Related Pages. This applies to ALL page types (source, concept, entity, synthesis, overview). Related Pages sections supplement inline links, they do not replace them.
```

- [ ] **Step 3: Modify `scripts/scaffold.py` to generate `wiki/overview.md`**

Read the current scaffold.py (258 lines). After the block that creates `wiki/index.md` (around lines 157-183), add a new block to create `wiki/overview.md`:

```python
    # --- wiki/overview.md ---
    overview = wiki_dir / "overview.md"
    overview.write_text(
        f"# {title} 知识库概览\n\n"
        f"> 这篇概览在每次 ingest 后自动更新，将整个知识库的核心发现串联为一篇连贯叙事。\n\n"
        f"## 核心主题\n\n"
        f"<!-- 叙述本知识库关注的 2-3 个核心研究方向 -->\n\n"
        f"## 关键发现\n\n"
        f"<!-- 按 Source 归纳最重要的结论 -->\n\n"
        f"## 开放问题\n\n"
        f"<!-- 从 questions.md 汇总 -->\n",
        encoding="utf-8",
    )
    print(f"  Created {overview}")
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All 57+ tests pass (scaffold tests may need updating if they assert exact file count)

- [ ] **Step 5: Commit**

```bash
git add _templates/overview.md _schema/CLAUDE.md scripts/scaffold.py
git commit -m "feat: add overview.md template and scaffold generation"
```

---

### Task 2: Add overview.md existence lint check (Pass 13)

**Files:**
- Modify: `scripts/lint_wiki.py` (add Pass 13)
- Modify: `tests/test_scripts.py` (add test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scripts.py`:

```python
# --- overview.md existence ---

class TestOverviewExists:
    def test_flags_missing_overview(self, tmp_path):
        """Wiki without overview.md should be flagged."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Delete overview.md
        (wiki / "wiki" / "overview.md").unlink()
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "overview" in proc.stdout.lower()

    def test_passes_with_overview(self, tmp_path):
        """Wiki with overview.md should pass this check."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # scaffold now creates overview.md, so it should pass
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert "overview" not in proc.stdout.lower() or proc.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestOverviewExists::test_flags_missing_overview -v`
Expected: FAIL (no Pass 13 exists yet)

- [ ] **Step 3: Add Pass 13 to `scripts/lint_wiki.py`**

After Pass 12 (source pages sources field check, around line 488), add:

```python
    # ── Pass 13: overview.md exists ─────────────────────────────────
    overview_path = wiki_path / "overview.md"
    if not overview_path.exists():
        print("❌ wiki/overview.md is missing — run scaffold to create it, then update during ingest")
        issues += 1
    else:
        print("✅ overview.md exists")
```

**IMPORTANT**: The lint function uses `wiki_path` (not `wiki_dir`) as the variable name for the `wiki/` directory (defined at line 173: `wiki_path = root_path / "wiki"`). Also, `issues` is an `int` counter (not a list), so use `issues += 1`.

Update the docstring at top of file from "11-check" to "14-check" (since Pass 14 is also being added).

- [ ] **Step 4: Run tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestOverviewExists -v`
Expected: Both tests pass.

- [ ] **Step 5: Run all tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/lint_wiki.py tests/test_scripts.py
git commit -m "feat: add lint Pass 13 — overview.md existence check"
```

---

### Task 3: Add inline wikilink density lint check (Pass 14)

**Files:**
- Modify: `scripts/lint_wiki.py` (add Pass 14)
- Modify: `tests/test_scripts.py` (add test class)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scripts.py`:

```python
# --- inline wikilink density ---

class TestInlineWikilinkDensity:
    def test_flags_page_with_no_inline_links(self, tmp_path):
        """A concept page with wikilinks only in Related Pages should be flagged."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Create a concept page with wikilinks ONLY in Related Pages (body has none)
        page = wiki / "wiki" / "concepts" / "test-concept.md"
        page.write_text(
            '---\n'
            'title: "Test Concept"\n'
            'title_zh: "测试概念"\n'
            'type: concept\n'
            'summary: "A test concept"\n'
            'tags: []\n'
            'sources:\n'
            '  - "[[test-source]]"\n'
            'origin: agent-compiled\n'
            'status: developing\n'
            'created: 2026-05-21\n'
            'updated: 2026-05-21\n'
            'review_by: ""\n'
            '---\n\n'
            '# Test Concept\n\n'
            '## Definition\n\n'
            'This is a concept about something. It relates to other things.\n\n'
            '## How It Works\n\n'
            'The mechanism involves multiple steps.\n\n'
            '## Related Pages\n\n'
            '- [[other-concept]]\n'
            '- [[another-entity]]\n',
            encoding="utf-8",
        )
        # Add to index
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[test-concept]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "inline" in proc.stdout.lower() or "wikilink density" in proc.stdout.lower()

    def test_passes_page_with_inline_links(self, tmp_path):
        """A concept page with inline wikilinks in body should pass."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        page = wiki / "wiki" / "concepts" / "test-concept.md"
        page.write_text(
            '---\n'
            'title: "Test Concept"\n'
            'title_zh: "测试概念"\n'
            'type: concept\n'
            'summary: "A test concept"\n'
            'tags: []\n'
            'sources:\n'
            '  - "[[test-source]]"\n'
            'origin: agent-compiled\n'
            'status: developing\n'
            'created: 2026-05-21\n'
            'updated: 2026-05-21\n'
            'review_by: ""\n'
            '---\n\n'
            '# Test Concept\n\n'
            '## Definition\n\n'
            'This concept builds on [[other-concept]] and extends it.\n\n'
            '## How It Works\n\n'
            'The mechanism is related to [[another-entity]] in practice.\n\n'
            '## Related Pages\n\n'
            '- [[other-concept]]\n',
            encoding="utf-8",
        )
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[test-concept]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Should pass — inline wikilinks exist in body
        assert "inline" not in proc.stdout.lower() or proc.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestInlineWikilinkDensity::test_flags_page_with_no_inline_links -v`
Expected: FAIL

- [ ] **Step 3: Add Pass 14 to `scripts/lint_wiki.py`**

After Pass 13, add:

```python
    # ── Pass 14: Inline wikilink density ─────────────────────────────
    # Pages with >= 50 words of body content should have at least 1 inline [[wikilink]]
    # in their body (outside of Related Pages / Sources sections and frontmatter).
    low_density: list[tuple[str, int]] = []
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
        # Count words (rough: split on whitespace, filter short tokens)
        words = [w for w in body_clean.split() if len(w) > 1]
        if len(words) < 50:
            continue
        # Count inline wikilinks in the cleaned body
        inline_links = re.findall(r"\[\[([^\]]+)\]\]", body_clean)
        if len(inline_links) == 0:
            low_density.append((rel, len(words)))
    if low_density:
        print(f"\n⚠️  {len(low_density)} page(s) with no inline wikilinks in body (>= 50 words):")
        for path, wc in low_density:
            print(f"   {path} ({wc} words, 0 inline links)")
        issues += len(low_density)
    else:
        print("✅ All pages with substantial body content have inline wikilinks")
```

**IMPORTANT**: Use `all_wiki_files` (already defined at line 182) and `wiki_path` (not `wiki_dir`). Use `re` directly (already imported at file top), not `import re as _re`. Use `issues += len(low_density)` since `issues` is an `int` counter.

- [ ] **Step 4: Run tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestInlineWikilinkDensity -v`
Expected: Both tests pass.

- [ ] **Step 5: Run all tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/lint_wiki.py tests/test_scripts.py
git commit -m "feat: add lint Pass 14 — inline wikilink density check"
```

---

### Task 4: Update README and docs

**Files:**
- Modify: `README.md` (add checks 13-14, mention overview.md in directory structure)

- [ ] **Step 1: Update README.md checks section**

Add after check 12:

```markdown
13. overview.md existence — wiki must have a narrative overview page
14. Inline wikilink density — pages with ≥50 words of body content must have at least 1 inline `[[wikilink]]`
```

Update the check count in the description text if it says a specific number.

- [ ] **Step 2: Add overview.md to directory structure in README**

In the directory structure example, add `overview.md` to the `wiki/` listing if not already shown.

- [ ] **Step 3: Run all tests one final time**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for lint checks 13-14 and overview.md"
```

---

### Task 5: Sync changes to quant-wiki

**Files:**
- Modify: `D:\llm-workspace\quant-wiki\scripts\lint_wiki.py` (copy Pass 13 + 14)
- Modify: `D:\llm-workspace\quant-wiki\CLAUDE.md` (add overview update step, add inline wikilink rule)
- Create: `D:\llm-workspace\quant-wiki\wiki\overview.md` (initial content)

- [ ] **Step 1: Copy updated scripts from template**

```bash
cp D:/llm-workspace/llm-wiki-template/scripts/lint_wiki.py D:/llm-workspace/quant-wiki/scripts/lint_wiki.py
cp D:/llm-workspace/llm-wiki-template/scripts/scaffold.py D:/llm-workspace/quant-wiki/scripts/scaffold.py
```

- [ ] **Step 2: Update quant-wiki CLAUDE.md**

In the Ingest Phase 2 section, add step 10 (update overview.md). In the Writing Style section, add the inline wikilink rule. Both rules are the same text as in Task 1 Step 2.

- [ ] **Step 3: Create initial `wiki/overview.md` for quant-wiki**

Read all existing wiki pages in quant-wiki and write a comprehensive overview that:
- Covers the 3 core research directions (业绩超预期/因子投资, 可转债, 择时/形态)
- Summarizes key findings from each source with [[wikilinks]]
- Lists open questions from questions.md
- Contains inline [[wikilinks]] throughout (not just in a list)

This step requires reading all existing pages and synthesizing — the content will be domain-specific.

- [ ] **Step 4: Run lint on quant-wiki**

Run: `cd D:\llm-workspace\quant-wiki && python scripts/lint_wiki.py .`
Expected: All 14 checks pass (including new overview check and inline wikilink check — any pages flagged by Pass 14 should have inline links added)

- [ ] **Step 5: Fix any lint issues**

If Pass 14 flags pages, add inline [[wikilinks]] to those pages' body content.

- [ ] **Step 6: Commit both repos**

```bash
cd D:/llm-workspace/quant-wiki
git add scripts/ CLAUDE.md wiki/overview.md wiki/
git commit -m "feat: add overview.md, inline wikilink rule, sync lint Pass 13-14"
```

```bash
cd D:/llm-workspace/llm-wiki-template
git push
cd D:/llm-workspace/quant-wiki
git push
```
