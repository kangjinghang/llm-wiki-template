"""Tests for create_syntheses.py — synthesis page creation from candidates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from create_syntheses import (
    build_frontmatter,
    extract_summary,
    read_source_pages,
    write_synthesis_page,
)


class TestBuildFrontmatter:
    """Test YAML frontmatter generation."""

    def test_basic_frontmatter(self):
        fm = build_frontmatter("行业轮动", ["src-a", "src-b"], ["量化", "a股"])
        assert 'title: "行业轮动"' in fm
        assert "type: synthesis" in fm
        assert "[[src-a]]" in fm
        assert "[[src-b]]" in fm
        assert "量化" in fm
        assert "origin: agent-compiled" in fm
        assert "status: seed" in fm

    def test_truncates_tags_to_10(self):
        tags = [f"tag{i}" for i in range(15)]
        fm = build_frontmatter("Test", [], tags)
        # Should only include first 10 tags
        assert "tag9" in fm
        assert "tag10" not in fm

    def test_sources_in_wikilink_format(self):
        fm = build_frontmatter("X", ["alpha-策略", "beta模型"], [])
        assert '- "[[alpha-策略]]"' in fm
        assert '- "[[beta模型]]"' in fm

    def test_today_date(self):
        from datetime import date
        today = date.today().isoformat()
        fm = build_frontmatter("X", [], [])
        assert f"created: {today}" in fm
        assert f"updated: {today}" in fm


class TestExtractSummary:
    """Test summary extraction from Overview section."""

    def test_extracts_first_paragraph(self):
        body = (
            "## Overview / 概述\n\n"
            "这是第一段概述内容，用于生成summary。\n\n"
            "## Key Findings / 核心发现\n\n"
            "发现内容。\n"
        )
        summary = extract_summary(body)
        assert "概述内容" in summary
        assert len(summary) <= 120

    def test_truncates_long_summary(self):
        long_text = "A" * 200
        body = f"## Overview / 概述\n\n{long_text}\n\n## Next\n"
        summary = extract_summary(body)
        assert len(summary) <= 120
        assert summary.endswith("...")

    def test_returns_empty_if_no_overview(self):
        body = "## Key Findings\n\nSome findings.\n"
        assert extract_summary(body) == ""


class TestReadSourcePages:
    """Test source page content reading."""

    def test_reads_existing_source(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        sources = wiki_dir / "sources"
        sources.mkdir(parents=True)

        (sources / "my-source.md").write_text(
            "---\ntitle: Test\n---\nBody content here.\n",
            encoding="utf-8",
        )

        result = read_source_pages(wiki_dir, ["my-source"])
        assert "Body content here." in result
        assert "### Source: my-source" in result

    def test_handles_missing_source(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        sources = wiki_dir / "sources"
        sources.mkdir(parents=True)

        result = read_source_pages(wiki_dir, ["nonexistent"])
        assert "页面不存在" in result

    def test_truncates_long_source(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        sources = wiki_dir / "sources"
        sources.mkdir(parents=True)

        long_body = "X" * 5000
        (sources / "long.md").write_text(
            f"---\ntitle: Long\n---\n{long_body}\n",
            encoding="utf-8",
        )

        result = read_source_pages(wiki_dir, ["long"])
        assert "已截断" in result
        assert len(result) < 3000


class TestWriteSynthesisPage:
    """Test synthesis page file writing."""

    def test_writes_complete_page(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        body = (
            "## Overview / 概述\n\n这是概述。\n\n"
            "## Key Findings / 核心发现\n\n- 发现1\n"
        )
        path = write_synthesis_page(
            wiki_dir, "test-slug", "测试标题", ["src-a"], ["量化"], body,
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "type: synthesis" in content
        assert "测试标题" in content
        assert "发现1" in content
        assert "[[src-a]]" in content
        assert "<!-- human:start -->" in content

    def test_prepends_title_heading(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        body = "## Overview\n\nSome text.\n"
        path = write_synthesis_page(
            wiki_dir, "slug", "My Title", [], [], body,
        )
        content = path.read_text(encoding="utf-8")
        assert content.count("# My Title") == 1

    def test_deduplicates_notes_heading(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        body = (
            "## Overview\n\nText.\n"
            "## Notes / 笔记\n\n## Notes / 笔记\n"
            "<!-- human:start -->\n<!-- human:end -->\n"
        )
        path = write_synthesis_page(
            wiki_dir, "slug", "Test", [], [], body,
        )
        content = path.read_text(encoding="utf-8")
        # Should not have duplicate Notes headings
        assert content.count("## Notes / 笔记") == 1

    def test_dry_run_does_not_write(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        body = "## Overview\n\nText.\n"
        path = write_synthesis_page(
            wiki_dir, "slug", "Test", [], [], body, dry_run=True,
        )
        assert not path.exists()

    def test_extracts_summary_into_frontmatter(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        body = (
            "## Overview / 概述\n\n"
            "这是一段用于summary的文字。\n\n"
            "## Key Findings\n\nFindings.\n"
        )
        path = write_synthesis_page(
            wiki_dir, "slug", "Test", [], [], body,
        )
        content = path.read_text(encoding="utf-8")
        assert "用于summary的文字" in content
        # Summary should appear in frontmatter
        lines = content.split("\n")
        summary_line = [l for l in lines if l.startswith("summary:")]
        assert len(summary_line) == 1
        assert "用于summary的文字" in summary_line[0]
