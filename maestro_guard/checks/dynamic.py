"""Dynamic spec execution check — runs AI-generated HTML/JS in a headless browser
and verifies behavior against a markdown spec.

This check catches hallucinations that static analysis cannot:
- Functions that throw at runtime
- DOM elements that don't render as expected
- API calls to hallucinated endpoints
- Async behavior failures
- Console errors and unhandled rejections
- Styling that doesn't match requirements

Usage (via CLI):
    maestro-guard check index.html --exec-spec spec.md
"""

import os


def verify_dynamic(html_content: str, spec_content: str) -> tuple[bool, str, str]:
    """Run dynamic spec execution against HTML content.

    Parses the spec markdown, launches headless Chromium via Playwright,
    loads the HTML file, and runs every assertion in the browser context.

    Args:
        html_content: The raw HTML content to verify.
        spec_content: Raw markdown spec content (see demo/exec_spec.md).

    Returns:
        tuple[bool, str, str]: (all_passed, detail_summary, fix_suggestion)
    """
    # Check if Playwright is available
    try:
        from maestro_guard.specs.executor import HAS_PLAYWRIGHT
    except ImportError:
        return _no_playwright()

    if not HAS_PLAYWRIGHT:
        return _no_playwright()

    # Also check environment variable — Playwright browser may be installed
    # but we want to allow disabling browser-dependent checks
    if os.environ.get("MAESTRO_NO_BROWSER", "").lower() in ("1", "true", "yes"):
        return (True, "Dynamic spec execution disabled (MAESTRO_NO_BROWSER)", "")

    # Parse the spec
    from maestro_guard.specs.parser import parse_spec

    try:
        spec = parse_spec(spec_content)
    except Exception as exc:
        return (False, f"Failed to parse spec: {exc}", "Check spec format (see demo/exec_spec.md)")

    if not spec.assertions:
        return (True, "Spec has no executable assertions (nothing to verify)", "")

    # Execute spec in headless browser
    from maestro_guard.specs.executor import SpecExecutor

    executor = SpecExecutor(html_content)
    try:
        executor.setup()
        executor.load_html()

        result = executor.run_spec(spec)

        if result.all_passed:
            detail = (
                f"Dynamic spec: {result.passed_count}/{len(result.results)} "
                f"assertions passed ({result.total_duration_ms:.0f}ms)"
            )
            return (True, detail, "")

        # Build failure detail
        failures = [r for r in result.results if not r.passed]
        fail_lines = []
        for f in failures[:5]:
            desc = f.assertion.description[:60]
            if f.actual:
                fail_lines.append(f"  ❌ {desc} (got: {f.actual[:40]})")
            elif f.error:
                fail_lines.append(f"  ❌ {desc} (error: {f.error[:40]})")
            else:
                fail_lines.append(f"  ❌ {desc}")

        if len(failures) > 5:
            fail_lines.append(f"  ... and {len(failures) - 5} more failures")

        # Check for page errors
        if result.page_errors:
            fail_lines.append(f"  Page errors: {len(result.page_errors)}")

        detail = (
            f"Dynamic spec: {result.passed_count}/{len(result.results)} passed, "
            f"{result.failed_count} failed ({result.total_duration_ms:.0f}ms)\n"
            + "\n".join(fail_lines)
        )

        suggestion = (
            f"💡 Fix the failing assertions first — they reveal where AI-generated "
            f"code doesn't match the spec. Run 'maestro-guard check --exec-spec {spec.title}' "
            f"after each fix iteration."
        )

        return (False, detail, suggestion)

    except Exception as exc:
        return (False, f"Dynamic spec execution failed: {exc}", "Check that Playwright Chromium is installed: playwright install chromium")

    finally:
        try:
            executor.teardown()
        except Exception:
            pass


def _no_playwright() -> tuple[bool, str, str]:
    """Return when Playwright is not available."""
    return (
        True,
        "Dynamic spec execution skipped (Playwright not installed). "
        "Install with: pip install playwright && playwright install chromium",
        "",
    )
