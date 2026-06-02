"""Tests for lint_wiki.py — new lint checks (Pass 17–20)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lint_wiki import lint


class TestDuplicateIndexEntries:
    """Pass 17: exact-duplicate [[target]] in index.md."""

    def test_detects_duplicate_entries(self, tmp_path, capsys):
        """Same [[target]] appearing twice in Sources section should be flagged."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        sources = wiki / "sources"
        sources.mkdir()
        (sources / "alpha.md").write_text("---\ntitle: Alpha\n---\nBody.", encoding="utf-8")
        (sources / "beta.md").write_text("---\ntitle: Beta\n---\nBody.", encoding="utf-8")

        index = (
            "# Index\n\n## Sources\n\n"
            "- [[alpha]] — desc 1\n"
            "- [[beta]] — desc 2\n"
            "- [[alpha]] — desc 3\n"  # duplicate
            "\n## Concepts\n\n"
        )
        (wiki / "index.md").write_text(index, encoding="utf-8")

        ret = lint(str(tmp_path))
        out = capsys.readouterr().out
        assert ret == 1  # issues found
        assert "Duplicate index entries" in out
        assert "[[alpha]]" in out

    def test_no_duplicates_passes(self, tmp_path, capsys):
        """Unique entries should not trigger this check."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        sources = wiki / "sources"
        sources.mkdir()
        (sources / "alpha.md").write_text("---\ntitle: Alpha\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Sources\n\n- [[alpha]] — desc\n\n## Concepts\n\n",
            encoding="utf-8",
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        assert "No duplicate index entries" in out

    def test_same_target_in_different_sections_is_ok(self, tmp_path, capsys):
        """[[alpha]] in Sources AND Concepts is allowed (different sections)."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        (concepts / "alpha.md").write_text("---\ntitle: Alpha\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Sources\n\n- [[alpha]] — source desc\n\n"
            "## Concepts\n\n- [[alpha]] — concept desc\n",
            encoding="utf-8",
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        # Same target in different sections is not a duplicate
        assert "No duplicate index entries" in out


class TestCaseInsensitiveDuplicateEntries:
    """Pass 18: [[PEAD效应]] and [[pead效应]] coexisting in index.md."""

    def test_detects_case_insensitive_dupes(self, tmp_path, capsys):
        """[[PEAD效应]] and [[pead效应]] in same section should be flagged."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        (concepts / "pead效应.md").write_text("---\ntitle: PEAD\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n"
            "- [[PEAD效应]] — desc 1\n"
            "- [[pead效应]] — desc 2\n",
            encoding="utf-8",
        )
        ret = lint(str(tmp_path))
        out = capsys.readouterr().out
        assert ret == 1
        assert "Case-insensitive duplicate" in out

    def test_no_case_dupes_passes(self, tmp_path, capsys):
        """Unique casing should pass."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        (concepts / "alpha.md").write_text("---\ntitle: Alpha\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[alpha]] — desc\n",
            encoding="utf-8",
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        assert "No case-insensitive duplicate" in out


class TestCrossDirectorySlugCollisions:
    """Pass 19: same filename in different wiki subdirectories."""

    def test_detects_collision(self, tmp_path, capsys):
        """Same slug in concepts/ and sources/ should be flagged."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        sources = wiki / "sources"
        concepts.mkdir()
        sources.mkdir()
        (concepts / "因子模型.md").write_text("---\ntitle: 因子模型\n---\nBody.", encoding="utf-8")
        (sources / "因子模型.md").write_text("---\ntitle: 因子模型\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[因子模型]] — c\n\n## Sources\n\n- [[因子模型]] — s\n",
            encoding="utf-8",
        )
        ret = lint(str(tmp_path))
        out = capsys.readouterr().out
        assert ret == 1
        assert "Cross-directory slug collision" in out
        assert "因子模型" in out

    def test_no_collision_passes(self, tmp_path, capsys):
        """Different slugs in different dirs should pass."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        sources = wiki / "sources"
        concepts.mkdir()
        sources.mkdir()
        (concepts / "alpha.md").write_text("---\ntitle: Alpha\n---\nBody.", encoding="utf-8")
        (sources / "source-a.md").write_text("---\ntitle: SA\n---\nBody.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[alpha]] — c\n\n## Sources\n\n- [[source-a]] — s\n",
            encoding="utf-8",
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        assert "No cross-directory slug collisions" in out


class TestThinPages:
    """Pass 20: pages with fewer than 15 words of body content."""

    def test_detects_thin_page(self, tmp_path, capsys):
        """Page with < 15 words of body should be flagged."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        (concepts / "stub.md").write_text(
            "---\ntitle: Stub\nsummary: thin\n---\nShort.", encoding="utf-8"
        )

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[stub]] — desc\n", encoding="utf-8"
        )
        ret = lint(str(tmp_path))
        out = capsys.readouterr().out
        assert ret == 1
        assert "Thin page" in out or "thin" in out.lower()
        assert "stub" in out

    def test_substantial_page_passes(self, tmp_path, capsys):
        """Page with >= 15 words of body should pass."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        body = " ".join(["word"] * 20)
        (concepts / "full.md").write_text(
            f"---\ntitle: Full\nsummary: ok\n---\n{body}", encoding="utf-8"
        )

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[full]] — desc\n", encoding="utf-8"
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        assert "No thin pages" in out

    def test_page_without_frontmatter_skipped(self, tmp_path, capsys):
        """Pages with no frontmatter should not trigger false positives."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        concepts = wiki / "concepts"
        concepts.mkdir()
        (concepts / "nofm.md").write_text("Just some text without frontmatter.", encoding="utf-8")

        (wiki / "index.md").write_text(
            "# Index\n\n## Concepts\n\n- [[nofm]] — desc\n", encoding="utf-8"
        )
        lint(str(tmp_path))
        out = capsys.readouterr().out
        # Should not crash or flag
        assert "No thin pages" in out
