"""Tests for ingest_finish.py script."""

import sys
from pathlib import Path
from datetime import date

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ingest_finish import format_log_entry, detect_changes


class TestFormatLogEntry:
    def test_basic_entry(self):
        """Minimal entry with title and source only."""
        result = format_log_entry(
            title="主动买卖因子的正确用法",
            source="raw/articles/[202009050948]主动买卖因子的正确用法.md",
            created=None,
            updated=None,
            notes=None,
        )
        assert "## Ingest: 主动买卖因子的正确用法" in result
        assert "- Source: `raw/articles/[202009050948]主动买卖因子的正确用法.md`" in result

    def test_entry_with_created(self):
        """Entry with created pages."""
        result = format_log_entry(
            title="主动买卖因子的正确用法",
            source="raw/articles/[202009050948]主动买卖因子的正确用法.md",
            created="wiki/sources/主动买卖因子的正确用法.md,wiki/concepts/主动买卖因子.md",
            updated=None,
            notes=None,
        )
        assert "- Created: `wiki/sources/主动买卖因子的正确用法.md`" in result
        assert "- Created: `wiki/concepts/主动买卖因子.md`" in result

    def test_entry_with_updated(self):
        """Entry with updated pages."""
        result = format_log_entry(
            title="昼夜分离隔夜跳空与日内反转选股因子",
            source="raw/articles/xxx.md",
            created=None,
            updated="wiki/entities/华安金工.md,wiki/index.md",
            notes=None,
        )
        assert "- Updated: `wiki/entities/华安金工.md`" in result
        assert "- Updated: `wiki/index.md`" in result

    def test_entry_with_notes(self):
        """Entry with notes appended."""
        result = format_log_entry(
            title="测试文章",
            source="raw/articles/test.md",
            created=None,
            updated=None,
            notes="开源金工市场微观结构研究系列第9篇",
        )
        assert "- 开源金工市场微观结构研究系列第9篇" in result

    def test_entry_ends_with_blank_line(self):
        """Each entry must end with a trailing newline for separation."""
        result = format_log_entry(
            title="测试",
            source="raw/test.md",
            created=None,
            updated=None,
            notes=None,
        )
        assert result.endswith("\n")

    def test_full_entry_matches_expected_format(self):
        """Full entry with all fields matches actual log format."""
        result = format_log_entry(
            title="主动买卖因子的正确用法",
            source="raw/articles/[202009050948]主动买卖因子的正确用法.md",
            created="wiki/sources/主动买卖因子的正确用法.md,wiki/concepts/主动买卖因子.md",
            updated="wiki/entities/开源金工.md,wiki/index.md",
            notes="ACT因子（主动买卖因子），因子切割论应用于主动买卖方向",
        )
        expected = (
            "## Ingest: 主动买卖因子的正确用法\n"
            "\n"
            "- Source: `raw/articles/[202009050948]主动买卖因子的正确用法.md`\n"
            "- Created: `wiki/sources/主动买卖因子的正确用法.md`\n"
            "- Created: `wiki/concepts/主动买卖因子.md`\n"
            "- Updated: `wiki/entities/开源金工.md`\n"
            "- Updated: `wiki/index.md`\n"
            "- ACT因子（主动买卖因子），因子切割论应用于主动买卖方向\n"
            "\n"
        )
        assert result == expected


class TestLogFileIO:
    """Test log file creation and appending behavior using format_log_entry output."""

    def test_new_log_file_format(self):
        """When log file doesn't exist, it should start with date heading."""
        today = date.today().isoformat()
        entry = format_log_entry("测试", "raw/test.md", None, None, None)
        content = f"# {today}\n\n{entry}"
        assert content.startswith(f"# {today}")
        assert "## Ingest: 测试" in content

    def test_append_to_existing_log(self):
        """When log file exists, new entry is appended after existing content."""
        today = date.today().isoformat()
        existing = f"# {today}\n\n## Ingest: 第一篇\n\n- Source: `raw/a.md`\n\n"
        entry = format_log_entry("第二篇", "raw/b.md", None, None, None)
        result = existing + entry
        assert "第一篇" in result
        assert "第二篇" in result
        assert result.index("第一篇") < result.index("第二篇")

    def test_entries_separated_by_blank_line(self):
        """Consecutive entries should be separated by a blank line."""
        entry1 = format_log_entry("第一篇", "raw/a.md", None, None, None)
        entry2 = format_log_entry("第二篇", "raw/b.md", None, None, None)
        combined = entry1 + entry2
        # entry1 ends with \n\n, entry2 starts with ## — so there's a blank line between
        assert "## Ingest: 第一篇" in combined
        assert "## Ingest: 第二篇" in combined


