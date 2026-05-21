# Filename Language + Wikilink Density Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lint Pass 15 to flag pure-ASCII concept/entity filenames, and tighten Pass 14 to require 2+ inline wikilinks for pages with 80+ words.

**Architecture:** Two incremental changes to `lint_wiki.py`. Pass 15 checks that concept and entity page filenames contain at least one non-ASCII character (i.e., Chinese characters). Pass 14 threshold changes from "1 link / 50 words" to "2 links / 80 words".

**Tech Stack:** Python 3.10+, pytest

---

### Task 1: Add lint Pass 15 — pure-ASCII filename check

**Files:**
- Modify: `scripts/lint_wiki.py` (add Pass 15 after Pass 14)
- Modify: `tests/test_scripts.py` (add TestPureASCIIFilename class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scripts.py`:

```python
# --- pure-ASCII filename check ---

class TestPureASCIIFilename:
    def test_flags_english_concept_filename(self, tmp_path):
        """Concept page with pure-ASCII (English) filename should be flagged."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Create a stub target for the inline wikilink to avoid dead-link failures
        stub = wiki / "wiki" / "concepts" / "test-concept.md"
        stub.write_text(
            '---\ntitle: "Test"\ntype: concept\n---\nStub\n',
            encoding="utf-8",
        )
        # Create a concept page with English-only filename
        page = wiki / "wiki" / "concepts" / "smart-money-factor.md"
        page.write_text(
            '---\n'
            'title: "Smart Money Factor"\n'
            'title_zh: "聪明钱因子"\n'
            'type: concept\n'
            'summary: "A test concept"\n'
            'tags: []\n'
            'sources:\n'
            '  - "[[test-source]]"\n'
            'origin: agent-compiled\n'
            'status: seed\n'
            'created: 2026-05-21\n'
            'updated: 2026-05-21\n'
            'review_by: ""\n'
            '---\n\n'
            '# Smart Money Factor\n\n'
            '## Definition\n\n'
            'The [[test-concept]] smart money factor tracks institutional flow.\n',
            encoding="utf-8",
        )
        # Add to index
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[smart-money-factor]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "ascii" in proc.stdout.lower() or "chinese" in proc.stdout.lower() or "filename" in proc.stdout.lower()

    def test_passes_chinese_filename(self, tmp_path):
        """Concept page with Chinese filename should pass."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        page = wiki / "wiki" / "concepts" / "聪明钱因子.md"
        page.write_text(
            '---\n'
            'title: "聪明钱因子"\n'
            'title_zh: "聪明钱因子"\n'
            'type: concept\n'
            'summary: "A test concept"\n'
            'tags: []\n'
            'sources:\n'
            '  - "[[test-source]]"\n'
            'origin: agent-compiled\n'
            'status: seed\n'
            'created: 2026-05-21\n'
            'updated: 2026-05-21\n'
            'review_by: ""\n'
            '---\n\n'
            '# 聪明钱因子\n\n'
            '## 定义\n\n'
            '聪明钱因子追踪 [[机构资金]] 流向。\n',
            encoding="utf-8",
        )
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[聪明钱因子]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0

    def test_passes_source_english_filename(self, tmp_path):
        """Source pages with English filenames should NOT be flagged."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Source pages are allowed English filenames (raw article titles may be English)
        raw = wiki / "raw" / "articles" / "english-report.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("Content", encoding="utf-8")
        page = wiki / "wiki" / "sources" / "english-report.md"
        page.write_text(
            '---\n'
            'title: "English Report"\n'
            'title_zh: ""\n'
            'type: source\n'
            'summary: "A test source"\n'
            'tags: []\n'
            'origin: agent-compiled\n'
            'status: seed\n'
            'created: 2026-05-21\n'
            'updated: 2026-05-21\n'
            'raw_path: "raw/articles/english-report.md"\n'
            'raw_hash: "' + __import__('hashlib').sha256(b'Content').hexdigest() + '"\n'
            'review_by: ""\n'
            '---\n\n'
            '# English Report\n\nContent\n',
            encoding="utf-8",
        )
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[english-report]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestPureASCIIFilename::test_flags_english_concept_filename -v`
Expected: FAIL (no Pass 15 yet)

- [ ] **Step 3: Add Pass 15 to `scripts/lint_wiki.py`**

After Pass 14 (inline wikilink density, around line 535), add:

```python
    # ── Pass 15: Non-ASCII filename for concept/entity pages ──────────
    # Concept and entity pages should use Chinese filenames, not pure-ASCII English.
    # Source pages are exempt (raw article titles may be English).
    ascii_names: list[str] = []
    for md_file in all_wiki_files:
        rel = str(md_file.relative_to(wiki_path))
        parts = rel.replace("\\", "/").split("/")
        if len(parts) < 2:
            continue
        subdir = parts[0]  # concepts, entities, sources, etc.
        if subdir not in ("concepts", "entities"):
            continue
        stem = md_file.stem
        # Pure ASCII = all characters are in range 0-127
        if stem.isascii() and stem:
            ascii_names.append(rel)
    if ascii_names:
        print(f"\n⚠️  {len(ascii_names)} concept/entity page(s) with pure-ASCII (English) filenames:")
        for name in ascii_names:
            print(f"   {name} — use Chinese filename instead")
        issues += len(ascii_names)
    else:
        print("✅ All concept/entity pages have non-ASCII (Chinese) filenames")
```

Update docstring: change "14-check" to "15-check". Add item 15: "Pure-ASCII filename — concept/entity pages must use Chinese filenames".

- [ ] **Step 4: Run tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/test_scripts.py::TestPureASCIIFilename -v`
Expected: All 3 tests pass.

- [ ] **Step 5: Run all tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd D:\llm-workspace\llm-wiki-template
git add scripts/lint_wiki.py tests/test_scripts.py
git commit -m "feat: add lint Pass 15 — pure-ASCII filename check for concept/entity pages"
```

---

### Task 2: Tighten Pass 14 threshold — require 2+ links at 80+ words

**Files:**
- Modify: `scripts/lint_wiki.py` (Pass 14 lines 503-535)
- Modify: `tests/test_scripts.py` (adjust TestInlineWikilinkDensity)

- [ ] **Step 1: Adjust the Pass 14 implementation**

Read `scripts/lint_wiki.py` lines 503-535. Change the threshold from "50 words, 0 links" to "80 words, < 2 links". Specifically:

Change line 504 comment from:
```python
    # Pages with >= 50 words of body content should have at least 1 inline [[wikilink]]
```
to:
```python
    # Pages with >= 80 words of body content should have at least 2 inline [[wikilink]]
```

Change line 523:
```python
        if len(words) < 50:
```
to:
```python
        if len(words) < 80:
```

Change line 527:
```python
        if len(inline_links) == 0:
```
to:
```python
        if len(inline_links) < 2:
```

Change line 530:
```python
        print(f"\n⚠️  {len(low_density)} page(s) with no inline wikilinks in body (>= 50 words):")
```
to:
```python
        print(f"\n⚠️  {len(low_density)} page(s) with fewer than 2 inline wikilinks in body (>= 80 words):")

```

Change line 532:
```python
            print(f"   {path} ({wc} words, 0 inline links)")
```
to:
```python
            print(f"   {path} ({wc} words, {len(inline_links)} inline links)")
```

Also update the docstring at top of file to reflect the new threshold.

- [ ] **Step 2: Update tests**

The existing `TestInlineWikilinkDensity` tests need updating for the new thresholds.

Read `tests/test_scripts.py` and find the `TestInlineWikilinkDensity` class.

For `test_flags_page_with_no_inline_links`: the test page currently has ~65 words with 0 inline links in body. This needs to have >= 80 words and < 2 links. Update the body text to be longer (add more sentences) so it crosses the 80-word threshold. Keep 0 inline links in body.

For `test_passes_page_with_inline_links`: the page currently has inline links. Verify it still passes with the new threshold (it should, since it has 2 inline links).

- [ ] **Step 3: Run all tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd D:\llm-workspace\llm-wiki-template
git add scripts/lint_wiki.py tests/test_scripts.py
git commit -m "feat: tighten Pass 14 — require 2+ inline wikilinks at 80+ words"
```

---

### Task 3: Update README + sync to quant-wiki

**Files:**
- Modify: `README.md` (add check 15, update Pass 14 description)
- Copy: `scripts/lint_wiki.py` to quant-wiki
- Fix: any quant-wiki pages flagged by the new checks

- [ ] **Step 1: Update README.md**

In the numbered lint check list, add:
```
15. Non-ASCII filename — concept/entity pages must use Chinese filenames (not pure-ASCII English)
```

Update check 14 description to reflect new threshold:
```
14. Inline wikilink density — pages with ≥80 words of body content must have at least 2 inline `[[wikilink]]`
```

Update the total check count in the description text if it says a specific number.

- [ ] **Step 2: Run all tests**

Run: `cd D:\llm-workspace\llm-wiki-template && python -m pytest tests/ -q --tb=short`
Expected: All tests pass.

- [ ] **Step 3: Commit template**

```bash
cd D:\llm-workspace\llm-wiki-template
git add README.md
git commit -m "docs: update README for lint checks 15 and tightened Pass 14"
```

- [ ] **Step 4: Copy scripts to quant-wiki**

```bash
cp D:/llm-workspace/llm-wiki-template/scripts/lint_wiki.py D:/llm-workspace/quant-wiki/scripts/lint_wiki.py
```

- [ ] **Step 5: Run lint on quant-wiki**

Run: `cd D:\llm-workspace\quant-wiki && python scripts/lint_wiki.py .`

This will likely flag:
- Pass 14: pages with 80+ words but only 1 inline link (the 2 pages we identified: 名义价格幻觉.md, 开源金工.md)
- Pass 15: concept/entity pages with English filenames (the 9 recently ingested pages)

- [ ] **Step 6: Fix flagged issues**

For Pass 14 (low inline links): add inline [[wikilinks]] to the 2 flagged pages' body content.

For Pass 15 (English filenames): rename the flagged concept/entity pages from English to Chinese filenames, and update all [[wikilinks]] referencing them across the wiki. For each renamed page:
1. Read the page to get its `title_zh` or derive the Chinese name
2. Rename the file: `mv old-name.md new-chinese-name.md`
3. Update all wikilinks in other files that reference the old name
4. Update the entry in `wiki/index.md`

- [ ] **Step 7: Re-run lint**

Run: `cd D:\llm-workspace\quant-wiki && python scripts/lint_wiki.py .`
Expected: All checks pass.

- [ ] **Step 8: Commit quant-wiki**

```bash
cd D:/llm-workspace/quant-wiki
git add scripts/ wiki/
git commit -m "feat: sync lint Pass 15, fix English filenames and low-density inline links"
```

- [ ] **Step 9: Push both repos**

```bash
cd D:/llm-workspace/llm-wiki-template && git push
cd D:/llm-workspace/quant-wiki && git push
```
