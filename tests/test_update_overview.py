"""Tests for update_overview.py — section insertion and wikilink validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from update_overview import insert_section, check_dead_wikilinks


class TestInsertSection:
    def test_inserts_before_marker(self):
        """Insert section before ## 开放问题 marker."""
        overview = "# Overview\n\n## 开放问题\n\n- Q1?\n"
        section = "### New Topic\n\nSome content here.\n"
        result, changed = insert_section(overview, section)
        assert changed is True
        assert "### New Topic" in result
        # Section should appear before 开放问题
        assert result.index("### New Topic") < result.index("## 开放问题")

    def test_dedup_by_heading(self):
        """Skip if heading already exists."""
        overview = "# Overview\n\n### Existing\n\nOld.\n\n## 开放问题\n"
        section = "### Existing\n\nNew content.\n"
        result, changed = insert_section(overview, section)
        assert changed is False
        assert result == overview

    def test_appends_when_no_marker(self):
        """Append at end when no marker found."""
        overview = "# Overview\n\nSome intro.\n"
        section = "### New Topic\n\nContent.\n"
        result, changed = insert_section(overview, section)
        assert changed is True
        assert "### New Topic" in result


class TestCheckDeadWikilinks:
    def test_warns_on_dead_links(self, tmp_path):
        """Print warnings for wikilinks with no matching page."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        concepts = wiki_dir / "concepts"
        concepts.mkdir()
        (concepts / "existing-concept.md").write_text("---\n---\nbody\n", encoding="utf-8")

        content = "See [[existing-concept]] and [[dead-link]] here."
        dead = check_dead_wikilinks(content, wiki_dir)

        assert "dead-link" in dead
        assert "existing-concept" not in dead

    def test_returns_empty_when_all_valid(self, tmp_path):
        """No warnings when all wikilinks point to existing pages."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        concepts = wiki_dir / "concepts"
        concepts.mkdir()
        (concepts / "alpha.md").write_text("---\n---\nbody\n", encoding="utf-8")

        content = "See [[alpha]] only."
        dead = check_dead_wikilinks(content, wiki_dir)
        assert dead == []

    def test_no_links_returns_empty(self, tmp_path):
        """No wikilinks means no dead links."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()

        content = "Plain text, no links."
        dead = check_dead_wikilinks(content, wiki_dir)
        assert dead == []

    def test_slugified_match(self, tmp_path):
        """Dead link detection uses slugify for matching."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        concepts = wiki_dir / "concepts"
        concepts.mkdir()
        (concepts / "修正超预期股票池2-0.md").write_text("---\n---\nbody\n", encoding="utf-8")

        # The link uses the slugified form (hyphen, not dot)
        content = "See [[修正超预期股票池2-0]]."
        dead = check_dead_wikilinks(content, wiki_dir)
        assert dead == []

    def test_detects_unslugified_link_as_dead(self, tmp_path):
        """A link with dots instead of hyphens is detected as dead."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        concepts = wiki_dir / "concepts"
        concepts.mkdir()
        (concepts / "修正超预期股票池2-0.md").write_text("---\n---\nbody\n", encoding="utf-8")

        # The link uses dot (wrong) while page uses hyphen (correct)
        content = "See [[修正超预期股票池2.0]]."
        dead = check_dead_wikilinks(content, wiki_dir)
        assert "修正超预期股票池2.0" in dead