class TestDetectChanges:
    """Test auto-detection of created/updated files from git diff."""

    def test_detects_new_and_modified(self, tmp_path):
        """Parse git diff --name-status output correctly."""
        import subprocess
        # Init a git repo with a commit
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, check=True)
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "existing.md").write_text("old", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True, check=True)

        # Create changes: new file + modified file + ignored file
        (tmp_path / "wiki" / "new_page.md").write_text("new", encoding="utf-8")
        (tmp_path / "wiki" / "existing.md").write_text("changed", encoding="utf-8")
        (tmp_path / "other.txt").write_text("ignored", encoding="utf-8")

        created, updated = detect_changes(tmp_path)
        assert "wiki/new_page.md" in created
        assert "wiki/existing.md" in updated
        assert "other.txt" not in created
        assert "other.txt" not in updated

    def test_empty_when_no_changes(self, tmp_path):
        """Return empty strings when no git changes."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, check=True)
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "a.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True, check=True)

        created, updated = detect_changes(tmp_path)
        assert created == ""
        assert updated == ""

    def test_non_git_dir_returns_empty(self, tmp_path):
        """Gracefully handle non-git directory."""
        created, updated = detect_changes(tmp_path)
        assert created == ""
        assert updated == ""


class TestLogDeduplication:
    """Test that duplicate log entries for the same title are skipped."""

    def test_duplicate_title_skipped(self, tmp_path):
        """Same title on second run does not append a duplicate entry."""
        import subprocess

        SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_finish.py"
        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)

        # First call — should write entry
        proc1 = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Test Article", "--source", "raw/test.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc1.returncode == 0, proc1.stderr

        # Second call with same title — should skip log write
        proc2 = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Test Article", "--source", "raw/test.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc2.returncode == 0, proc2.stderr
        assert "SKIP" in proc2.stdout

        # Log file should contain the entry exactly once
        from datetime import date
        log_path = log_dir / f"{date.today().isoformat()}.md"
        content = log_path.read_text(encoding="utf-8")
        assert content.count("## Ingest: Test Article") == 1

    def test_different_title_appended(self, tmp_path):
        """Different title on second run appends normally."""
        import subprocess

        SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_finish.py"
        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)

        # First call
        proc1 = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Article Alpha", "--source", "raw/a.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc1.returncode == 0, proc1.stderr

        # Second call with different title — should append
        proc2 = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Article Beta", "--source", "raw/b.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc2.returncode == 0, proc2.stderr

        # Both entries should be present
        from datetime import date
        log_path = log_dir / f"{date.today().isoformat()}.md"
        content = log_path.read_text(encoding="utf-8")
        assert "## Ingest: Article Alpha" in content
        assert "## Ingest: Article Beta" in content
        assert content.count("## Ingest:") == 2


class TestExtractArchive:
    """Test that extract JSON is archived after successful ingest."""

    def test_archives_extract_json(self, tmp_path):
        """Extract JSON moves to meta/archive/ after ingest."""
        import subprocess

        SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_finish.py"

        # Set up meta dir with .last-extract pointing to an extract file
        meta_dir = tmp_path / "wiki" / "meta"
        meta_dir.mkdir(parents=True)
        extract_file = meta_dir / "extract-test-article.json"
        extract_file.write_text('{"title": "Test"}', encoding="utf-8")
        (meta_dir / ".last-extract").write_text("wiki/meta/extract-test-article.json", encoding="utf-8")

        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Test Article", "--source", "raw/test.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Archived" in proc.stdout

        # Original file should be gone
        assert not extract_file.exists()
        # Archive should contain the file
        archive_dir = meta_dir / "archive"
        assert archive_dir.exists()
        assert (archive_dir / "extract-test-article.json").exists()

    def test_no_archive_when_no_last_extract(self, tmp_path):
        """No error when .last-extract doesn't exist."""
        import subprocess

        SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_finish.py"

        meta_dir = tmp_path / "wiki" / "meta"
        meta_dir.mkdir(parents=True)
        log_dir = tmp_path / "log"
        log_dir.mkdir(parents=True)

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path),
             "--title", "Test", "--source", "raw/test.md", "--no-commit"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Archived" not in proc.stdout