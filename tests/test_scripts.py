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

    def test_does_not_match_body(self):
        content = "---\ntitle: \"\"\n---\ntitle: should not change"
        result = fill_fm_field(content, "title", '"Replaced"')
        assert 'title: "Replaced"' in result
        assert "title: should not change" in result


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
            '---\ntitle: ""\ntype: concept\ntags: []\n---\n# {title}\n', encoding="utf-8"
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
        assert 'title: "Test Page"' in content
        assert "type: concept" in content
        assert "tags: [A, B]" in content
        assert "# Test Page" in content

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

    def test_synthesis_fallback_fixes_type(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "syntheses").mkdir(parents=True)
        (wiki / "_templates" / "concept.md").write_text(
            '---\ntitle: ""\ntype: concept\n---\n# {title}\n', encoding="utf-8"
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "synthesis", "Syn Test"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "syntheses" / "syn-test.md"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "type: synthesis" in content

    def test_raw_path_warning(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "sources").mkdir(parents=True)
        (wiki / "_templates" / "source.md").write_text(
            '---\ntitle: ""\ntype: source\nraw_path: ""\n---\n# {title}\n', encoding="utf-8"
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "source", "S1",
             "--raw-path", "raw/articles/nonexistent.md"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "WARNING" in proc.stderr


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
            capture_output=True, text=True, encoding="utf-8",
        )
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        proc = subprocess.run(
            [sys.executable, str(lint), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert "Traceback" not in proc.stderr

    def test_lint_exits_0_on_healthy_wiki(self, tmp_path):
        wiki = tmp_path / "mywiki"
        scaffold = REPO_ROOT / "scripts" / "scaffold.py"
        subprocess.run(
            [sys.executable, str(scaffold), str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        proc = subprocess.run(
            [sys.executable, str(lint), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0

    def test_lint_exits_1_on_dead_wikilink(self, tmp_path):
        wiki = tmp_path / "mywiki"
        scaffold = REPO_ROOT / "scripts" / "scaffold.py"
        subprocess.run(
            [sys.executable, str(scaffold), str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        (wiki / "wiki" / "concepts" / "broken.md").write_text(
            "---\ntitle: Broken\ntype: concept\n---\n[[NonExistentPage]]\n",
            encoding="utf-8",
        )
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        proc = subprocess.run(
            [sys.executable, str(lint), str(wiki)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "Dead wikilinks" in proc.stdout


# --- audit_review ---

class TestAuditReview:
    def test_audit_review_runs(self, tmp_path):
        wiki = tmp_path / "mywiki"
        scaffold = REPO_ROOT / "scripts" / "scaffold.py"
        subprocess.run(
            [sys.executable, str(scaffold), str(wiki), "Test Wiki"],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Write a sample audit file
        (wiki / "audit" / "audit-001.md").write_text(
            '---\nid: audit-001\ntarget: wiki/concepts/test.md\n'
            'target_lines: [1, 5]\nanchor_before: ""\nanchor_text: "test"\n'
            'anchor_after: ""\nseverity: warn\nauthor: user\n'
            'source: manual\ncreated: 2026-05-19\nstatus: open\n---\n'
            '# Comment\n\nThis is wrong.',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "audit_review.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "--open"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0
        assert "audit-001" in proc.stdout

    def test_audit_review_no_files(self, tmp_path):
        wiki = tmp_path / "mywiki"
        scaffold = REPO_ROOT / "scripts" / "scaffold.py"
        subprocess.run(
            [sys.executable, str(scaffold), str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        script = REPO_ROOT / "scripts" / "audit_review.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "--open"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "No open audit files found" in proc.stdout


# --- load_tag_taxonomy ---

class TestLoadTagTaxonomy:
    @staticmethod
    def _get_loader():
        from lint_wiki import load_tag_taxonomy
        return load_tag_taxonomy

    def test_loads_taxonomy_from_claude_md(self, tmp_path):
        loader = self._get_loader()
        (tmp_path / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n"
            "- **Topics**: deep-learning, nlp\n"
            "- **Methods**: training\n\n"
            "## Other Section\n",
            encoding="utf-8",
        )
        result = loader(tmp_path)
        assert result is not None
        assert "deep-learning" in result
        assert "nlp" in result
        assert "training" in result

    def test_loads_taxonomy_from_schema_subdir(self, tmp_path):
        loader = self._get_loader()
        (tmp_path / "_schema").mkdir()
        (tmp_path / "_schema" / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n- deep-learning\n- nlp\n\n## Next\n",
            encoding="utf-8",
        )
        result = loader(tmp_path)
        assert result is not None
        assert "deep-learning" in result

    def test_returns_none_when_no_taxonomy(self, tmp_path):
        loader = self._get_loader()
        (tmp_path / "CLAUDE.md").write_text("## Just a doc\n\nNo taxonomy here.\n", encoding="utf-8")
        result = loader(tmp_path)
        assert result is None

    def test_returns_none_when_no_schema_file(self, tmp_path):
        loader = self._get_loader()
        result = loader(tmp_path)
        assert result is None

    def test_extracts_bold_prefixed_tags(self, tmp_path):
        loader = self._get_loader()
        (tmp_path / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n"
            "- **Topics**: deep-learning, nlp, computer-vision\n"
            "- **Meta**: comparison, prediction\n\n"
            "## Writing Style\n",
            encoding="utf-8",
        )
        result = loader(tmp_path)
        assert result is not None
        assert "computer-vision" in result
        assert "prediction" in result

    def test_tags_are_lowercase(self, tmp_path):
        loader = self._get_loader()
        (tmp_path / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n- Deep-Learning\n- NLP\n\n## End\n",
            encoding="utf-8",
        )
        result = loader(tmp_path)
        assert result is not None
        assert "deep-learning" in result
        assert "nlp" in result
        assert "Deep-Learning" not in result


# --- Pass 9: tag taxonomy lint integration ---

class TestTagTaxonomyLint:
    def test_flags_invalid_tag(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        # Create a minimal wiki with a CLAUDE.md that has a taxonomy
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n- deep-learning\n- nlp\n\n## End\n",
            encoding="utf-8",
        )
        (tmp_path / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        # Page with a tag NOT in taxonomy
        (tmp_path / "wiki" / "concepts" / "test.md").write_text(
            '---\ntitle: Test\ntype: concept\ntags: [deep-learning, fake-tag]\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "fake-tag" in proc.stdout

    def test_passes_with_valid_tags(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            "## Tag Taxonomy\n\n- deep-learning\n- nlp\n\n## End\n",
            encoding="utf-8",
        )
        (tmp_path / "wiki" / "index.md").write_text("# Index\n\n- [[test]]\n", encoding="utf-8")
        (tmp_path / "wiki" / "concepts" / "test.md").write_text(
            '---\ntitle: Test\ntype: concept\ntags: [deep-learning, nlp]\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0

    def test_skips_when_no_taxonomy(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "CLAUDE.md").write_text("## Just Docs\n\nNo taxonomy.\n", encoding="utf-8")
        (tmp_path / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        (tmp_path / "wiki" / "concepts" / "test.md").write_text(
            '---\ntitle: Test\ntype: concept\ntags: [anything]\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        # Should skip tag check entirely (no taxonomy) — other issues may exist but not tag-related
        assert "No tag taxonomy found" in proc.stdout


# --- Pass 10: stale page lint integration ---

class TestStalePageLint:
    def test_flags_past_review_date(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        (tmp_path / "wiki" / "concepts" / "stale.md").write_text(
            '---\ntitle: Stale\ntype: concept\nreview_by: "2020-01-01"\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "Pages past review date" in proc.stdout

    def test_passes_with_future_review_date(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "wiki" / "index.md").write_text("# Index\n\n- [[fresh]]\n", encoding="utf-8")
        (tmp_path / "wiki" / "concepts" / "fresh.md").write_text(
            '---\ntitle: Fresh\ntype: concept\nreview_by: "2099-12-31"\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0

    def test_passes_with_empty_review_by(self, tmp_path):
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        (tmp_path / "wiki" / "index.md").write_text("# Index\n\n- [[empty]]\n", encoding="utf-8")
        (tmp_path / "wiki" / "concepts" / "empty.md").write_text(
            '---\ntitle: Empty\ntype: concept\nreview_by: ""\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0


# --- --compute-hash integration ---

class TestComputeHash:
    def test_adds_raw_hash_to_frontmatter(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "sources").mkdir(parents=True)
        (wiki / "raw" / "articles").mkdir(parents=True)
        # Create a raw file to hash
        raw_content = "This is the raw source content."
        (wiki / "raw" / "articles" / "test.md").write_text(raw_content, encoding="utf-8")
        (wiki / "_templates" / "source.md").write_text(
            '---\ntitle: ""\ntype: source\nraw_path: ""\n---\n# {title}\n',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "source", "Test Source",
             "--raw-path", "raw/articles/test.md", "--compute-hash"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "sources" / "test-source.md"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "raw_hash:" in content
        # Verify the hash is correct
        import hashlib
        expected_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
        assert expected_hash in content

    def test_no_hash_without_flag(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "sources").mkdir(parents=True)
        (wiki / "raw" / "articles").mkdir(parents=True)
        (wiki / "raw" / "articles" / "test.md").write_text("content", encoding="utf-8")
        (wiki / "_templates" / "source.md").write_text(
            '---\ntitle: ""\ntype: source\nraw_path: ""\n---\n# {title}\n',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "source", "No Hash",
             "--raw-path", "raw/articles/test.md"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "sources" / "no-hash.md"
        content = out.read_text(encoding="utf-8")
        assert "raw_hash:" not in content

    def test_no_hash_when_raw_path_missing(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "sources").mkdir(parents=True)
        (wiki / "_templates" / "source.md").write_text(
            '---\ntitle: ""\ntype: source\nraw_path: ""\n---\n# {title}\n',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "source", "Missing Raw",
             "--raw-path", "raw/articles/nonexistent.md", "--compute-hash"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        out = wiki / "wiki" / "sources" / "missing-raw.md"
        content = out.read_text(encoding="utf-8")
        assert "raw_hash:" not in content

    def test_lint_flags_hash_mismatch(self, tmp_path):
        """When raw file changes after ingest, lint should detect the mismatch."""
        import hashlib
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "sources").mkdir(parents=True)
        (tmp_path / "raw" / "articles").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        # Create raw file and compute its hash
        raw_file = tmp_path / "raw" / "articles" / "test.md"
        original_content = "Original content"
        raw_file.write_text(original_content, encoding="utf-8")
        original_hash = hashlib.sha256(original_content.encode()).hexdigest()
        # Create wiki page with the hash
        (tmp_path / "wiki" / "index.md").write_text("# Index\n\n- [[test-src]]\n", encoding="utf-8")
        (tmp_path / "wiki" / "sources" / "test-src.md").write_text(
            f'---\ntitle: Test\ntype: source\nraw_path: "raw/articles/test.md"\n'
            f'raw_hash: "{original_hash}"\n---\nBody\n',
            encoding="utf-8",
        )
        # Modify the raw file
        raw_file.write_text("Modified content", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 1
        assert "raw_hash mismatch" in proc.stdout

    def test_lint_passes_when_hash_matches(self, tmp_path):
        """When raw file is unchanged, lint should pass hash check."""
        import hashlib
        lint = REPO_ROOT / "scripts" / "lint_wiki.py"
        (tmp_path / "wiki" / "sources").mkdir(parents=True)
        (tmp_path / "raw" / "articles").mkdir(parents=True)
        (tmp_path / "log").mkdir()
        (tmp_path / "audit").mkdir()
        raw_file = tmp_path / "raw" / "articles" / "test.md"
        content = "Stable content"
        raw_file.write_text(content, encoding="utf-8")
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        (tmp_path / "wiki" / "index.md").write_text("# Index\n\n- [[test-src]]\n", encoding="utf-8")
        (tmp_path / "wiki" / "sources" / "test-src.md").write_text(
            f'---\ntitle: Test\ntype: source\nraw_path: "raw/articles/test.md"\n'
            f'raw_hash: "{content_hash}"\n---\nBody\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(lint), str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert proc.returncode == 0
        assert "raw_hash mismatch" not in proc.stdout


# --- --review-by integration ---

class TestReviewBy:
    def test_sets_review_by_in_frontmatter(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "concepts").mkdir(parents=True)
        (wiki / "_templates" / "concept.md").write_text(
            '---\ntitle: ""\ntype: concept\nreview_by: ""\n---\n# {title}\n',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "concept", "Time Sensitive",
             "--review-by", "2026-06-01"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "time-sensitive.md"
        content = out.read_text(encoding="utf-8")
        assert 'review_by: "2026-06-01"' in content

    def test_no_review_by_without_flag(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "_templates").mkdir(parents=True)
        (wiki / "wiki" / "concepts").mkdir(parents=True)
        (wiki / "_templates" / "concept.md").write_text(
            '---\ntitle: ""\ntype: concept\nreview_by: ""\n---\n# {title}\n',
            encoding="utf-8",
        )
        script = REPO_ROOT / "scripts" / "create_page.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(wiki), "concept", "No Review"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "no-review.md"
        content = out.read_text(encoding="utf-8")
        assert 'review_by: ""' in content


# --- naming convention lint ---

class TestNamingConventionLint:
    def test_flags_uppercase_filename(self, tmp_path):
        """Pages with uppercase characters in filename should be flagged."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        # Create a page with uppercase filename (LLM might do this)
        (wiki / "wiki" / "concepts" / "ESP-Factor.md").write_text(
            "---\ntitle: ESP Factor\ntype: concept\n---\nContent\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "naming" in proc.stdout.lower() or "uppercase" in proc.stdout.lower() or "case" in proc.stdout.lower()

    def test_passes_all_lowercase(self, tmp_path):
        """All-lowercase filenames should pass naming check."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        (wiki / "wiki" / "concepts" / "esp-factor.md").write_text(
            "---\ntitle: ESP Factor\ntype: concept\n---\nContent\n",
            encoding="utf-8",
        )
        # Add to index to avoid orphan/missing-index issues
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "*(none yet)*", "- [[esp-factor]]", 1
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0


# --- source template: sources field should be absent ---

class TestSourceTemplateNoSources:
    def test_source_template_has_no_sources_field(self):
        template = (REPO_ROOT / "_templates" / "source.md").read_text(encoding="utf-8")
        # source pages use raw_path, not sources — the field should not be in the template
        fm_section = template.split("---")[1]
        assert "sources" not in fm_section or "sources: []" not in fm_section
        # But raw_path MUST be there
        assert "raw_path" in fm_section


# --- raw_hash presence check ---

class TestRawHashPresence:
    def test_flags_source_with_raw_path_but_no_hash(self, tmp_path):
        """Source pages with raw_path should also have raw_hash."""
        wiki = tmp_path / "mywiki"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scaffold.py"),
             str(wiki), "Test Wiki"],
            capture_output=True, text=True,
        )
        # Create a source page with raw_path but no raw_hash
        raw = wiki / "raw" / "articles" / "test.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("Some content", encoding="utf-8")
        page = wiki / "wiki" / "sources" / "test-source.md"
        page.write_text(
            '---\ntitle: "Test"\ntype: source\nraw_path: "raw/articles/test.md"\n---\nContent\n',
            encoding="utf-8",
        )
        # Add to index
        index = wiki / "wiki" / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8").replace("*(none yet)*", "- [[test-source]]", 1),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint_wiki.py"), str(wiki)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "raw_hash" in proc.stdout.lower()
