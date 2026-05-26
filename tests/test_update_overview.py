"""Tests for update_overview.py script."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from update_overview import insert_section


class TestInsertBeforeOpenQuestions:
    def test_insert_before_marker(self):
        content = "# Title\n\n## 核心主题\n\nSome text.\n\n## 开放问题\n\n1. Q1?\n"
        result, changed = insert_section(content, "### New Topic\n\nNew paragraph.")
        assert changed is True
        assert "### New Topic" in result
        assert result.index("### New Topic") < result.index("## 开放问题")
        assert "1. Q1?" in result  # preserved

    def test_insert_before_english_marker(self):
        content = "# Title\n\n## Notes\n\nSome notes.\n"
        result, changed = insert_section(content, "### Topic\n\nText.")
        assert changed is True
        assert result.index("### Topic") < result.index("## Notes")


class TestFallback:
    def test_fallback_to_notes(self):
        content = "# Title\n\n## Notes / 笔记\n\nNote.\n"
        result, changed = insert_section(content, "### Topic\n\nText.")
        assert changed is True
        assert "### Topic" in result

    def test_fallback_to_eof(self):
        content = "# Title\n\nSome content without markers.\n"
        result, changed = insert_section(content, "### Topic\n\nText.")
        assert changed is True
        assert "### Topic" in result


class TestDedup:
    def test_skip_duplicate_heading(self):
        content = "# Title\n\n### Existing Topic\n\nOld text.\n\n## 开放问题\n\n"
        result, changed = insert_section(content, "### Existing Topic\n\nNew text.")
        assert changed is False
        assert result == content  # unchanged

    def test_allow_different_heading(self):
        content = "# Title\n\n### Topic A\n\nOld.\n\n## 开放问题\n\n"
        result, changed = insert_section(content, "### Topic B\n\nNew.")
        assert changed is True
        assert "### Topic B" in result


class TestPreservesFrontmatter:
    def test_preserves_frontmatter(self):
        content = "---\ntitle: Overview\ntype: overview\n---\n\n# Title\n\n## 开放问题\n\n"
        result, changed = insert_section(content, "### Topic\n\nText.")
        assert changed is True
        assert result.startswith("---\ntitle: Overview")
        assert "### Topic" in result
        assert "## 开放问题" in result


class TestMultilineContent:
    def test_multiline_content(self):
        content = "# Title\n\n## 开放问题\n\n"
        section = "### Topic\n\nLine 1.\n\nLine 2 with [[wikilink]].\n\nLine 3."
        result, changed = insert_section(content, section)
        assert changed is True
        assert "Line 1." in result
        assert "[[wikilink]]" in result
        assert result.index("Line 1.") < result.index("## 开放问题")
