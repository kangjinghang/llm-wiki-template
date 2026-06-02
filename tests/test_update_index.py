"""Tests for update_index.py — index entry dedup and summary generation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from update_index import (
    _extract_wikilink,
    _find_section_range,
    _entries_in_section,
    add_entries,
    _generate_summary,
)


class TestExtractWikilink:
    def test_basic_wikilink(self):
        """Extract target from a simple entry."""
        assert _extract_wikilink("[[alpha]] — some description") == "alpha"

    def test_entry_without_wikilink(self):
        """Return None when no wikilink present."""
        assert _extract_wikilink("plain text only") is None

    def test_wikilink_at_end(self):
        """Extract wikilink from end of entry."""
        assert _extract_wikilink("see [[beta]]") == "beta"


class TestFindSectionRange:
    def test_finds_existing_section(self):
        """Return (start, end) for a known section."""
        content = "# Index\n\n## Sources\n\n- [[a]]\n\n## Concepts\n\n- [[b]]\n"
        rng = _find_section_range(content, "## Sources")
        assert rng is not None
        start, end = rng
        assert start < end
        assert "## Sources" in content[start:end]
        assert "## Concepts" not in content[start:end]

    def test_returns_none_for_missing(self):
        """Return None when section heading not found."""
        content = "# Index\n\n## Concepts\n\n- [[a]]\n"
        assert _find_section_range(content, "## Sources") is None


class TestEntriesInSection:
    def test_extracts_targets(self):
        """Collect all [[...]] targets from a section."""
        content = "# Index\n\n## Concepts\n\n- [[alpha]] — desc\n- [[beta]] — desc2\n\n## Entities\n\n- [[gamma]]\n"
        result = _entries_in_section(content, "## Concepts")
        assert result == {"alpha", "beta"}

    def test_empty_section(self):
        """Return empty set when section exists but has no links."""
        content = "# Index\n\n## Concepts\n\nNo entries yet.\n\n## Entities\n\n- [[x]]\n"
        result = _entries_in_section(content, "## Concepts")
        assert result == set()


class TestAddEntries:
    def test_adds_new_entry(self):
        """Add a new entry to existing section."""
        content = "# Index\n\n## Sources\n\n- [[existing]] — old\n\n## Concepts\n\n- [[a]]\n"
        result = add_entries(content, "source", ["[[new-source]] — a new source"])
        assert "[[new-source]]" in result
        assert "[[existing]]" in result  # old entry preserved

    def test_deduplicates_by_wikilink(self):
        """Skip entry whose wikilink target already exists in section."""
        content = "# Index\n\n## Concepts\n\n- [[alpha]] — original desc\n\n## Entities\n\n- [[x]]\n"
        result = add_entries(content, "concept", ["[[alpha]] — updated desc"])
        # Should NOT add duplicate — original entry preserved unchanged
        assert result.count("[[alpha]]") == 1

    def test_creates_missing_section(self):
        """Create section if it doesn't exist."""
        content = "# Index\n\n## Concepts\n\n- [[a]]\n"
        result = add_entries(content, "source", ["[[my-source]] — desc"])
        assert "## Sources" in result
        assert "[[my-source]]" in result

    def test_no_changes_when_all_duplicate(self):
        """Return unchanged content when all entries are duplicates."""
        content = "# Index\n\n## Concepts\n\n- [[alpha]] — desc\n\n## Entities\n\n- [[x]]\n"
        result = add_entries(content, "concept", ["[[alpha]] — another desc"])
        assert result == content


class TestGenerateSummary:
    def test_generates_compact_summary(self):
        """Summary has only wikilinks, no descriptions."""
        index = "# Index\n\n## Sources\n\n- [[src1]] — A source\n- [[src2]] — Another\n\n## Concepts\n\n- [[con1]] — Idea\n"
        summary = _generate_summary(index)
        assert "# Index Summary" in summary
        assert "- [[src1]]" in summary
        assert "- [[src2]]" in summary
        assert "- [[con1]]" in summary
        # No descriptions in summary
        assert "A source" not in summary
        assert "Idea" not in summary

    def test_empty_sections_omitted(self):
        """Sections with no entries are not included in summary."""
        index = "# Index\n\n## Sources\n\n- [[src1]] — desc\n\n## Syntheses\n\n"
        summary = _generate_summary(index)
        assert "## Sources" in summary
        assert "## Syntheses" not in summary
