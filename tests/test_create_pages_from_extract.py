"""Tests for create_pages_from_extract.py — dead wikilink fix and raw_path fill."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from create_pages_from_extract import fix_dead_wikilinks, fill_missing_raw_path, normalize_wikilinks, find_raw_path_for_extract


class TestFixDeadWikilinks:
    def test_strips_brackets_from_dead_links(self, tmp_path):
        """Remove brackets from wikilinks pointing to non-existent pages."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "existing.md").write_text("---\n---\nbody\n", encoding="utf-8")
        (wiki_dir / "另一个.md").write_text("---\n---\nbody\n", encoding="utf-8")

        page = wiki_dir / "test.md"
        page.write_text(
            "See [[existing]] and [[不存在]] and [[Another Dead]]. [[另一个]] is fine.\n",
            encoding="utf-8",
        )

        count = fix_dead_wikilinks(str(wiki_dir), [str(page)])
        assert count == 2
        text = page.read_text(encoding="utf-8")
        assert "[[existing]]" in text
        assert "[[另一个]]" in text
        assert "不存在" in text
        assert "[[不存在]]" not in text
        assert "Another Dead" in text
        assert "[[Another Dead]]" not in text

    def test_preserves_alias_links(self, tmp_path):
        """Keep alias links where slug matches an existing page."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "existing.md").write_text("---\n---\nbody\n", encoding="utf-8")

        page = wiki_dir / "test.md"
        page.write_text("[[existing|Display Name]] ok.\n", encoding="utf-8")

        count = fix_dead_wikilinks(str(wiki_dir), [str(page)])
        assert count == 0
        assert "[[existing|Display Name]]" in page.read_text(encoding="utf-8")

    def test_strips_dead_alias_links(self, tmp_path):
        """Strip brackets from alias links where slug has no page."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()

        page = wiki_dir / "test.md"
        page.write_text("[[不存在|Display]] here.\n", encoding="utf-8")

        count = fix_dead_wikilinks(str(wiki_dir), [str(page)])
        assert count == 1
        assert "不存在|Display" in page.read_text(encoding="utf-8")
        assert "[[不存在" not in page.read_text(encoding="utf-8")

    def test_no_changes_when_all_valid(self, tmp_path):
        """Return 0 and leave text unchanged when all links are valid."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "foo.md").write_text("---\n---\nbody\n", encoding="utf-8")

        page = wiki_dir / "test.md"
        original = "See [[foo]].\n"
        page.write_text(original, encoding="utf-8")

        count = fix_dead_wikilinks(str(wiki_dir), [str(page)])
        assert count == 0
        assert page.read_text(encoding="utf-8") == original

    def test_skips_nonexistent_files(self, tmp_path):
        """Return 0 gracefully when a path doesn't exist."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()

        count = fix_dead_wikilinks(str(wiki_dir), [str(tmp_path / "nope.md")])
        assert count == 0


class TestFillMissingRawPath:
    def test_fills_empty_raw_path(self, tmp_path):
        """Fill empty raw_path on an existing source page."""
        wiki_dir = tmp_path / "wiki" / "sources"
        wiki_dir.mkdir(parents=True)
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "[202210281436]test-article.md"
        raw_file.write_text("content", encoding="utf-8")

        source = wiki_dir / "test-article.md"
        source.write_text(
            '---\ntitle: "Test"\nraw_path: ""\n---\nBody\n',
            encoding="utf-8",
        )

        result = fill_missing_raw_path(source, 'raw/articles/[202210281436]test-article.md', tmp_path)
        assert result is True
        text = source.read_text(encoding="utf-8")
        assert 'raw/articles/[202210281436]test-article.md' in text
        assert 'raw_hash:' in text

    def test_skips_when_raw_path_already_set(self, tmp_path):
        """Do nothing when raw_path already has a value."""
        wiki_dir = tmp_path / "wiki" / "sources"
        wiki_dir.mkdir(parents=True)

        source = wiki_dir / "test.md"
        original = '---\ntitle: "Test"\nraw_path: "raw/articles/existing.md"\n---\nBody\n'
        source.write_text(original, encoding="utf-8")

        result = fill_missing_raw_path(source, 'raw/articles/new.md', tmp_path)
        assert result is False
        assert source.read_text(encoding="utf-8") == original

    def test_skips_when_no_raw_path_provided(self, tmp_path):
        """Do nothing when raw_path argument is None."""
        wiki_dir = tmp_path / "wiki" / "sources"
        wiki_dir.mkdir(parents=True)

        source = wiki_dir / "test.md"
        original = '---\ntitle: "Test"\nraw_path: ""\n---\nBody\n'
        source.write_text(original, encoding="utf-8")

        result = fill_missing_raw_path(source, None, tmp_path)
        assert result is False


