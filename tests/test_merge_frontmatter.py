"""Tests for merge_frontmatter.py script."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from merge_frontmatter import (
    parse_frontmatter, merge_array_field, serialize_frontmatter,
    merge_related_pages_section, merge_timeline_entries,
)


class TestParseFrontmatter:
    def test_basic_parse(self):
        """Parse a file with standard frontmatter."""
        content = '---\ntitle: "Test"\ntype: concept\ntags: [a, b]\n---\n\nBody text\n'
        fm, body, raw_fm = parse_frontmatter(content)
        assert fm["title"] == '"Test"'
        assert fm["type"] == "concept"
        assert fm["tags"] == "[a, b]"
        assert body == "\nBody text\n"

    def test_list_format_sources(self):
        """Parse frontmatter with YAML list format arrays."""
        content = '---\ntitle: "Test"\nsources:\n  - "[[a]]"\n  - "[[b]]"\n---\nBody\n'
        fm, body, raw_fm = parse_frontmatter(content)
        assert '  - "[[a]]"' in raw_fm
        assert '  - "[[b]]"' in raw_fm

    def test_no_frontmatter(self):
        """File without frontmatter returns None."""
        content = "Just body text\n"
        fm, body, raw_fm = parse_frontmatter(content)
        assert fm is None
        assert body == content


class TestMergeArrayField:
    def test_append_to_list_format(self):
        """Append new item to YAML list format array."""
        raw_fm = 'title: "Test"\nsources:\n  - "[[a]]"\n  - "[[b]]"\n'
        result = merge_array_field(raw_fm, "sources", ["[[c]]"])
        assert '  - "[[c]]"' in result
        assert '  - "[[a]]"' in result
        assert '  - "[[b]]"' in result

    def test_dedup_list_format(self):
        """Skip items that already exist."""
        raw_fm = 'title: "Test"\nsources:\n  - "[[a]]"\n  - "[[b]]"\n'
        result = merge_array_field(raw_fm, "sources", ["[[a]]", "[[c]]"])
        assert result.count('  - "[[a]]"') == 1
        assert '  - "[[c]]"' in result

    def test_append_to_inline_format(self):
        """Append new item to inline format array like tags: [a, b]."""
        raw_fm = 'title: "Test"\ntags: [a, b]\n'
        result = merge_array_field(raw_fm, "tags", ["c"])
        assert "c" in result
        assert "a" in result
        assert "b" in result

    def test_dedup_inline_format(self):
        """Skip items that already exist in inline format."""
        raw_fm = 'title: "Test"\ntags: [a, b]\n'
        result = merge_array_field(raw_fm, "tags", ["a", "c"])
        # Check the inline array specifically — "a" appears once in the array value
        import re
        match = re.search(r"tags:\s*\[(.+?)\]", result)
        assert match is not None
        items = [item.strip() for item in match.group(1).split(",")]
        assert items == ["a", "b", "c"]

    def test_no_changes_returns_same(self):
        """When all items already exist, return unchanged."""
        raw_fm = 'title: "Test"\ntags: [a, b]\n'
        result = merge_array_field(raw_fm, "tags", ["a", "b"])
        assert result == raw_fm

    def test_field_not_present_skips(self):
        """When field doesn't exist in frontmatter, skip silently."""
        raw_fm = 'title: "Test"\ntags: [a]\n'
        result = merge_array_field(raw_fm, "related", ["[[x]]"])
        assert result == raw_fm


class TestSerializeFrontmatter:
    def test_roundtrip(self):
        """Serialize preserves original format."""
        content = '---\ntitle: "Test"\ntype: concept\n---\nBody\n'
        fm, body, raw_fm = parse_frontmatter(content)
        result = serialize_frontmatter(raw_fm, body)
        assert result == content


