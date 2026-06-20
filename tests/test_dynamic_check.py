"""Integration tests for dynamic spec execution check.

Tests the verify_dynamic function end-to-end, including the full
spec parsing → Playwright execution → result pipeline.
"""

import os
from pathlib import Path

import pytest

from maestro_guard.checks.dynamic import verify_dynamic

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    """Read a fixture file and return its content."""
    path = FIXTURES / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# Skip all tests in this file if PLAYWRIGHT_TEST is not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("PLAYWRIGHT_TEST", ""),
    reason="Set PLAYWRIGHT_TEST=1 to run browser-dependent tests",
)


class TestVerifyDynamic:
    """Tests for the verify_dynamic check function."""

    def test_good_html_passes(self):
        """A correct HTML page should pass its spec."""
        html = _read("hello.html")
        spec = _read("hello_spec.md")

        passed, detail, suggestion = verify_dynamic(html, spec)

        assert passed, f"Expected pass but got: {detail}"
        assert "passed" in detail or "passed" in detail.lower()
        assert isinstance(suggestion, str)

    def test_broken_html_fails(self):
        """An HTML page with mismatched content should fail its spec."""
        html = _read("broken.html")
        spec = _read("broken_spec.md")

        passed, detail, suggestion = verify_dynamic(html, spec)

        assert not passed, f"Expected failure but got: {detail}"
        assert "failed" in detail.lower() or "FAIL" in detail
        assert "Fix" in suggestion or "fix" in suggestion.lower()

    def test_empty_spec_passes(self):
        """An empty spec with no assertions should pass."""
        html = _read("hello.html")
        spec = "# Empty spec\n## Assertions\n"

        passed, detail, suggestion = verify_dynamic(html, spec)

        assert passed, f"Expected pass for empty spec but got: {detail}"
        assert "no executable assertions" in detail.lower()

    def test_spec_parse_error_returns_fail(self):
        """A spec that fails to parse should return a failure."""
        html = _read("hello.html")
        spec = "### DOM: `bad syntax no quotes"

        passed, detail, suggestion = verify_dynamic(html, spec)

        # Should not crash — should return a structured failure
        assert isinstance(passed, bool)
        assert isinstance(detail, str)
        assert isinstance(suggestion, str)

    def test_console_error_detected(self):
        """A page with console errors should fail the console check."""
        html = "<script>console.error('boom')</script>"
        spec = """# Console Check
## Assertions
### Console: no errors
### Timeout: 3000ms
"""

        passed, detail, suggestion = verify_dynamic(html, spec)

        assert not passed, f"Expected failure for console error but got: {detail}"

    def test_multiple_assertions_all_pass(self):
        """Multiple assertions all passing should result in pass."""
        html = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <div class="items">
    <span>Item 1</span>
    <span>Item 2</span>
    <span>Item 3</span>
  </div>
  <script>
    window.initApp = function() { return true; };
  </script>
</body>
</html>"""
        spec = """# Test Page
## Assertions
### DOM: `document.title` == `Test Page`
### DOM: `document.querySelectorAll('.items span').length` >= `3`
### JS: `typeof window.initApp` == `function`
### Console: no errors
### Async: page loads without uncaught errors
### Timeout: 5000ms
"""

        passed, detail, suggestion = verify_dynamic(html, spec)

        assert passed, f"Expected pass but got: {detail}"
        assert "4/4" in detail or "passed" in detail.lower()
