"""Tests for update_index.py script."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from update_index import add_entries, _extract_wikilink, _find_section_range


class TestExtractWikilink:
    def test_basic(self):
        assert _extract_wikilink("[[foo]] — desc") == "foo"

    def test_no_wikilink(self):
        assert _extract_wikilink("plain text") is None


class TestFindSectionRange:
    def test_finds_section(self):
        content = "# Title\n\n## Sources\n\n- [[a]]\n\n## Concepts\n\n- [[b]]\n"
        rng = _find_section_range(content, "## Sources")
        assert rng is not None
        start, end = rng
        assert "## Sources" in content[start:end]
        assert "## Concepts" not in content[start:end]

    def test_missing_section(self):
        content = "# Title\n\n## Concepts\n\n- [[b]]\n"
        assert _find_section_range(content, "## Sources") is None


class TestAddSourceEntry:
    def test_add_source_entry(self, tmp_path):
        content = "# Title\n\n## Sources\n\n- [[existing]] — desc\n\n## Concepts\n\n"
        result = add_entries(content, "source", ["[[new-source]] — new desc"])
        assert "[[new-source]]" in result
        # Should be before ## Concepts
        assert result.index("[[new-source]]") < result.index("## Concepts")

    def test_dedup_source(self, tmp_path):
        content = "# Title\n\n## Sources\n\n- [[existing]] — desc\n\n## Concepts\n\n"
        result = add_entries(content, "source", ["[[existing]] — updated desc"])
        assert result == content  # no change


class TestAddConceptEntry:
    def test_add_concept_entry(self):
        content = "# Title\n\n## Sources\n\n- [[a]]\n\n## Concepts\n\n- [[old]] — old\n\n## Entities\n\n"
        result = add_entries(content, "concept", ["[[new-concept]] — new"])
        assert "[[new-concept]]" in result
        assert result.index("[[new-concept]]") < result.index("## Entities")

    def test_add_to_concepts_with_subsections(self):
        content = "# Title\n\n## Concepts\n\n### Sub A\n\n- [[a]]\n\n### Sub B\n\n- [[b]]\n\n## Entities\n\n"
        result = add_entries(content, "concept", ["[[c]] — new"])
        assert "[[c]]" in result
        assert result.index("[[c]]") < result.index("## Entities")


class TestAddEntityEntry:
    def test_add_entity_entry(self):
        content = "# Title\n\n## Entities\n\n- [[existing-entity]] — desc\n\n## Open Questions\n\n"
        result = add_entries(content, "entity", ["[[new-entity]] — new"])
        assert "[[new-entity]]" in result
        assert result.index("[[new-entity]]") < result.index("## Open Questions")


class TestCreateMissingSection:
    def test_creates_syntheses_section(self):
        content = "# Title\n\n## Entities\n\n- [[a]]\n\n## Open Questions\n\n"
        result = add_entries(content, "synthesis", ["[[synth-1]] — first synthesis"])
        assert "## Syntheses" in result
        assert "[[synth-1]]" in result
        assert result.index("## Syntheses") < result.index("## Open Questions")


class TestMultipleFlags:
    def test_add_multiple_sections(self):
        content = "# Title\n\n## Sources\n\n- [[a]]\n\n## Concepts\n\n- [[b]]\n\n## Entities\n\n- [[c]]\n\n"
        result = content
        result = add_entries(result, "source", ["[[new-src]] — src desc"])
        result = add_entries(result, "concept", ["[[new-cpt]] — cpt desc"])
        result = add_entries(result, "entity", ["[[new-ent]] — ent desc"])
        assert "[[new-src]]" in result
        assert "[[new-cpt]]" in result
        assert "[[new-ent]]" in result
        # Order preserved: sources before concepts before entities
        assert result.index("[[new-src]]") < result.index("[[new-cpt]]")
        assert result.index("[[new-cpt]]") < result.index("[[new-ent]]")
