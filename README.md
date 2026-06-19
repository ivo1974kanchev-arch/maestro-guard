# Maestro Guard — AI Code Verification

**Zero-dependency CLI tool that checks AI-generated HTML/JS for the bugs LLMs consistently produce.**

Every developer using Cursor, Claude Code, or Copilot has shipped AI code that looked right but had hidden bugs. Maestro Guard catches them in milliseconds — broken DOM references, empty function stubs, console.errors left in production, syntax errors.

```bash
pip install maestro-guard
maestro-guard check index.html --json
```

Zero dependencies. Pure Python stdlib.

## Commands

### `check` — Deterministic code verification

```bash
maestro-guard check index.html
maestro-guard check index.html --spec spec.md     # With spec fulfillment
maestro-guard check index.html --json              # CI-friendly JSON output
maestro-guard check index.html --verbose           # Show skipped checks
maestro-guard check ./output/                      # Check all HTML files
```

### `review` — Multi-perspective heuristic analysis

```bash
maestro-guard review index.html                    # Full 5-perspective review
maestro-guard review index.html --roles security,ux  # Specific roles only
maestro-guard review index.html --improve           # Structured fix suggestions
```

The `review` command analyzes code from 5 expert perspectives using built-in heuristics. No API keys required.

| Perspective | What it checks |
|---|---|
| **Security Auditor** | Inline event handlers, eval(), innerHTML, CSP, localStorage |
| **Code Quality Analyst** | Dead code, magic numbers, var usage, console.log, nesting |
| **UX Reviewer** | Viewport meta, alt text, semantic HTML, ARIA, focus styles |
| **Completeness Checker** | Page title, meta description, charset, favicon, broken links |
| **Business Viability Reviewer** | CTA, pricing, social proof, navigation, value proposition |

## The 4 Checks

| Check | Weight | What it catches |
|---|---|---|
| `js_syntax` | 25 | Unbalanced braces/parens/brackets, broken strings |
| `handlers` | 25 | Empty function stubs, casing mismatches |
| `dom_refs` | 20 | `getElementById('x')` where `id="x"` doesn't exist |
| `console_errors` | 15 | `console.error()` / `console.warn()` in production |
| `fulfillment` | 15 | Spec keywords not found in output (requires `--spec`) |

A check must score **100/100** to pass. No partial credit. No silent failures.

## Exit Codes

- **0** — All checks passed
- **1** — One or more checks failed

## Example Output

```
============================================================
  MULTI-PERSPECTIVE REVIEW REPORT
============================================================

  ❌ FAIL  Security Auditor  (4.5/10)
       ⚠ Inline event handlers found: onclick, onsubmit
       ⚠ No Content-Security-Policy meta tag found
       💡 Use addEventListener() instead of inline attributes

  ✅ PASS  Code Quality Analyst  (8.0/10)

  ❌ FAIL  UX Reviewer  (5.0/10)
       ⚠ No viewport meta tag found
       ⚠ Limited use of semantic HTML

  ───────────────────────────────────────
  Overall Score: 50.0/100
  Status: ❌ SOME REVIEWS FAILED
```

## Use in CI

```yaml
- name: Verify AI-generated code
  run: maestro-guard check ./output/index.html --json
```

## Why Maestro Guard

This is a standalone version of the verification engine from [Maestro](https://github.com/maestro-build/maestro). Same checks. No build pipeline. Use it when you just need to verify files, not run a full spec-driven workflow.

It's intentionally minimal. Four checks. Two commands. Zero dependencies. MIT licensed.

## License

MIT
