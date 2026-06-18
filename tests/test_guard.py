"""Comprehensive tests for maestro_guard verification library."""

import os
import tempfile
from pathlib import Path

from maestro_guard.report import GuardianReport
from maestro_guard.checks.js_syntax import verify_js_syntax
from maestro_guard.checks.handlers import verify_handlers
from maestro_guard.checks.dom_refs import verify_dom_refs
from maestro_guard.checks.console_errors import verify_console_errors
from maestro_guard.checks.fulfillment import verify_fulfillment

FIXTURES = Path(__file__).parent / "fixtures"


# ─── GuardianReport Tests ─────────────────────────────────────────────

class TestGuardianReport:
    def test_empty_report(self):
        r = GuardianReport()
        assert r.score == 0
        assert r.all_passed is False
        assert len(r.failing_checks) > 0

    def test_all_pass_score(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        r.add_check("handlers_defined", True, "OK", weight=25)
        r.add_check("dom_refs", True, "OK", weight=20)
        r.add_check("no_console_errors", True, "OK", weight=15)
        r.add_check("fulfillment", True, "OK", weight=15)
        assert r.score == 100
        assert r.all_passed is True

    def test_partial_score(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        r.add_check("handlers_defined", False, "Empty stubs", weight=25)
        assert r.score < 100
        assert r.all_passed is False

    def test_failing_checks(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        r.add_check("handlers_defined", False, "Empty: foo", weight=25)
        fails = r.failing_checks
        assert any("handlers" in name for name, _ in fails)

    def test_to_dict_structure(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        d = r.to_dict()
        assert "score" in d
        assert "all_passed" in d
        assert "checks" in d
        assert "fixes" in d

    def test_to_json(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        j = r.to_json()
        assert '"score"' in j
        assert '"checks"' in j

    def test_summary_contains_score(self):
        r = GuardianReport()
        r.add_check("js_syntax", True, "OK", weight=25)
        s = r.summary()
        assert "25/100" in s or "Score" in s


# ─── JS Syntax Check Tests ────────────────────────────────────────────

class TestJsSyntax:
    def test_valid_js_passes(self):
        html = "<script>function foo() { return 1; } var x = 5;</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert ok, msg

    def test_unbalanced_braces_fails(self):
        html = "<script>function foo() { if (x) { bar(); }</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert not ok, "Should detect unbalanced braces"

    def test_unbalanced_parens_fails(self):
        html = "<script>foo(bar(1, 2);</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert not ok, "Should detect unbalanced parens"

    def test_empty_html_passes(self):
        ok, msg, _ = verify_js_syntax("<html><body></body></html>")
        assert ok, "Empty HTML should pass"

    def test_no_script_block_passes(self):
        ok, msg, _ = verify_js_syntax("<html><body><p>No JS here</p></body></html>")
        assert ok, "No script block should pass"

    def test_multiple_script_blocks(self):
        html = "<script>var a = 1;</script><script>function b() { return a; }</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert ok, msg

    def test_template_literals(self):
        html = "<script>const x = `${a} + ${b}`; const y = `{ ${c} }`;</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert ok, "Template literals with braces should pass"

    def test_arrow_functions(self):
        html = "<script>const fn = (x) => { return x * 2; };</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert ok, "Arrow functions should pass"

    def test_unbalanced_brackets(self):
        html = "<script>const arr = [1, 2, 3;</script>"
        ok, msg, _ = verify_js_syntax(html)
        assert not ok, "Should detect unbalanced brackets"


# ─── Handlers Check Tests ─────────────────────────────────────────────

class TestHandlers:
    def test_non_empty_functions_pass(self):
        html = "<script>function foo() { return 1; } function bar(x) { return x + 1; }</script>"
        ok, msg, _ = verify_handlers(html)
        assert ok, msg

    def test_empty_stub_detected(self):
        html = "<script>function handleClick() {}</script>"
        ok, msg, _ = verify_handlers(html)
        assert not ok, "Empty function stub should be detected"

    def test_mixed_full_and_empty(self):
        html = "<script>function realFn() { return 1; } function stubFn() {}</script>"
        ok, msg, _ = verify_handlers(html)
        assert not ok, "Should detect empty stub among real functions"

    def test_no_functions_passes(self):
        html = "<script>var x = 5; console.log(x);</script>"
        ok, msg, _ = verify_handlers(html)
        assert ok, "No function definitions should pass"

    def test_no_script_passes(self):
        ok, msg, _ = verify_handlers("<html></html>")
        assert ok

    def test_async_functions(self):
        html = "<script>async function fetchData() { const r = await fetch('/api'); return r.json(); }</script>"
        ok, msg, _ = verify_handlers(html)
        assert ok, "Async functions should pass"

    def test_function_expressions(self):
        html = "<script>const handler = function() { return 1; };</script>"
        ok, msg, _ = verify_handlers(html)
        assert ok, "Function expressions should pass"


# ─── DOM Refs Check Tests ─────────────────────────────────────────────

class TestDomRefs:
    def test_matching_ids_pass(self):
        html = """
        <div id="app"></div>
        <div id="output"></div>
        <script>
            document.getElementById('app');
            document.getElementById('output');
        </script>
        """
        ok, msg, _ = verify_dom_refs(html)
        assert ok, msg

    def test_missing_id_detected(self):
        html = """
        <div id="main"></div>
        <script>document.getElementById('nonexistent');</script>
        """
        ok, msg, _ = verify_dom_refs(html)
        assert not ok, "Missing DOM ID should be detected"
        assert 'nonexistent' in msg

    def test_no_getelementbyid_passes(self):
        html = "<script>console.log('hello');</script>"
        ok, msg, _ = verify_dom_refs(html)
        assert ok

    def test_multiple_missing_ids(self):
        html = """
        <script>
            document.getElementById('a');
            document.getElementById('b');
        </script>
        """
        ok, msg, _ = verify_dom_refs(html)
        assert not ok
        assert "a" in msg and "b" in msg


# ─── Console Errors Check Tests ───────────────────────────────────────

class TestConsoleErrors:
    def test_clean_js_passes(self):
        html = "<script>console.log('info'); console.debug('debug');</script>"
        ok, msg, _ = verify_console_errors(html)
        assert ok, "console.log should not fail"

    def test_console_error_detected(self):
        html = "<script>console.error('Something broke');</script>"
        ok, msg, _ = verify_console_errors(html)
        assert not ok, "console.error should be detected"

    def test_console_warn_allowed(self):
        html = "<script>console.warn('deprecated');</script>"
        ok, msg, _ = verify_console_errors(html)
        assert ok, "console.warn should be allowed (graceful degradation)"

    def test_no_script_passes(self):
        ok, msg, _ = verify_console_errors("<html></html>")
        assert ok

    def test_console_error_in_string_ignored(self):
        html = "<script>const msg = 'console.error should not fire';</script>"
        ok, msg, _ = verify_console_errors(html)
        assert ok, "console.error in a string literal should be ignored"

    def test_console_error_variable_ignored(self):
        html = "<script>const console = { error: function() {} };</script>"
        ok, msg, _ = verify_console_errors(html)
        assert ok, "console.error as property definition should be ignored"


# ─── Fulfillment Check Tests ─────────────────────────────────────────

class TestFulfillment:
    def test_passing_keywords(self):
        html = "<html><body><div id=\"dashboard\"></div><div id=\"chart\"></div><script>var data = 42; function render() { return data; }</script></body></html>"
        spec = "dashboard chart data render"
        ok, msg, _ = verify_fulfillment(html, spec)
        assert ok, f"Keywords should match: {msg}"

    def test_failing_no_keywords(self):
        html = "<script>function foo() {}</script>"
        spec = "Build a login page with authentication and user management"
        ok, msg, _ = verify_fulfillment(html, spec)
        assert not ok, "No matching keywords should fail"

    def test_empty_spec(self):
        html = "<script>function foo() {}</script>"
        ok, msg, _ = verify_fulfillment(html, "")
        assert not ok, "Empty spec should fail"


# ─── Integration Tests ────────────────────────────────────────────────

class TestIntegration:
    def test_good_fixture_passes_all(self):
        path = FIXTURES / "good.html"
        content = path.read_text(encoding="utf-8")
        
        r = GuardianReport()
        ok, msg, _ = verify_js_syntax(content)
        r.add_check("js_syntax", ok, msg, weight=25)
        ok, msg, _ = verify_handlers(content)
        r.add_check("handlers_defined", ok, msg, weight=25)
        ok, msg, _ = verify_dom_refs(content)
        r.add_check("dom_refs", ok, msg, weight=20)
        ok, msg, _ = verify_console_errors(content)
        r.add_check("no_console_errors", ok, msg, weight=15)
        
        assert r.all_passed, f"Good fixture should pass all checks. Score: {r.score}/100\n{r.summary()}"

    def test_bad_fixture_fails(self):
        path = FIXTURES / "bad.html"
        content = path.read_text(encoding="utf-8")
        
        r = GuardianReport()
        ok, msg, _ = verify_js_syntax(content)
        r.add_check("js_syntax", ok, msg, weight=25)
        ok, msg, _ = verify_handlers(content)
        r.add_check("handlers_defined", ok, msg, weight=25)
        ok, msg, _ = verify_dom_refs(content)
        r.add_check("dom_refs", ok, msg, weight=20)
        ok, msg, _ = verify_console_errors(content)
        r.add_check("no_console_errors", ok, msg, weight=15)
        
        assert not r.all_passed, "Bad fixture should fail"
        assert r.score < 100, "Bad fixture should have score < 100"
