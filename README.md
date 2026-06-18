# Maestro Guard — AI Code Verification Tool

**Maestro Guard** is a lightweight, zero-dependency CLI tool that verifies AI-generated HTML/JS code for common LLM bugs. It catches the silent failures that AI coding tools produce — broken DOM references, empty function stubs, console.errors left in production code, and syntax errors.

## Why

Every developer using Cursor, Claude Code, Copilot, or any AI coding tool has experienced this: the generated code *looks* right but has hidden bugs. Maestro Guard runs 4 deterministic checks in milliseconds to catch them.

## Install

```bash
pip install maestro-guard
```

Zero dependencies. Pure Python stdlib.

## Usage

### `check` — Verify code correctness

```bash
# Basic check
maestro-guard check index.html

# With spec fulfillment verification
maestro-guard check index.html --spec spec.md

# JSON output (for CI)
maestro-guard check index.html --json

# Verbose mode (shows skipped checks)
maestro-guard check index.html --verbose

# Check all HTML files in a directory
maestro-guard check ./output/
```

### `review` — Multi-perspective heuristic analysis

```bash
# Full 5-perspective review
maestro-guard review index.html

# Specific roles only
maestro-guard review index.html --roles security,ux,code_quality

# JSON output
maestro-guard review index.html --json

# Improvement analysis (structured fix suggestions)
maestro-guard review index.html --improve
```

The `review` command analyzes HTML/JS content from **5 expert perspectives** using built-in heuristic rules (no API keys required):

| Perspective | What it checks |
|---|---|
| **Security Auditor** | Inline event handlers, eval(), innerHTML, document.write, CSP, localStorage, data URIs |
| **Code Quality Analyst** | Commented-out code, TODO/FIXME markers, magic numbers, var usage, console.log, deep nesting, empty functions |
| **UX Reviewer** | Viewport meta tag, alt text, semantic HTML, form labels, ARIA attributes, loading states, focus styles |
| **Completeness Checker** | Page title, meta description, charset, favicon, placeholder content, broken links, empty sections, lang attribute |
| **Business Viability Reviewer** | Call-to-action, pricing, social proof, contact info, navigation, value proposition, analytics, footer |

#### Review output format

```
============================================================
  MULTI-PERSPECTIVE REVIEW REPORT
============================================================

  ❌ FAIL  Security Auditor  (4.5/10)
       ⚠ Inline event handlers found: onclick, onsubmit — potential XSS vector
       ⚠ No Content-Security-Policy meta tag found
       💡 Move event handlers to JS using addEventListener() instead of inline attributes
       💡 Add a Content-Security-Policy meta tag

  ✅ PASS  Code Quality Analyst  (8.0/10)
       💡 Remove commented-out code; use version control for history instead

  ❌ FAIL  UX Reviewer  (5.0/10)
       ⚠ No viewport meta tag found — page may not be mobile-friendly
       ⚠ Limited use of semantic HTML elements — poor accessibility
       💡 Add <meta name="viewport" content="width=device-width, initial-scale=1">
       💡 Use <header>, <nav>, <main>, <article>, <section>, <footer> for screen readers

  ❌ FAIL  Completeness Checker  (4.0/10)
       ⚠ Missing or empty <title> tag
       ⚠ Missing meta description tag
       ⚠ Missing charset meta tag
       💡 Add a descriptive <title> tag for SEO and browser tabs
       💡 Add <meta name="description" content="..."> for SEO

  ❌ FAIL  Business Viability Reviewer  (3.5/10)
       ⚠ No clear call-to-action (CTA) found — may reduce conversion
       ⚠ Weak value proposition — benefits/features not clearly stated
       ⚠ No social proof elements found
       💡 Add a prominent CTA button (e.g., 'Get Started', 'Sign Up', 'Contact Us')
       💡 Clearly articulate what problem you solve and why users should care

  ───────────────────────────────────────

  Overall Score: 50.0/100
  Status: ❌ SOME REVIEWS FAILED

============================================================
```

#### JSON output format

```json
{
  "overall_score": 50.0,
  "all_passed": false,
  "total_reviewers": 5,
  "verdict": "FAIL",
  "reviews": [
    {
      "role": "security",
      "role_name": "Security Auditor",
      "score": 4.5,
      "issues": ["Inline event handlers found...", "No CSP found..."],
      "suggestions": ["Move event handlers to JS using addEventListener()..."],
      "verdict": "fail",
      "weight": 20
    }
  ],
  "improvement_analysis": {
    "total_issues": 12,
    "by_severity": {
      "critical": 3,
      "major": 5,
      "minor": 4
    },
    "issues": [...]
  }
}
```

## Checks

- `js_syntax` (25) — Unbalanced braces/parens/brackets, broken strings
- `handlers` (25) — Empty function stubs, casing mismatches
- `dom_refs` (20) — `getElementById('x')` where `id="x"` doesn't exist
- `console_errors` (15) — `console.error()` / `console.warn()` in production code
- `fulfillment` (15) — Spec keywords not found in output (requires `--spec`)

A check must score **100/100** to pass. No partial credit. No silent failures. Either it works or it doesn't.

## Exit Codes

- **0** — All checks passed
- **1** — One or more checks failed

## Use in CI

```bash
# GitHub Action step
- name: Verify AI-generated code
  run: maestro-guard check ./output/index.html --json
```

## License

MIT
