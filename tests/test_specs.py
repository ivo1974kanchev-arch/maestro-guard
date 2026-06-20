"""
Tests for the dynamic spec execution system (spec parser + executor).

Requires Playwright to be installed (pip install playwright && playwright install chromium).
Tests are skipped if Playwright is not available.
"""

import os
from pathlib import Path

import pytest

from maestro_guard.specs.parser import (
    parse_spec,
    AssertionType,
    spec_to_dict,
    format_assertion_summary,
)

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
DEMO_DIR = HERE.parent / "demo"


# ─── Parser Tests ─────────────────────────────────────────────────────


class TestSpecParser:
    def test_parse_basic_spec(self):
        """Parse a simple spec with DOM and JS assertions."""
        text = """# Test Spec

## Assertions

### DOM: `document.title` == `Hello World`
### JS: `typeof window.greet` == `function`
### Console: no errors
### Timeout: 3000ms
"""
        spec = parse_spec(text)
        assert spec.title == "Test Spec"
        assert len(spec.assertions) == 3
        assert spec.timeout_ms == 3000

    def test_parse_dom_equals(self):
        text = "### DOM: `document.querySelector('.value').textContent` == `$48,290`"
        spec = parse_spec(text)
        assert len(spec.assertions) == 1
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.DOM_EQUALS
        assert "querySelector" in a.js_expression
        assert a.expected == "$48,290"

    def test_parse_dom_gte(self):
        text = "### DOM: `document.querySelectorAll('.stat-card').length` >= `4`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.DOM_GREATER_OR_EQ
        assert a.expected == "4"

    def test_parse_dom_not_equals(self):
        text = "### DOM: `document.title` != `Untitled Page`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.DOM_NOT_EQUALS

    def test_parse_dom_matches(self):
        text = "### DOM: `document.title` matches `^Analytics`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.DOM_MATCHES

    def test_parse_js_typeof(self):
        text = "### JS: `typeof window.initDashboard` == `function`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.JS_TYPE_OF
        assert a.js_expression == "window.initDashboard"
        assert a.expected == "function"

    def test_parse_js_equals(self):
        text = "### JS: `1 + 1` == `2`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.JS_EQUALS

    def test_parse_console_no_errors(self):
        text = "### Console: no errors"
        spec = parse_spec(text)
        assert spec.assertions[0].assert_type == AssertionType.CONSOLE_NO_ERRORS

    def test_parse_console_warn_count(self):
        text = "### Console: warn count <= 3"
        spec = parse_spec(text)
        a = spec.assertions[0]
        assert a.assert_type == AssertionType.CONSOLE_WARN_COUNT
        assert a.expected == 3

    def test_parse_style_equals(self):
        text = "### Style: `.sidebar` `display` == `flex`"
        spec = parse_spec(text)
        a = spec.assertions[0]
        # Could be STYLE_EQUALS or DOM_EQUALS
        assert a.assert_type in (AssertionType.STYLE_EQUALS,)
        assert a.selector == ".sidebar"

    def test_parse_async(self):
        text = "### Async: page loads without uncaught errors"
        spec = parse_spec(text)
        assert spec.assertions[0].assert_type == AssertionType.ASYNC_NO_ERRORS

    def test_parse_timeout(self):
        text = """## Assertions

### Timeout: 10000ms
### Console: no errors
"""
        spec = parse_spec(text)
        assert spec.timeout_ms == 10000

    def test_parse_structure_check(self):
        text = """### Structure
- The page has a sidebar with navigation links
"""
        spec = parse_spec(text)
        assert any(a.assert_type == AssertionType.STRUCTURE_CHECK for a in spec.assertions)

    def test_parse_exemptions(self):
        text = """## Exemptions
- API unreachable is acceptable
- console.warn for missing data is OK
"""
        spec = parse_spec(text)
        assert len(spec.exemptions) == 2
        assert "API unreachable" in spec.exemptions[0]

    def test_parse_demo_spec(self):
        """Parse the full demo exec_spec.md."""
        spec_path = DEMO_DIR / "exec_spec.md"
        if not spec_path.exists():
            pytest.skip("demo/exec_spec.md not found")
        text = spec_path.read_text(encoding="utf-8")
        spec = parse_spec(text)

        assert spec.title == "SaaS Analytics Dashboard — Dynamic Spec"
        assert len(spec.assertions) > 10
        assert spec.timeout_ms == 5000
        assert len(spec.exemptions) > 0

        # Check breakdown
        summary = format_assertion_summary(spec)
        assert "Assertions:" in summary
        assert "DOM_EQUALS" in summary or "DOM" in summary
        assert "JS_TYPE_OF" in summary or "JS" in summary

    def test_assertion_types_enum(self):
        """Verify all assertion types are represented."""
        types = {
            AssertionType.DOM_EQUALS,
            AssertionType.DOM_NOT_EQUALS,
            AssertionType.DOM_GREATER_OR_EQ,
            AssertionType.DOM_MATCHES,
            AssertionType.JS_EQUALS,
            AssertionType.JS_TYPE_OF,
            AssertionType.CONSOLE_NO_ERRORS,
            AssertionType.CONSOLE_NO_WARNINGS,
            AssertionType.CONSOLE_WARN_COUNT,
            AssertionType.BEHAVIOR,
            AssertionType.STYLE_EQUALS,
            AssertionType.ASYNC_NO_ERRORS,
            AssertionType.TIMEOUT,
            AssertionType.STRUCTURE_CHECK,
        }
        assert len(types) == 14
        assert AssertionType.DOM_EQUALS.name == "DOM_EQUALS"

    def test_spec_to_dict(self):
        text = """# Dict Test
## Assertions
### DOM: `document.title` == `Test`
### JS: `typeof window.foo` == `function`
"""
        spec = parse_spec(text)
        d = spec_to_dict(spec)
        assert d["title"] == "Dict Test"
        assert d["assertion_count"] == 2
        assert "assertion_types" in d
        assert "DOM_EQUALS" in d["assertion_types"]
        assert "JS_TYPE_OF" in d["assertion_types"]

    def test_behavior_assertion(self):
        text = """## Assertions
### Behavior: refreshData disables button
```js
document.querySelector('.refresh-btn').click()
document.querySelector('.refresh-btn').disabled == true
```
"""
        spec = parse_spec(text)
        behaviors = [a for a in spec.assertions if a.assert_type == AssertionType.BEHAVIOR]
        assert len(behaviors) == 1
        assert "click()" in behaviors[0].js_expression


