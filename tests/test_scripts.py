"""Tests for llm-wiki-template scripts."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from create_page import slugify, fill_template, fill_fm_field, type_to_dir


# --- slugify ---

class TestSlugify:
    def test_basic_english(self):
        assert slugify("Attention Mechanism") == "attention-mechanism"

    def test_special_chars_replaced_with_hyphen(self):
        assert slugify("Attention/Mechanism (2024)") == "attention-mechanism-2024"

    def test_multiple_hyphens_collapsed(self):
        assert slugify("A  --  B") == "a-b"

    def test_chinese_preserved(self):
        assert slugify("因子拥挤") == "因子拥挤"

    def test_mixed_chinese_english(self):
        assert slugify("Transformer 变换器") == "transformer-变换器"

    def test_leading_trailing_hyphens_stripped(self):
        assert slugify("--hello--") == "hello"

    def test_empty_string(self):
        assert slugify("") == "untitled"

    def test_only_special_chars(self):
        assert slugify("!!!") == "untitled"

    def test_underscores_to_hyphens(self):
        assert slugify("hello_world") == "hello-world"

    def test_multiple_spaces(self):
        assert slugify("  多    空格  测试  ") == "多-空格-测试"


# --- fill_fm_field ---

class TestFillFmField:
    def test_fill_empty_field(self):
        content = "---\ntitle: \"\"\n---"
        result = fill_fm_field(content, "title", '"Hello"')
        assert 'title: "Hello"' in result

    def test_fill_preserves_other_fields(self):
        content = "---\ntitle: \"\"\ntype: concept\n---"
        result = fill_fm_field(content, "title", '"Test"')
        assert 'type: concept' in result
        assert 'title: "Test"' in result


# --- fill_template ---

class TestFillTemplate:
    def test_fills_date_and_title(self):
        template = "---\ntitle: \"\"\n---\n# {title}\nCreated: {date}"
        result = fill_template(template, "Test", None, "2026-05-19", [], [], None)
        assert "# Test" in result
        assert "Created: 2026-05-19" in result

    def test_fills_tags(self):
        template = "---\ntags: []\n---"
        result = fill_template(template, "X", None, "2026-01-01", ["AI", "ML"], [], None)
        assert "tags: [AI, ML]" in result


# --- type_to_dir ---

class TestTypeToDir:
    def test_source(self):
        assert type_to_dir("source") == "sources"

    def test_concept(self):
        assert type_to_dir("concept") == "concepts"

    def test_entity(self):
        assert type_to_dir("entity") == "entities"

    def test_synthesis(self):
        assert type_to_dir("synthesis") == "syntheses"

    def test_comparison(self):
        assert type_to_dir("comparison") == "syntheses"

    def test_unknown(self):
        assert type_to_dir("unknown") == "concepts"


# --- parse_frontmatter (from lint_wiki.py) ---

class TestParseFrontmatter:
    @staticmethod
    def _get_parser():
        from lint_wiki import parse_frontmatter
        return parse_frontmatter

    def test_simple_string(self):
        parse = self._get_parser()
        text = '---\ntitle: "Hello"\ntype: concept\n---\nBody'
        result = parse(text)
        assert result == {"title": "Hello", "type": "concept"}

    def test_array_field(self):
        parse = self._get_parser()
        text = '---\ntags: [AI, ML]\n---\nBody'
        result = parse(text)
        assert result["tags"] == ["AI", "ML"]

    def test_empty_array(self):
        parse = self._get_parser()
        text = '---\ntags: []\n---\nBody'
        result = parse(text)
        assert result["tags"] == []

    def test_no_frontmatter(self):
        parse = self._get_parser()
        result = parse("Just body text")
        assert result is None

    def test_integer_array(self):
        parse = self._get_parser()
        text = '---\ntarget_lines: [10, 15]\n---\nBody'
        result = parse(text)
        assert result["target_lines"] == [10, 15]
