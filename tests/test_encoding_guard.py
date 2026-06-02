"""Tests for cross-platform compatibility — encoding guards and path handling."""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


class TestEncodingGuards:
    """All scripts with print() output must have console encoding guards."""

    GUARD_PATTERN = 'sys.stdout.reconfigure(encoding="utf-8"'

    def _has_print(self, path: Path) -> bool:
        """Check if a script uses print() anywhere."""
        text = path.read_text(encoding="utf-8")
        return "print(" in text

    def _has_guard(self, path: Path) -> bool:
        """Check if a script has the encoding guard."""
        text = path.read_text(encoding="utf-8")
        return self.GUARD_PATTERN in text

    def test_all_scripts_with_print_have_encoding_guard(self):
        """Every script that calls print() must have the reconfigure guard."""
        missing = []
        for script in sorted(SCRIPTS_DIR.glob("*.py")):
            if self._has_print(script) and not self._has_guard(script):
                missing.append(script.name)
        assert missing == [], (
            f"Scripts missing encoding guard: {missing}\n"
            "Add after 'import sys':\n"
            '  if sys.stdout and hasattr(sys.stdout, "reconfigure"):\n'
            '      sys.stdout.reconfigure(encoding="utf-8", errors="replace")\n'
            '  if sys.stderr and hasattr(sys.stderr, "reconfigure"):\n'
            '      sys.stderr.reconfigure(encoding="utf-8", errors="replace")'
        )

    def test_library_scripts_may_skip_guard(self):
        """Pure library modules (no print) don't need the guard."""
        slug_utils = SCRIPTS_DIR / "slug_utils.py"
        assert slug_utils.exists()
        assert not self._has_print(slug_utils), "slug_utils should remain a pure library"


class TestPathHandling:
    """Verify cross-platform path handling patterns."""

    def test_scripts_use_pathlib_not_os_path(self):
        """Scripts should use pathlib.Path, not os.path for path operations."""
        for script in SCRIPTS_DIR.glob("*.py"):
            text = script.read_text(encoding="utf-8")
            # os.path.join is a red flag — should use Path / operator
            assert "os.path.join" not in text, f"{script.name} uses os.path.join instead of pathlib"

    def test_read_write_use_utf8(self):
        """All read_text/write_text calls must specify encoding='utf-8'."""
        import re
        for script in SCRIPTS_DIR.glob("*.py"):
            text = script.read_text(encoding="utf-8")
            # Find lines containing .read_text( or .write_text(
            for i, line in enumerate(text.split("\n"), 1):
                if ".read_text(" not in line and ".write_text(" not in line:
                    continue
                # Skip comment lines
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                # The encoding= may be on the same line or a continuation.
                # For single-line calls, check directly.
                if "encoding=" not in line:
                    # Check next lines for encoding= (multi-line call, e.g. 10 lines)
                    lines = text.split("\n")
                    found = False
                    for j in range(i - 1, min(i + 12, len(lines))):
                        if "encoding=" in lines[j]:
                            found = True
                            break
                        # Stop at closing paren — call ended without encoding
                        if ")" in lines[j] and j > i - 1:
                            break
                    if not found:
                        assert False, (
                            f"{script.name}:{i}: {line.strip()[:80]} "
                            "missing encoding='utf-8'"
                        )