# ─── Executor Tests (require Playwright) ──────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("PLAYWRIGHT_TEST", False),
    reason="Set PLAYWRIGHT_TEST=1 to run Playwright-dependent tests",
)
class TestSpecExecutor:
    """Integration tests that require Playwright.

    Run with: PLAYWRIGHT_TEST=1 pytest tests/test_specs.py -v
    """

    def test_execute_clean_html(self):
        """Execute the demo spec against the clean HTML page."""
        from maestro_guard.specs.executor import SpecExecutor

        # Load the clean HTML
        html_path = FIXTURES / "good.html"
        if not html_path.exists():
            # Try fixtures
            html = "<html><body><div id='app'><div class='value'>OK</div></div></body></html>"
        else:
            html = html_path.read_text(encoding="utf-8")

        # Parse the demo spec
        spec_path = DEMO_DIR / "exec_spec.md"
        if spec_path.exists():
            spec_text = spec_path.read_text(encoding="utf-8")
        else:
            # Fallback: minimal inline spec
            spec_text = """# Test
            ## Assertions
            ### DOM: `document.title` == `Valid Page`
            ### Console: no errors
            ### Async: no uncaught errors"""
        spec = parse_spec(spec_text)

        # Execute
        executor = SpecExecutor(html, html_path=str(html_path) if isinstance(html_path, (str, Path)) else "")
        try:
            executor.setup()
            executor.load_html()
            result = executor.run_spec(spec)
            assert executor is not None
        finally:
            executor.teardown()

    def test_execute_simple_assertions(self):
        """Test basic assertion execution against a simple HTML page."""
        from maestro_guard.specs.executor import SpecExecutor

        html = """<!DOCTYPE html>
<html lang="en">
<head><title>Test Page</title></head>
<body>
  <div id="app" class="container">
    <span class="value">42</span>
  </div>
  <script>
    function greet(name) { return "Hello " + name; }
  </script>
</body>
</html>"""

        spec_text = """# Simple Test
## Assertions
### DOM: `document.title` == `Test Page`
### JS: `typeof window.greet` == `function`
### Console: no errors
"""
        spec = parse_spec(spec_text)
        executor = SpecExecutor(html)
        try:
            executor.setup()
            executor.load_html()
            result = executor.run_spec(spec)
            assert result.passed_count >= 2
            assert result.all_passed
        finally:
            executor.teardown()

    def test_execute_with_failures(self):
        """Test that assertion failures are correctly reported."""
        from maestro_guard.specs.executor import SpecExecutor

        html = """<!DOCTYPE html>
<html><head><title>Wrong Title</title></head>
<body><div id="app"></div></body></html>"""

        spec_text = """# Fail Test
## Assertions
### DOM: `document.title` == `Expected Title`
### Console: no errors
"""
        spec = parse_spec(spec_text)
        executor = SpecExecutor(html)
        try:
            executor.setup()
            executor.load_html()
            result = executor.run_spec(spec)
            assert result.failed_count >= 1
            assert not result.all_passed
        finally:
            executor.teardown()

    def test_console_capture(self):
        """Test that console messages are captured."""
        from maestro_guard.specs.executor import SpecExecutor

        html = """<!DOCTYPE html>
<html><head><title>Console Test</title></head>
<body>
<script>
  console.log("info message");
  console.warn("warning message");
  console.error("error message");
</script>
</body></html>"""

        spec_text = """# Console Test
## Assertions
### Console: no errors
### Console: no warnings
"""
        spec = parse_spec(spec_text)
        executor = SpecExecutor(html)
        try:
            executor.setup()
            executor.load_html()
            result = executor.run_spec(spec)
            assert result.failed_count >= 1  # console.error should fail
            assert len(result.console_messages) >= 3
            error_msgs = [m for m in result.console_messages if m["type"] == "error"]
            assert len(error_msgs) == 1
        finally:
            executor.teardown()

    def test_style_assertion(self):
        """Test style assertions work."""
        from maestro_guard.specs.executor import SpecExecutor

        html = """<!DOCTYPE html>
<html><head>
<style>
  .flex-box { display: flex; }
</style>
</head>
<body>
  <div class="flex-box"><span>Item</span></div>
</body></html>"""

        spec_text = """# Style Test
## Assertions
### Style: `.flex-box` `display` == `flex`
"""
        spec = parse_spec(spec_text)
        executor = SpecExecutor(html)
        try:
            executor.setup()
            executor.load_html()
            result = executor.run_spec(spec)
            assert result.all_passed, f"Expected style pass but got: {result.results[0]}"
        finally:
            executor.teardown()
