# Remove hot.md and questions.md Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `hot.md` and `questions.md` from the wiki schema, consolidating their content into `index.md` (Active Threads + Open Questions sections) to reduce session startup from 4 Read calls to 2.

**Architecture:** scaffold.py stops creating hot.md/questions.md. index.md template gains "Active Threads" and "Open Questions" sections. CLAUDE.md removes all references. quant-wiki gets the same changes plus physical file deletion.

**Tech Stack:** Python, pytest, argparse CLI scripts

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `llm-wiki-template/tests/test_scripts.py` | Modify | Remove old assertions, add new ones |
| `llm-wiki-template/scripts/scaffold.py` | Modify | Remove hot.md/questions.md creation, add sections to index.md |
| `llm-wiki-template/_schema/CLAUDE.md` | Modify | Remove all references to hot.md/questions.md |
| `llm-wiki-template/.claude/commands/query.md` | (inside scaffold.py) | Remove "Read hot.md first" |
| `llm-wiki-template/.claude/commands/ingest.md` | (inside scaffold.py) | Remove "hot.md" from update list |
| `quant-wiki/CLAUDE.md` | Modify | Same _schema/CLAUDE.md changes |
| `quant-wiki/hot.md` | Delete | No longer needed |
| `quant-wiki/questions.md` | Delete | No longer needed |

---

### Task 1: Write failing tests for scaffold changes

**Files:**
- Modify: `llm-wiki-template/tests/test_scripts.py:231-232` (remove old assertions)
- Modify: `llm-wiki-template/tests/test_scripts.py` (add new assertions)

- [ ] **Step 1: Update scaffold test — remove old assertions, add new ones**

In `test_scripts.py`, the test `test_scaffold_creates_structure` at line 231-232 asserts `hot.md` and `questions.md` exist. Change those to assert they do NOT exist, and assert index.md has the new sections.

Find in `test_scaffold_creates_structure`:
```python
        assert (wiki / "hot.md").exists()
        assert (wiki / "questions.md").exists()
```

Replace with:
```python
        # hot.md and questions.md removed — content merged into index.md
        assert not (wiki / "hot.md").exists()
        assert not (wiki / "questions.md").exists()
```

Then add new assertions at the end of the same test to verify index.md has the new sections:
```python
        index_text = (wiki / "wiki" / "index.md").read_text(encoding="utf-8")
        assert "## Active Threads" in index_text
        assert "## Open Questions" in index_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd llm-wiki-template && python -m pytest tests/test_scripts.py::TestScaffoldAndLint::test_scaffold_creates_structure -v`
Expected: FAIL — `hot.md` still exists (scaffold still creates it), and index.md doesn't have "Active Threads" section yet.

---

### Task 2: Update scaffold.py — remove hot.md/questions.md, add sections to index.md

**Files:**
- Modify: `llm-wiki-template/scripts/scaffold.py`

- [ ] **Step 1: Remove hot.md creation block (lines 202-224)**

Delete the entire `# hot.md` block — the variable assignment, the `_write()` call, and the print statement. This is lines 202-224:
```python
    # hot.md
    hot_md = f"""# Hot Cache
...
"""
    _write(root_path, "hot.md", hot_md)
    print("Created hot.md")
```

- [ ] **Step 2: Remove questions.md creation block (lines 226-238)**

Delete the entire `# questions.md` block:
```python
    # questions.md
    questions_md = """# Open Questions
...
"""
    _write(root_path, "questions.md", questions_md)
    print("Created questions.md")
```

- [ ] **Step 3: Add Active Threads and Open Questions sections to index.md template**

In the `index_md` variable (around line 157), replace the `## Open Questions` section:

Find:
```python
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

## Open Questions

- <First research question>
"""
```

Replace with:
```python
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
```

- [ ] **Step 4: Update docstring (line 12)**

Find:
```python
and initial files (index.md, hot.md, questions.md).
```

Replace with:
```python
and initial files (index.md, wiki/overview.md).
```

- [ ] **Step 5: Update log entry (line 246)**

Find:
```python
- Created wiki/index.md, hot.md, questions.md
```

Replace with:
```python
- Created wiki/index.md, wiki/overview.md
```

- [ ] **Step 6: Update ingest command template (line 99)**

Find:
```python
3. Update wiki/index.md, log/{{date}}.md, hot.md, wiki/overview.md
```

