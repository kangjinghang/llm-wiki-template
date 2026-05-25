"""Tests for merge_frontmatter.py script."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from merge_frontmatter import parse_frontmatter, merge_array_field, serialize_frontmatter


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


class TestTripleBracketRejection:
    def test_rejects_triple_bracket_in_sources_arg(self, tmp_path):
        """Reject --sources containing [[[ syntax."""
        page = tmp_path / "test.md"
        page.write_text('---\ntitle: "Test"\nsources:\n  - "[[a]]"\n---\nBody\n', encoding="utf-8")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--sources", "[[[bad]]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "[[[" in proc.stderr

    def test_rejects_triple_bracket_in_related_arg(self, tmp_path):
        """Reject --related containing [[[ syntax."""
        page = tmp_path / "test.md"
        page.write_text('---\ntitle: "Test"\nrelated:\n  - "[[a]]"\n---\nBody\n', encoding="utf-8")
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "merge_frontmatter.py"),
             str(page), "--related", "[[[bad]]]"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "[[[" in proc.stderr
