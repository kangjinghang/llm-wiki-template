"""Tests for slug_utils.py — shared slugify and derive_slug."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from slug_utils import slugify, derive_slug


class TestSlugify:
    def test_ascii_spaces_to_dashes(self):
        """Spaces become hyphens."""
        assert slugify("Alpha Strategy 101") == "alpha-strategy-101"

    def test_chinese_preserved(self):
        """Chinese characters are kept as-is, English lowercased."""
        assert slugify("基于LSTM的因子选股") == "基于lstm的因子选股"

    def test_special_chars_to_dashes(self):
        """Punctuation becomes hyphens."""
        assert slugify("Hello World!") == "hello-world"

    def test_collapse_multiple_dashes(self):
        """Multiple consecutive hyphens collapse into one."""
        assert slugify("foo---bar") == "foo-bar"

    def test_strip_leading_trailing(self):
        """Leading/trailing hyphens are stripped."""
        assert slugify("--hello--") == "hello"

    def test_empty_returns_untitled(self):
        """Empty string returns 'untitled'."""
        assert slugify("") == "untitled"


class TestDeriveSlug:
    def test_strips_timestamp(self):
        """Strip [YYYYMMDDHHMM] timestamp prefix and .md extension."""
        result = derive_slug("raw/articles/[202011040800]中国Barra模型.md")
        assert result == "中国barra模型"

    def test_no_timestamp(self):
        """No timestamp prefix — just strip extension."""
        result = derive_slug("raw/articles/test.md")
        assert result == "test"

    def test_spaces_normalized_to_dashes(self):
        """Spaces in filename become hyphens (consistency with slugify)."""
        result = derive_slug("raw/articles/[20200101]Alpha Strategy.md")
        assert result == "alpha-strategy"
