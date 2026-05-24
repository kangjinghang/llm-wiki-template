"""Tests for extract_knowledge.py script."""

import json
import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract_knowledge import load_api_config, extract_claude_md_sections, build_extraction_prompt, parse_llm_response, derive_slug, resolve_article_path


class TestDeriveSlug:
    def test_basic_article_name(self):
        """Derive slug from simple article filename."""
        result = derive_slug("raw/articles/[202011040800]中国Barra模型.md")
        assert result == "中国barra模型"

    def test_removes_timestamp_prefix(self):
        """Strip [YYYYMMDDHHMM] timestamp prefix from filename."""
        result = derive_slug("raw/articles/[202011101842]有关Barra模型的思考.md")
        assert result == "有关barra模型的思考"

    def test_removes_extension(self):
        """Strip .md extension."""
        result = derive_slug("raw/articles/test-article.md")
        assert result == "test-article"


class TestLoadApiConfig:
    def test_reads_settings(self):
        """Load config from a valid settings.json."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            settings = {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "test-key-123",
                    "ANTHROPIC_BASE_URL": "https://api.test.com",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL": "test-model"
                }
            }
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            config = load_api_config(settings_path)
            assert config["api_key"] == "test-key-123"
            assert config["base_url"] == "https://api.test.com"
            assert config["model"] == "test-model"

    def test_missing_settings_file(self):
        """Return None when settings file doesn't exist."""
        config = load_api_config(Path("/nonexistent/settings.json"))
        assert config is None

    def test_missing_env_field(self):
        """Return None when settings has no env field."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text('{"model": "opus"}', encoding="utf-8")
            config = load_api_config(settings_path)
            assert config is None


class TestExtractClaudeMdSections:
    def test_extracts_required_sections(self):
        """Extract Page Thresholds, Naming Conventions, Tag Taxonomy, Writing Style."""
        claude_md = """## Naming Conventions

- **Concept pages**: lowercase with hyphens

## Page Thresholds

- **Create a page** when central to a source

## Tag Taxonomy

### 品种
- 股票, 债券

## Writing Style

- **Body text**: write summaries in Chinese

## Notes for the LLM

- Some note
"""
        result = extract_claude_md_sections(claude_md)
        assert "Page Thresholds" in result
        assert "Naming Conventions" in result
        assert "Tag Taxonomy" in result
        assert "Writing Style" in result
        assert "Notes for the LLM" not in result

    def test_missing_section_returns_empty(self):
        """Return empty string for sections not found."""
        claude_md = "## Something Else\n\nHello"
        result = extract_claude_md_sections(claude_md)
        assert result == ""


class TestBuildExtractionPrompt:
    def test_contains_claude_md_rules(self):
        """Prompt includes the CLAUDE.md rules text."""
        rules = "## Page Thresholds\n- Create a page when central"
        result = build_extraction_prompt(rules, "## Sources\n- test", "Article text here")
        assert "Page Thresholds" in result
        assert "Article text here" in result
        assert "## Sources" in result

    def test_contains_json_schema(self):
        """Prompt includes the JSON output format."""
        result = build_extraction_prompt("rules", "index", "article")
        assert '"title"' in result
        assert '"concepts"' in result
        assert '"entities"' in result


class TestParseLlmResponse:
    def test_clean_json(self):
        """Parse valid JSON string."""
        text = '{"title": "Test", "concepts": [], "entities": [], "tags": [], "key_findings": [], "relations": []}'
        result = parse_llm_response(text)
        assert result["title"] == "Test"

    def test_json_in_markdown_block(self):
        """Extract JSON from ```json ... ``` wrapper."""
        text = '```json\n{"title": "Test", "concepts": [], "entities": [], "tags": [], "key_findings": [], "relations": []}\n```'
        result = parse_llm_response(text)
        assert result["title"] == "Test"

    def test_missing_fields_filled(self):
        """Fill missing optional fields with defaults."""
        text = '{"title": "Test"}'
        result = parse_llm_response(text)
        assert result["concepts"] == []
        assert result["entities"] == []
        assert result["tags"] == []
        assert result["key_findings"] == []
        assert result["relations"] == []

    def test_invalid_json_returns_none(self):
        """Return None for unparseable text."""
        text = "This is not JSON at all"
        result = parse_llm_response(text)
        assert result is None


class TestResolveArticlePath:
    """Test --next flag: find first unprocessed article path."""

    def test_next_finds_unprocessed(self, tmp_path):
        """--next returns the first unprocessed article relative path."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        sources_dir = tmp_path / "wiki" / "sources"
        sources_dir.mkdir(parents=True)

        (raw_dir / "[20200101]alpha.md").write_text("A", encoding="utf-8")
        (raw_dir / "[20200102]beta.md").write_text("B", encoding="utf-8")

        result = resolve_article_path(tmp_path, use_next=True)
        assert result == "raw/articles/[20200101]alpha.md"

    def test_next_skips_processed(self, tmp_path):
        """--next skips articles that have source pages."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        sources_dir = tmp_path / "wiki" / "sources"
        sources_dir.mkdir(parents=True)

        (raw_dir / "[20200101]alpha.md").write_text("A", encoding="utf-8")
        (raw_dir / "[20200102]beta.md").write_text("B", encoding="utf-8")

        # Mark alpha as processed
        (sources_dir / "alpha.md").write_text(
            '---\nraw_path: "raw/articles/[20200101]alpha.md"\n---\n', encoding="utf-8"
        )

        result = resolve_article_path(tmp_path, use_next=True)
        assert result == "raw/articles/[20200102]beta.md"

    def test_next_returns_none_when_all_processed(self, tmp_path):
        """--next returns None when all articles have source pages."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        sources_dir = tmp_path / "wiki" / "sources"
        sources_dir.mkdir(parents=True)

        (raw_dir / "[20200101]alpha.md").write_text("A", encoding="utf-8")
        (sources_dir / "alpha.md").write_text(
            '---\nraw_path: "raw/articles/[20200101]alpha.md"\n---\n', encoding="utf-8"
        )

        result = resolve_article_path(tmp_path, use_next=True)
        assert result is None

    def test_explicit_path_ignores_unprocessed(self, tmp_path):
        """Explicit raw_article path is returned as-is (no --next logic)."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)

        (raw_dir / "[20200101]alpha.md").write_text("A", encoding="utf-8")

        result = resolve_article_path(tmp_path, use_next=False, raw_article="raw/articles/[20200101]alpha.md")
        assert result == "raw/articles/[20200101]alpha.md"

    def test_next_returns_none_when_empty(self, tmp_path):
        """--next returns None when no raw articles exist."""
        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)

        result = resolve_article_path(tmp_path, use_next=True)
        assert result is None
