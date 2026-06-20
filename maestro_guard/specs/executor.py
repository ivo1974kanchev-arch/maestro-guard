"""
Dynamic Spec Executor — Runs parsed assertions against a live HTML page.

Uses Playwright to launch a headless Chromium browser, load the page,
and evaluate JavaScript assertions in the browser context. Captures
console output, errors, and DOM state for verification.

Two modes:
1. Playwright mode (default, full browser) — most capable.
2. CDP-only mode (lighter, no playwright dependency needed) — experimental.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from maestro_guard.specs.parser import (
    Assertion,
    AssertionType,
    ParsedSpec,
)


@dataclass
class AssertionResult:
    """Result of executing a single assertion.

    Attributes:
        assertion: The original assertion.
        passed: Whether the assertion passed.
        actual: The actual value obtained from the browser.
        error: Error message if execution failed.
        duration_ms: How long execution took.
    """
    assertion: Assertion
    passed: bool = False
    actual: str = ""
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class SpecResult:
    """Result of executing an entire spec against a page.

    Attributes:
        spec: The parsed spec.
        results: Per-assertion results.
        passed_count: Number of passed assertions.
        failed_count: Number of failed assertions.
        total_duration_ms: Total execution time.
        console_messages: All console messages captured during execution.
        page_errors: JavaScript errors caught during execution.
        all_passed: True if every assertion passed.
    """
    spec: ParsedSpec
    results: list[AssertionResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_duration_ms: float = 0.0
    console_messages: list[dict] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    all_passed: bool = False


# ── Try to import Playwright ──────────────────────────────────────────

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class SpecExecutor:
    """Executes parsed specs against a live HTML page in a headless browser.

    Args:
        html_content: The HTML content to render.
        html_path: Optional file path (if content comes from a file).
        headless: Whether to run in headless mode.
        timeout_ms: Global timeout for assertions.
    """

    def __init__(
        self,
        html_content: str,
        html_path: str = "",
        headless: bool = True,
        timeout_ms: int = 5000,
    ):
        self.html_content = html_content
        self.html_path = html_path
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._console_log: list[dict] = []
        self._page_errors: list[str] = []

    def _on_console(self, msg):
        """Capture console messages from the browser."""
        entry = {
            "type": msg.type,
            "text": msg.text,
            "location": str(msg.location) if hasattr(msg, "location") else "",
        }
        self._console_log.append(entry)

    def _on_page_error(self, err):
        """Capture uncaught page errors."""
        self._page_errors.append(str(err))

    def setup(self) -> None:
        """Launch browser and create a page."""
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright is required for dynamic spec execution. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        self._page = self._context.new_page()

        # Capture console messages
        self._page.on("console", self._on_console)
        self._page.on("pageerror", self._on_page_error)

    def teardown(self) -> None:
        """Close browser and clean up."""
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            self._playwright.stop()

    def load_html(self) -> None:
        """Load the HTML content into the browser page."""
        # Write HTML to a temporary file and load via file://
        import tempfile
        import os

        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            delete=False,
            encoding="utf-8",
        )
        tmp.write(self.html_content)
        tmp_path = tmp.name
        tmp.close()

        try:
            self._page.goto(f"file://{tmp_path}", wait_until="networkidle")
        except Exception as e:
            # networkidle may not fire if there are no resources; try domcontentloaded
            self._page.goto(f"file://{tmp_path}", wait_until="domcontentloaded")
        finally:
            os.unlink(tmp_path)

    def _evaluate(self, js_expression: str, timeout_ms: int | None = None) -> Any:
        """Evaluate a JavaScript expression in the browser context.

        Args:
            js_expression: JavaScript code to evaluate.
            timeout_ms: Timeout in milliseconds.

        Returns:
            The result of evaluation (stringified).

        Raises:
            RuntimeError: If evaluation fails or times out.
        """
        timeout = timeout_ms or self.timeout_ms
        try:
            result = self._page.evaluate(js_expression)
            # Convert to string for comparison
            if result is None:
                return "null"
            if isinstance(result, bool):
                return "true" if result else "false"
            if isinstance(result, (int, float)):
                return str(result)
            if isinstance(result, str):
                return result
            if isinstance(result, dict) or isinstance(result, list):
                return json.dumps(result)
            return str(result)
        except Exception as e:
            raise RuntimeError(f"JS eval failed: {e}")

    def _evaluate_style(self, selector: str, property: str) -> str:
        """Evaluate a CSS computed style in the browser.

        Args:
            selector: CSS selector for the element.
            property: CSS property name (camelCase).

        Returns:
            The computed value as a string.
        """
        js = (
            f"(function() {{"
            f"  const el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return 'null';"
            f"  return getComputedStyle(el).getPropertyValue({json.dumps(property)});"
            f"}})()"
        )
        return self._evaluate(js)

    def _run_dom_equals(self, assertion: Assertion) -> AssertionResult:
        """Run a DOM == assertion."""
        actual = self._evaluate(assertion.js_expression, assertion.timeout_ms)
        expected = assertion.expected
        passed = actual == expected
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
            duration_ms=0.0,
        )

    def _run_dom_not_equals(self, assertion: Assertion) -> AssertionResult:
        """Run a DOM != assertion."""
        actual = self._evaluate(assertion.js_expression, assertion.timeout_ms)
        passed = actual != assertion.expected
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_dom_gte(self, assertion: Assertion) -> AssertionResult:
        """Run a DOM >= assertion (numeric comparison)."""
        actual = self._evaluate(assertion.js_expression, assertion.timeout_ms)
        try:
            actual_num = float(actual)
            expected_num = float(assertion.expected)
            passed = actual_num >= expected_num
        except (ValueError, TypeError):
            passed = False
            actual = f"{actual} (not numeric)"
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_dom_matches(self, assertion: Assertion) -> AssertionResult:
        """Run a DOM matches (regex) assertion."""
        actual = self._evaluate(assertion.js_expression, assertion.timeout_ms)
        try:
            import re
            passed = bool(re.search(assertion.expected, actual))
        except re.error as e:
            passed = False
            actual = f"{actual} (regex error: {e})"
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_js_typeof(self, assertion: Assertion) -> AssertionResult:
        """Run a JS typeof assertion."""
        expr = f"typeof ({assertion.js_expression})"
        actual = self._evaluate(expr, assertion.timeout_ms)
        passed = actual == assertion.expected
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_js_equals(self, assertion: Assertion) -> AssertionResult:
        """Run a JS == assertion."""
        actual = self._evaluate(assertion.js_expression, assertion.timeout_ms)
        passed = actual == assertion.expected
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_console_no_errors(self, assertion: Assertion) -> AssertionResult:
        """Check that no console.error calls were made."""
        errors = [m for m in self._console_log if m["type"] == "error"]
        passed = len(errors) == 0
        detail = f"{len(errors)} console.error(s)" if errors else "0 console.errors"
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=detail,
        )

    def _run_console_no_warnings(self, assertion: Assertion) -> AssertionResult:
        """Check that no console.warn calls were made."""
        warnings = [m for m in self._console_log if m["type"] == "warning"]
        passed = len(warnings) == 0
        detail = f"{len(warnings)} console.warn(s)" if warnings else "0 console.warns"
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=detail,
        )

    def _run_console_warn_count(self, assertion: Assertion) -> AssertionResult:
        """Check console.warn count against a threshold."""
        warnings = [m for m in self._console_log if m["type"] == "warning"]
        actual_count = len(warnings)
        threshold = int(assertion.expected)
        passed = actual_count <= threshold
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=str(actual_count),
        )

    def _run_behavior(self, assertion: Assertion) -> AssertionResult:
        """Run a behavior assertion — execute the steps and check result.

        The behavior assertion expects the js_expression field to contain
        newline-separated JavaScript steps to execute.
        """
        steps = assertion.js_expression.split("\n")
        try:
            for step in steps:
                step = step.strip()
                if step:
                    self._evaluate(step, assertion.timeout_ms)
            return AssertionResult(
                assertion=assertion,
                passed=True,
                actual="Steps executed",
            )
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error=str(e),
            )

    def _run_style_equals(self, assertion: Assertion) -> AssertionResult:
        """Run a Style == assertion."""
        actual = self._evaluate_style(assertion.selector, assertion.property)
        passed = actual == assertion.expected
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual,
        )

    def _run_async_no_errors(self, assertion: Assertion) -> AssertionResult:
        """Check that no unhandled errors occurred during page load."""
        passed = len(self._page_errors) == 0
        detail = "; ".join(self._page_errors[:5]) if self._page_errors else "No errors"
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=detail,
        )

    def run_assertion(self, assertion: Assertion) -> AssertionResult:
        """Dispatch a single assertion to the appropriate runner method."""
        start = time.time()

        try:
            runners = {
                AssertionType.DOM_EQUALS: self._run_dom_equals,
                AssertionType.DOM_NOT_EQUALS: self._run_dom_not_equals,
                AssertionType.DOM_GREATER_OR_EQ: self._run_dom_gte,
                AssertionType.DOM_MATCHES: self._run_dom_matches,
                AssertionType.JS_TYPE_OF: self._run_js_typeof,
                AssertionType.JS_EQUALS: self._run_js_equals,
                AssertionType.CONSOLE_NO_ERRORS: self._run_console_no_errors,
                AssertionType.CONSOLE_NO_WARNINGS: self._run_console_no_warnings,
                AssertionType.CONSOLE_WARN_COUNT: self._run_console_warn_count,
                AssertionType.BEHAVIOR: self._run_behavior,
                AssertionType.STYLE_EQUALS: self._run_style_equals,
                AssertionType.ASYNC_NO_ERRORS: self._run_async_no_errors,
            }

            runner = runners.get(assertion.assert_type)
            if runner is None:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    error=f"No runner for assertion type: {assertion.assert_type}",
                )

            result = runner(assertion)
            result.duration_ms = (time.time() - start) * 1000
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error=str(e),
                duration_ms=duration,
            )

    def run_spec(self, spec: ParsedSpec) -> SpecResult:
        """Run all assertions in a parsed spec against the loaded page.

        Args:
            spec: The parsed spec to execute.

        Returns:
            SpecResult with per-assertion results.
        """
        results = []
        passed_count = 0
        failed_count = 0

        for assertion in spec.assertions:
            # Skip structure checks (not executable)
            if assertion.assert_type == AssertionType.STRUCTURE_CHECK:
                continue

            result = self.run_assertion(assertion)
            results.append(result)

            if result.passed:
                passed_count += 1
            else:
                failed_count += 1

        total_duration = sum(r.duration_ms for r in results)

        return SpecResult(
            spec=spec,
            results=results,
            passed_count=passed_count,
            failed_count=failed_count,
            total_duration_ms=total_duration,
            console_messages=self._console_log,
            page_errors=self._page_errors,
            all_passed=failed_count == 0,
        )

    def format_results(self, result: SpecResult) -> str:
        """Format spec results as a human-readable string."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  DYNAMIC SPEC EXECUTION: {result.spec.title}")
        lines.append("=" * 60)
        lines.append("")

        for r in result.results:
            icon = "✅ PASS" if r.passed else "❌ FAIL"
            desc = r.assertion.description[:70]
            lines.append(f"  {icon}  {desc}")

            if not r.passed:
                if r.actual:
                    lines.append(f"         Actual: {r.actual[:60]}")
                if r.error:
                    lines.append(f"         Error: {r.error[:60]}")
            lines.append(f"         ({r.duration_ms:.0f}ms)")

        lines.append("")
        lines.append("  " + "─" * 39)
        lines.append("")
        lines.append(
            f"  Results: {result.passed_count} passed, {result.failed_count} failed "
            f"({result.total_duration_ms:.0f}ms total)"
        )

        if result.console_messages:
            error_msgs = [m for m in result.console_messages if m["type"] == "error"]
            warn_msgs = [m for m in result.console_messages if m["type"] == "warning"]
            if error_msgs:
                lines.append(f"  Console errors: {len(error_msgs)}")
                for m in error_msgs[:3]:
                    lines.append(f"    ❌ {m['text'][:80]}")
            if warn_msgs:
                lines.append(f"  Console warnings: {len(warn_msgs)}")
                for m in warn_msgs[:3]:
                    lines.append(f"    ⚠ {m['text'][:80]}")

        if result.page_errors:
            lines.append(f"  Page errors: {len(result.page_errors)}")
            for err in result.page_errors[:3]:
                lines.append(f"    ❌ {err[:80]}")

        status = "✅ ALL ASSERTIONS PASSED" if result.all_passed else "❌ SOME ASSERTIONS FAILED"
        lines.append(f"  Status: {status}")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
