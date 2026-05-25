"""Tests for create_page.py --content and --summary flags."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "create_page.py"

TEMPLATE_CONCEPT = '---\ntitle: ""\ntype: concept\nsummary: ""\ntags: []\n---\n# {title}\n\nTemplate body.\n'


def _make_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "_templates").mkdir(parents=True)
    (wiki / "wiki" / "concepts").mkdir(parents=True)
    (wiki / "_templates" / "concept.md").write_text(TEMPLATE_CONCEPT, encoding="utf-8")
    return wiki


class TestCreatePageWithContent:
    def test_create_page_with_content(self, tmp_path):
        wiki = _make_wiki(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(wiki), "concept", "Test",
             "--content", "## Hello\n\nWorld"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "test.md"
        content = out.read_text(encoding="utf-8")
        # Body should be replaced
        assert "## Hello\n\nWorld" in content
        assert "Template body." not in content
        # Frontmatter should be correct
        assert 'title: "Test"' in content
        assert "type: concept" in content

    def test_create_page_with_summary(self, tmp_path):
        wiki = _make_wiki(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(wiki), "concept", "Test",
             "--summary", "A test concept"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "test.md"
        content = out.read_text(encoding="utf-8")
        assert 'summary: "A test concept"' in content
        # Template body should still be present
        assert "Template body." in content

    def test_create_page_without_content(self, tmp_path):
        wiki = _make_wiki(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(wiki), "concept", "Test"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "test.md"
        content = out.read_text(encoding="utf-8")
        # Template body should be preserved
        assert "Template body." in content
        assert 'summary: ""' in content

    def test_create_page_content_preserves_frontmatter(self, tmp_path):
        wiki = _make_wiki(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(wiki), "concept", "Test",
             "--tags", "AI,ML",
             "--summary", "My summary",
             "--content", "## Custom body"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = wiki / "wiki" / "concepts" / "test.md"
        content = out.read_text(encoding="utf-8")
        # All frontmatter fields from args should be preserved
        assert 'title: "Test"' in content
        assert "type: concept" in content
        assert "tags: [AI, ML]" in content
        assert 'summary: "My summary"' in content
        # Body should be replaced
        assert "## Custom body" in content
        assert "Template body." not in content
