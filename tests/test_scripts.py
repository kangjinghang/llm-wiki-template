"""Tests for llm-wiki-template scripts."""

import subprocess
import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from create_page import slugify, fill_template, fill_fm_field, type_to_dir

REPO_ROOT = Path(__file__).resolve().parent.parent


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


# --- create_page CLI integration ---

class TestCreatePageCLI:
    def test_creates_page_with_valid_frontmatter(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "concepts").mkdir(parents=True)
        (wiki / "_templates" / "concept.md").write_text(
            '---\ntitle: ""\ntype: concept\n---\n# {title}\n', encoding="utf-8"
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "concept", "Test Page", "--tags", "A,B"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "test-page.md"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Test Page" in content

    def test_rejects_duplicate_page(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "concepts").mkdir(parents=True)
        (wiki / "_templates" / "concept.md").write_text(
            '---\ntitle: ""\ntype: concept\n---\n# {title}\n', encoding="utf-8"
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        cmd = [sys.executable, str(script), str(wiki), "concept", "Dup"]
        subprocess.run(cmd, capture_output=True, text=True)
        proc2 = subprocess.run(cmd, capture_output=True, text=True)
        assert proc2.returncode != 0
        assert "already exists" in proc2.stderr


# --- scaffold + lint integration ---

class TestScaffoldAndLint:
    def test_scaffold_creates_structure(self, tmp_path):
        wiki = tmp_path / "mywiki"
        script = REPO_ROOT / "scripts" / "scaffold.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert (wiki / "CLAUDE.md").exists()
        assert (wiki / "wiki" / "index.md").exists()
        assert (wiki / "hot.md").exists()
        assert (wiki / "questions.md").exists()
        assert (wiki / "raw" / "articles").is_dir()
        assert (wiki / "wiki" / "concepts").is_dir()

    def test_lint_runs_without_crash_on_scaffold(self, tmp_path):
        wiki = tmp_path / "mywiki"
        scaffold = REPO_ROOT / "scripts" / "scaffold.py"
        subprocess.run(
            [sys.executable, str(scaffold), str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        proc = subprocess.run(
            [sys.executable, str(lint), str(wiki)],
            capture_output=True, text=True,
        )
        assert "Traceback" not in proc.stderr