class TestNormalizeWikilinks:
    def test_lowercases_english_wikilinks_to_match_filename(self):
        """[[Bollinger带]] should become [[bollinger带]] when file is bollinger带.md."""
        existing = {"bollinger带", "lightgbm模型", "fama与french"}
        text = "See [[Bollinger带]] and [[LightGBM模型]] and [[Fama与French]].\n"
        result = normalize_wikilinks(text, existing)
        assert "[[bollinger带]]" in result
        assert "[[lightgbm模型]]" in result
        assert "[[fama与french]]" in result
        assert "[[Bollinger带]]" not in result

    def test_preserves_already_correct_links(self):
        """Links already matching filenames should be unchanged."""
        existing = {"foo", "bar"}
        text = "See [[foo]] and [[bar]].\n"
        result = normalize_wikilinks(text, existing)
        assert result == text

    def test_preserves_alias_links(self):
        """[[slug|Display]] should normalize slug part only."""
        existing = {"bollinger带"}
        text = "[[Bollinger带|Bollinger Band]] is useful.\n"
        result = normalize_wikilinks(text, existing)
        assert "[[bollinger带|Bollinger Band]]" in result

    def test_leaves_unknown_links_unchanged(self):
        """Links to pages not in existing should be left alone."""
        existing = {"foo"}
        text = "See [[SomeRandomPage]] here.\n"
        result = normalize_wikilinks(text, existing)
        assert "[[SomeRandomPage]]" in result

    def test_handles_mixed_case_with_special_chars(self):
        """Slug mismatch with hyphens and uppercase."""
        existing = {"bollinger带"}
        text = "[[Bollinger Band模型]] works.\n"
        result = normalize_wikilinks(text, existing)
        # slugify("Bollinger Band模型") = "bollinger-band模型", not in existing → unchanged
        # But [[Bollinger带]] should normalize
        text2 = "[[Bollinger带]] works.\n"
        result2 = normalize_wikilinks(text2, existing)
        assert "[[bollinger带]]" in result2

    def test_no_changes_returns_same_string(self):
        """When all links are correct, return identical content."""
        existing = {"foo"}
        text = "[[foo]] ok\n"
        result = normalize_wikilinks(text, existing)
        assert result == text


class TestFindRawPathForExtract:
    def test_finds_matching_article_by_slug(self, tmp_path):
        """Match raw article via extract filename slug (strips [timestamp])."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "[202211121445]test-article-name.md"
        raw_file.write_text("content", encoding="utf-8")

        extract_name = "extract-test-article-name.json"
        result = find_raw_path_for_extract(tmp_path, extract_name)
        assert result == "raw/articles/[202211121445]test-article-name.md"

    def test_finds_chinese_article(self, tmp_path):
        """Match raw article with Chinese filename and timestamp prefix."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "[202211121445]中金转债事件驱动化学反应与Python实现转债年度展望系列2.md"
        raw_file.write_text("content", encoding="utf-8")

        extract_name = "extract-中金转债事件驱动化学反应与python实现转债年度展望系列2.json"
        result = find_raw_path_for_extract(tmp_path, extract_name)
        assert result is not None
        assert "中金转债" in result
        assert "[202211121445]" in result

    def test_returns_none_when_no_match(self, tmp_path):
        """Return None when no raw article matches the extract slug."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        (raw_dir / "[202210281436]other-article.md").write_text("content", encoding="utf-8")

        result = find_raw_path_for_extract(tmp_path, "extract-nonexistent.json")
        assert result is None

    def test_returns_none_for_non_extract_filename(self, tmp_path):
        """Return None when filename doesn't start with 'extract-'."""
        result = find_raw_path_for_extract(tmp_path, "other-file.json")
        assert result is None

    def test_returns_none_when_raw_dir_missing(self, tmp_path):
        """Return None when raw/articles/ directory doesn't exist."""
        result = find_raw_path_for_extract(tmp_path, "extract-test.json")
        assert result is None

    def test_works_with_path_object(self, tmp_path):
        """Accept Path object as extract_path."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        raw_file = raw_dir / "[202301010000]my-article.md"
        raw_file.write_text("content", encoding="utf-8")

        result = find_raw_path_for_extract(tmp_path, Path("extract-my-article.json"))
        assert result == "raw/articles/[202301010000]my-article.md"