Replace with:
```python
3. Update wiki/index.md, log/{{date}}.md, wiki/overview.md
```

- [ ] **Step 7: Update query command template (line 105)**

Find:
```python
1. Read `hot.md` first to orient
```

Replace with:
```python
1. Read `wiki/index.md` first to orient
```

- [ ] **Step 8: Update overview.md template (line 197)**

Find:
```python
        f"<!-- 从 questions.md 汇总 -->\n",
```

Replace with:
```python
        f"<!-- 从 wiki/index.md Open Questions 汇总 -->\n",
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd llm-wiki-template && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
cd llm-wiki-template
git add scripts/scaffold.py tests/test_scripts.py
git commit -m "refactor: remove hot.md and questions.md from scaffold, merge into index.md"
```

---

### Task 3: Update _schema/CLAUDE.md — remove all hot.md/questions.md references

**Files:**
- Modify: `llm-wiki-template/_schema/CLAUDE.md`

- [ ] **Step 1: Remove directory structure entry (line 128)**

Find:
```
├── questions.md         ← open research questions queue
├── raw/                 ← immutable source documents
```

Replace with:
```
├── raw/                 ← immutable source documents
```

- [ ] **Step 2: Update query workflow reference (line 89)**

Find:
```
- The answer resolves an open question from `questions.md`
```

Replace with:
```
- The answer resolves an open question from the Open Questions section of `wiki/index.md`
```

- [ ] **Step 3: Update writing style reference (line 210)**

Find:
```
- **Contradictions**: present both views with citations; do not arbitrate. Add to `questions.md` if unresolved.
```

Replace with:
```
- **Contradictions**: present both views with citations; do not arbitrate. Add to the Open Questions section of `wiki/index.md` if unresolved.
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `cd llm-wiki-template && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd llm-wiki-template
git add _schema/CLAUDE.md
git commit -m "docs: remove hot.md/questions.md references from schema CLAUDE.md"
```

---

### Task 4: Sync changes to quant-wiki

**Files:**
- Modify: `quant-wiki/CLAUDE.md`
- Delete: `quant-wiki/hot.md`
- Delete: `quant-wiki/questions.md`

- [ ] **Step 1: Update quant-wiki/CLAUDE.md — directory structure**

Find:
```
├── questions.md         ← open research questions queue
├── raw/                 ← immutable source documents
```

Replace with:
```
├── raw/                 ← immutable source documents
```

- [ ] **Step 2: Update quant-wiki/CLAUDE.md — writing style reference**

Find:
```
- **Contradictions**: present both views with citations; do not arbitrate. Add to `questions.md` if unresolved.
```

Replace with:
```
- **Contradictions**: present both views with citations; do not arbitrate. Add to the Open Questions section of `wiki/index.md` if unresolved.
```

- [ ] **Step 3: Delete hot.md and questions.md**

```bash
cd quant-wiki
git rm hot.md questions.md
```

- [ ] **Step 4: Run quant-wiki tests**

Run: `cd quant-wiki && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd quant-wiki
git add CLAUDE.md
git commit -m "refactor: remove hot.md and questions.md, consolidate into index.md"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full test suites for both projects**

```bash
cd llm-wiki-template && python -m pytest tests/ -v
cd ../quant-wiki && python -m pytest tests/ -v
```

Expected: Both pass completely.

- [ ] **Step 2: Grep both projects for any remaining hot.md/questions.md references**

```bash
cd llm-workspace
grep -r "hot\.md\|questions\.md" llm-wiki-template/ quant-wiki/ --include="*.py" --include="*.md"
```

Expected: Zero results (no stale references remain).

---

## Self-Review

**Spec coverage:**
- Scaffold stops creating hot.md ✓ (Task 2)
- Scaffold stops creating questions.md ✓ (Task 2)
- index.md gains Active Threads section ✓ (Task 2)
- index.md keeps Open Questions section ✓ (Task 2)
- _schema/CLAUDE.md references removed ✓ (Task 3)
- quant-wiki CLAUDE.md updated ✓ (Task 4)
- quant-wiki files deleted ✓ (Task 4)
- All tests pass ✓ (Tasks 2, 3, 4, 5)
- No stale references ✓ (Task 5)

**Placeholder scan:** No TBD, TODO, or vague steps found.

**Type consistency:** N/A — no type changes.