class TestTripleBracketAutoFix:
    def test_auto_fixes_triple_bracket_in_sources_arg(self, tmp_path):
        """Auto-fix --sources containing [[[ syntax."""
        page = tmp_path / "test.md"
        page.write_text('---\ntitle: "Test"\nsources:\n  - "[[a]]"\n---\nBody\n', encoding="utf-8")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--sources", "[[[bad]]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "Auto-fixing" in proc.stderr
        # Verify the file has [[bad]] not [[[bad]]]
        result = page.read_text(encoding="utf-8")
        assert "[[bad]]" in result
        assert "[[[bad]]]" not in result

    def test_auto_fixes_triple_bracket_in_related_arg(self, tmp_path):
        """Auto-fix --related containing [[[ syntax."""
        page = tmp_path / "test.md"
        page.write_text('---\ntitle: "Test"\nrelated:\n  - "[[a]]"\n---\nBody\n', encoding="utf-8")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--related", "[[[bad]]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "Auto-fixing" in proc.stderr
        result = page.read_text(encoding="utf-8")
        assert "[[bad]]" in result
        assert "[[[bad]]]" not in result


class TestMergeRelatedPages:
    def test_append_to_existing_section(self):
        """Append new entries to existing Related Pages section."""
        body = (
            "\n## Summary\nSome text\n"
            "\n## Related Pages / 关联页面\n"
            "\n- [[开源金工]] — W式切割方法\n"
            "\n## Sources / 来源\n\n- ref\n"
        )
        result, changed = merge_related_pages_section(body, ["[[测试页面]] — 测试描述"])
        assert changed is True
        assert "[[测试页面]] — 测试描述" in result
        assert "[[开源金工]] — W式切割方法" in result

    def test_dedup_by_wikilink(self):
        """Skip entries whose wikilink target already exists."""
        body = (
            "\n## Related Pages / 关联页面\n"
            "\n- [[开源金工]] — old desc\n"
        )
        result, changed = merge_related_pages_section(body, ["[[开源金工]] — new desc"])
        assert changed is False
        assert result == body

    def test_create_section_if_missing(self):
        """Create Related Pages section before Sources heading."""
        body = (
            "\n## Summary\nSome text\n"
            "\n## Sources / 来源\n\n- ref\n"
        )
        result, changed = merge_related_pages_section(body, ["[[Foo]] — desc"])
        assert changed is True
        assert "## Related Pages / 关联页面" in result
        assert "[[Foo]] — desc" in result
        # Section should appear before Sources
        assert result.index("Related Pages") < result.index("## Sources")

    def test_create_section_at_eof(self):
        """Create Related Pages section at end when no Sources heading."""
        body = "\n## Summary\nSome text\n"
        result, changed = merge_related_pages_section(body, ["[[Foo]] — desc"])
        assert changed is True
        assert "## Related Pages / 关联页面" in result

    def test_no_entries_returns_unchanged(self):
        """Empty entries list returns unchanged."""
        body = "\n## Summary\nText\n"
        result, changed = merge_related_pages_section(body, [])
        assert changed is False
        assert result == body

    def test_english_heading_variant(self):
        """Handle ## Related Pages (English-only heading)."""
        body = "\n## Related Pages\n\n- [[Foo]] — desc\n"
        result, changed = merge_related_pages_section(body, ["[[Bar]] — desc2"])
        assert changed is True
        assert "[[Bar]] — desc2" in result


class TestMergeTimeline:
    def test_append_to_existing_timeline(self):
        """Append new timeline entries."""
        body = (
            "\n## Key Facts / 关键事实\n"
            "\n- 研究时间线：\n"
            "  - 2020.06：《Old》（Authors）——desc\n"
            "\n## Sources / 来源\n"
        )
        result, changed = merge_timeline_entries(body, ["2021.03：《New》（Authors）——desc2"])
        assert changed is True
        assert "2021.03：《New》（Authors）——desc2" in result
        assert "2020.06：《Old》（Authors）——desc" in result

    def test_dedup_by_exact_text(self):
        """Skip entries that already exist."""
        body = (
            "\n## Key Facts / 关键事实\n"
            "\n- 研究时间线：\n"
            "  - 2020.06：《Old》（Authors）——desc\n"
        )
        result, changed = merge_timeline_entries(body, ["2020.06：《Old》（Authors）——desc"])
        assert changed is False
        assert result == body

    def test_no_key_facts_section_skips(self):
        """Skip if no Key Facts section."""
        body = "\n## Summary\nText\n"
        result, changed = merge_timeline_entries(body, ["2020.06：entry"])
        assert changed is False
        assert result == body

    def test_no_timeline_sublist_skips(self):
        """Skip if Key Facts exists but no timeline sublist."""
        body = "\n## Key Facts / 关键事实\n\nSome facts\n"
        result, changed = merge_timeline_entries(body, ["2020.06：entry"])
        assert changed is False
        assert result == body

    def test_no_entries_returns_unchanged(self):
        """Empty entries list returns unchanged."""
        body = "\n## Key Facts / 关键事实\n"
        result, changed = merge_timeline_entries(body, [])
        assert changed is False
        assert result == body


class TestCombinedUpdate:
    def test_frontmatter_and_body_single_write(self, tmp_path):
        """Frontmatter + body updates in a single write."""
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsources:\n  - "[[a]]"\n---\n'
            "\n## Key Facts / 关键事实\n"
            "\n- 研究时间线：\n"
            "  - 2020.06：《Old》（A）——d\n"
            "\n## Sources / 来源\n",
            encoding="utf-8",
        )
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--sources", "[[b]]", "--timeline", "2021.03：《New》（A）——d2"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        result = page.read_text(encoding="utf-8")
        assert '  - "[[b]]"' in result
        assert "2021.03：《New》（A）——d2" in result

    def test_related_pages_and_frontmatter(self, tmp_path):
        """--related-pages creates section and appends alongside frontmatter update."""
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsources:\n  - "[[a]]"\n---\n'
            "\n## Summary\nText\n"
            "\n## Sources / 来源\n",
            encoding="utf-8",
        )
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--related-pages", "[[Foo]] — desc"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        result = page.read_text(encoding="utf-8")
        assert "## Related Pages / 关联页面" in result
        assert "[[Foo]] — desc" in result
        # Should be before Sources
        assert result.index("Related Pages") < result.index("## Sources")


