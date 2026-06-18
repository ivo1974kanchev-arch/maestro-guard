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

```bash
# Basic check
maestro-guard check index.html

# With spec fulfillment verification
maestro-guard check index.html --spec spec.md

# JSON output (for CI)
maestro-guard check index.html --json

# Verbose mode (shows skipped checks)
maestro-guard check index.html --verbose
```

## Checks

| Check | Weight | What it catches |
|---|---|---|
| `js_syntax` | 25 | Unbalanced braces/parens/brackets, broken strings |
| `handlers` | 25 | Empty function stubs, casing mismatches |
| `dom_refs` | 20 | `getElementById('x')` where `id="x"` doesn't exist |
| `console_errors` | 15 | `console.error()` / `console.warn()` in production code |
| `fulfillment` | 15 | Spec keywords not found in output (requires `--spec`) |

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