class TestBatchMode:
    """Test multi-file batch mode: same updates applied to multiple files."""

    def _make_page(self, tmp_path: Path, name: str, sources: str = "") -> Path:
        page = tmp_path / name
        page.write_text(
            f'---\ntitle: "{name}"\nsources:\n  - "{sources}"\n---\n\n## Summary\n\nText.\n',
            encoding="utf-8",
        )
        return page

    def test_batch_sources(self, tmp_path):
        """--sources applied to multiple files in one call."""
        p1 = self._make_page(tmp_path, "a.md", "[[old]]")
        p2 = self._make_page(tmp_path, "b.md", "[[old]]")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(p1), str(p2), "--sources", "[[new]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert '[[new]]' in p1.read_text(encoding="utf-8")
        assert '[[new]]' in p2.read_text(encoding="utf-8")

    def test_batch_dedup_per_file(self, tmp_path):
        """Dedup works independently per file in batch."""
        p1 = self._make_page(tmp_path, "a.md", "[[existing]]")
        p2 = self._make_page(tmp_path, "b.md", "[[old]]")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(p1), str(p2), "--sources", "[[existing]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        # p1 should show "No changes needed" since [[existing]] already there
        assert "No changes needed" in proc.stderr or "No changes needed" in proc.stdout

    def test_batch_related_pages(self, tmp_path):
        """--related-pages applied to multiple files."""
        p1 = tmp_path / "a.md"
        p1.write_text('---\ntitle: "A"\n---\n\n## Summary\n\n## Sources / 来源\n', encoding="utf-8")
        p2 = tmp_path / "b.md"
        p2.write_text('---\ntitle: "B"\n---\n\n## Summary\n\n## Sources / 来源\n', encoding="utf-8")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(p1), str(p2), "--related-pages", "[[Foo]] — desc"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "[[Foo]]" in p1.read_text(encoding="utf-8")
        assert "[[Foo]]" in p2.read_text(encoding="utf-8")
