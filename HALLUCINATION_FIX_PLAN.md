# Maestro Guard v0.2.0 — Hallucination Detection via Dynamic Execution
## Implementation Plan

Created: 2026-06-20  
Status: Research complete, prototype built  
From: Analysis of `/root/maestro-guard/` (v0.1.0)

---

## 1. Executive Summary

**Goal**: Upgrade Maestro Guard from static analysis (regex-based HTML/JS checks) to **dynamic execution** — running AI-generated HTML/JS in a sandboxed headless browser and verifying behavior against a markdown spec.

**Status**: Prototype complete. 23 new tests passing (18 parser + 5 executor). 72 existing tests still passing. Total: 95 tests.

**Key insight**: LLMs generate code that *looks* correct but fails at runtime. Static analysis can catch broken DOM refs and syntax errors, but only dynamic execution catches:
- Functions that throw at runtime
- DOM elements that don't render as expected
- API calls to hallucinated endpoints
- Async behavior failures
- Console errors and unhandled rejections
- Styling that doesn't match requirements

---

## 2. Current Architecture (v0.1.0)

```
maestro_guard/
├── cli.py              # CLI entry point (argparse)
├── __init__.py
├── __main__.py
├── report.py            # GuardianReport (scoring, summary)
├── review.py            # ReviewOrchestrator (heuristic 5-perspective review)
├── checks/
│   ├── dom_refs.py      # getElementById vs HTML id attribute check
│   ├── handlers.py      # Empty function stubs, casing mismatches
│   ├── console_errors.py# console.error/warn detection
│   ├── js_syntax.py     # Balanced braces, parens, Node.js syntax check
│   └── fulfillment.py   # Keyword-based spec fulfillment (15% threshold)
└── review/
    ├── aggregator.py    # Score aggregation
    ├── improver.py      # Content improvement analysis
    └── prompts.py       # Role definitions
```

**Current checks** (all static, all regex-based):
| Check | Weight | Method |
|---|---|---|
| js_syntax | 25 | Regex + Node.js `--check` |
| handlers | 25 | Regex function body analysis |
| dom_refs | 20 | Regex ID matching |
| console_errors | 15 | Regex call detection |
| fulfillment | 15 | Keyword overlap (15% threshold) |

**Dependencies**: Pure Python stdlib (+ `lxml` for review module, optional).

**Tests**: 72 unit/integration tests via pytest.

---

## 3. Target Architecture (v0.2.0)

```
maestro_guard/
├── cli.py              # Extended CLI with --exec-spec flag
├── __init__.py
├── __main__.py
├── report.py            # Extended: dynamic check results
├── checks/
│   ├── ...              # Unchanged static checks
│   └── dynamic.py       # NEW: wraps spec parser + executor as a check
├── specs/               # NEW: dynamic spec subsystem
│   ├── __init__.py
│   ├── parser.py        # NEW: markdown spec -> structured assertions
│   └── executor.py      # NEW: Playwright-based assertion runner
└── sandbox/             # NEW: Docker-based sandboxing (future)
    └── runner.py        # NEW: container lifecycle management
```

**New capabilities**:
- `maestro-guard check index.html --exec-spec spec.md` — dynamic execution verification
- Markdown specs define executable assertions against live browser DOM
- Playwright headless Chromium runs the page and checks behavior
- Docker sandbox for untrusted AI-generated code (optional, configurable)

**New dependencies**: `playwright>=1.40` (already installed), Docker for sandboxing (already available)

---

## 4. Spec Format (Designed & Prototyped)

### Full example (from `demo/exec_spec.md`):

```markdown
# SaaS Analytics Dashboard — Dynamic Spec

## Description
A modern dark-themed analytics dashboard that loads metrics from an API
and displays them in stat cards with charts and activity feed.

## Assertions

### DOM: `document.title` == `Analytics Dashboard — Acme Corp`
### DOM: `document.querySelectorAll('.stat-card').length` >= `4`
### DOM: `document.querySelector('.stat-card .value')` != `null`

### JS: `typeof window.initDashboard` == `function`
### JS: `typeof window.loadMetrics` == `function`

### Console: no errors
### Console: no warnings

### Style: `.sidebar` `display` == `flex`
### Style: `.stats-grid` `display` == `grid`

### Behavior: refreshData disables button
```js
document.querySelector('.refresh-btn').click()
document.querySelector('.refresh-btn').disabled == true
```

### Async: page loads without uncaught errors
### Timeout: 5000ms

## Exemptions
- console.warn for "Could not load live data" is acceptable
```

### Supported assertion types:

| Prefix | Example | What it checks |
|---|---|---|
| `### DOM:` | `### DOM: \`expr\` == \`value\`` | JS expression result equals expected |
| `### DOM:` | `### DOM: \`expr\` >= \`4\`` | Numeric comparison |
| `### DOM:` | `### DOM: \`expr\` != \`null\`` | Not-equals |
| `### DOM:` | `### DOM: \`expr\` matches \`pattern\`` | Regex match |
| `### JS:` | `### JS: \`typeof x\` == \`function\`` | Type checking |
| `### JS:` | `### JS: \`1+1\` == \`2\`` | Value equality |
| `### Console:` | `### Console: no errors` | Zero console.error calls |
| `### Console:` | `### Console: warn count <= 3` | Warning threshold |
| `### Style:` | `### Style: \`.sel\` \`prop\` == \`val\`` | CSS computed style |
| `### Behavior:` | Followed by ```js``` block | Execute steps in browser |
| `### Async:` | `### Async: page loads without errors` | No unhandled errors |
| `### Timeout:` | `### Timeout: 5000ms` | Global assertion timeout |
| `### Structure` | Non-executable, for spec readability | |

---

## 5. File-by-File Build Plan

### Phase 1: Core Spec System (PROTOTYPED ✓)

| File | Lines | What it does | Status |
|---|---|---|---|
| `maestro_guard/specs/__init__.py` | 1 | Package init | DONE |
| `maestro_guard/specs/parser.py` | ~320 | Markdown → `ParsedSpec` with 14 assertion types | DONE |
| `maestro_guard/specs/executor.py` | ~400 | Playwright browser + assertion execution | DONE |
| `tests/test_specs.py` | ~360 | 23 tests (18 parser + 5 executor) | DONE |
| `demo/exec_spec.md` | ~65 | Example spec for SaaS dashboard | DONE |

### Phase 2: CLI Integration (TODO)

| File | What to build |
|---|---|
| `maestro_guard/checks/dynamic.py` | New check wrapper: parse spec → launch executor → return results |
| `maestro_guard/cli.py` | Add `--exec-spec` flag to `check` command |
| `maestro_guard/report.py` | Extend GuardianReport to include dynamic check results |
| `tests/test_dynamic_check.py` | Integration test for the CLI path |

### Phase 3: Docker Sandboxing (TODO)

| File | What to build |
|---|---|
| `maestro_guard/sandbox/__init__.py` | Package init |
| `maestro_guard/sandbox/runner.py` | Container lifecycle: pull image, copy HTML, run headless, clean up |
| `maestro_guard/sandbox/Dockerfile` | Minimal image with Python + Playwright Chromium |
| `tests/test_sandbox.py` | Integration test for sandbox mode |

### Phase 4: Advanced Features (FUTURE)

| File/Feature | What to build |
|---|---|
| `specs/hallucination_patterns.py` | Pre-built spec templates for common AI code patterns |
| CDP direct mode | Experimental: lighter dependency via websockets + raw CDP |
| HTML report output | Rich HTML report with screenshots of failures |
| CI integration docs | GitHub Actions example for `--exec-spec` |

---

## 6. How Sandboxed Execution Works

### Architecture (Docker-based):

```
┌──────────────────────────────┐
│   Host (maestro-guard CLI)   │
│                              │
│  1. Read HTML + spec         │
│  2. Create tempdir           │
│  3. Write HTML to tempdir    │
│  4. docker run --rm          │
│     -v tempdir:/work         │
│     -m 512m --cpus 1         │
│     --network none           │
│     --security-opt           │
│       no-new-privileges      │
│                              │
│  5. Container:               │
│     - Launch Playwright      │
│     - Load HTML via file://  │
│     - Run assertions         │
│     - Output JSON to stdout  │
│                              │
│  6. Parse JSON result        │
│  7. Clean up tempdir         │
│  8. Report to user           │
└──────────────────────────────┘
```

### Docker image (~150MB):

```dockerfile
FROM python:3.11-slim
RUN pip install playwright && \
    playwright install chromium && \
    playwright install-deps chromium
COPY --from=build /app/specs /usr/lib/maestro/specs
```

### Security considerations:
- `--network none` — no network access (prevents data exfiltration)
- `--read-only` — read-only filesystem
- `--cap-drop ALL` — drop all Linux capabilities
- `--security-opt no-new-privileges` — prevent privilege escalation
- Memory limit 512MB, CPU limit 1 core — prevent resource exhaustion
- Temp directory cleaned up after execution

---

## 7. Dependencies

### Required (already available):
| Package | Version | Purpose | Status |
|---|---|---|---|
| `playwright` | >=1.40 | Headless browser automation | ALREADY INSTALLED (1.60.0) |
| `websockets` | >=10 | (Alternative) direct CDP connection | ALREADY INSTALLED |

### Optional (already available):
| Tool | Purpose | Status |
|---|---|---|
| `docker` | Sandboxed execution container | ALREADY AVAILABLE (29.3.0) |
| `node` >=18 | Backend syntax checking | ALREADY AVAILABLE (v20.20.2) |

### No new pip packages needed for v0.2.0 MVP.
Playwright and websockets are already in the environment. Docker is available for sandboxing.

---

## 8. Risk Areas / Hard Problems

### HIGH: Playwright browser download size
- **Risk**: `playwright install chromium` downloads ~300MB of browser binaries
- **Mitigation**: Pre-build Docker image with browsers cached; or use `chromium_headless_shell` (lighter, ~80MB)
- **Observation**: Playwright + Chromium is already installed on the current system

### MEDIUM: AI code may attempt network access
- **Risk**: AI-generated code may `fetch()` to hallucinated APIs
- **Mitigation**: `--network none` in Docker container; Playwright intercept + block all network requests
- **Current behavior**: `networkidle` wait may hang if code pings unreachable endpoints; use `domcontentloaded` fallback

### MEDIUM: Async behavior timing
- **Risk**: Spec assertions run before async JS completes
- **Mitigation**: Each assertion has configurable timeout; `Async:` assertions wait for page idle; `Behavior:` assertions execute step-by-step with explicit waits

### MEDIUM: Malicious code in sandbox
- **Risk**: AI-generated HTML/JS could contain XSS, infinite loops, or resource abuse
- **Mitigation**: Docker with `--network none`, memory/cpu limits, read-only FS, timeouts
- **Escalation**: For untrusted code, run in a disposable VM (Firecracker/snap) instead of Docker

### LOW: Spec format ambiguity
- **Risk**: Backtick-delimited expressions could conflict with markdown formatting
- **Mitigation**: Spec uses `###` prefix (not interpreted by markdown renderers); backtick pairs inside `### ` lines are unambiguous

### LOW: CDP alternative complexity
- **Risk**: Building a CDP-only executor requires ~500+ lines of websocket protocol handling
- **Mitigation**: Use Playwright by default (already installed); CDP-only mode is a future optimization goal, not MVP requirement

---

## 9. Key Design Decisions

### Why Playwright over CDP-only for MVP:
- Playwright is already installed (1.60.0 with Chromium 1223)
- Handles browser lifecycle, page navigation, console capture, error handling
- CDP-only would need manual websocket management, protocol message parsing, and is more fragile
- Future: Add CDP mode for environments where Playwright can't be installed

### Why backtick-delimited assertions over YAML/JSON:
- AI models (Claude, GPT) generate markdown naturally
- No new schema to learn — spec looks like documentation
- Spec doubles as documentation for human readers
- Easy to parse with simple regex (no YAML parser dependency)

### Why separate spec parser from executor:
- Parser has zero dependencies (pure Python stdlib)
- Executor requires Playwright (heavier dependency)
- Can run parser in CI without browsers installed (syntax checking)
- Can swap executor (CDP vs Playwright) without changing spec format

---

## 10. Implementation Estimate

| Phase | Files | Person-days | Risk |
|---|---|---|---|
| P1: Core spec system | 5 files, ~800 LOC | ✅ DONE | None |
| P2: CLI integration | 3 files, ~200 LOC | 1 day | Low |
| P3: Docker sandbox | 3 files, ~300 LOC | 2 days | Medium |
| P4: Advanced features | Varies | 5 days | Medium |
| **Total** | **~11 files, ~1300 LOC** | **~8 days** | |

---

## 11. Prototype Results

The prototype at `/root/maestro-guard/` already demonstrates:

- **23 new tests passing** (95 total, including 72 existing)
- **14 assertion types** parsed from markdown
- **5 Playwright integration tests** running in headless Chromium
- **Full pipeline**: markdown → `ParsedSpec` → browser execution → `SpecResult`
- **Console capture**: errors, warnings, and log messages collected from page
- **Style assertions**: computed CSS property verification
- **DOM assertions**: `querySelector`, `querySelectorAll`, property checks
- **JS assertions**: `typeof` checks, value comparisons
- **Failure detection**: assertions correctly identify when code behavior doesn't match spec

**Example output format**:
```
============================================================
  DYNAMIC SPEC EXECUTION: SaaS Analytics Dashboard
============================================================

  ✅ PASS  No console.error() calls during page load
         (120ms)
  ✅ PASS  typeof window.initDashboard == function
         (5ms)
  ❌ FAIL  document.title == Expected Title
         Actual: Wrong Title
         (3ms)
  ...
  Results: 8 passed, 1 failed (450ms total)
  Status: ❌ SOME ASSERTIONS FAILED
```

---

## 12. Quick Start for Next Developer

```bash
# The prototype is already functional. To test:
cd /root/maestro-guard

# Run all tests (including Playwright executor tests):
PLAYWRIGHT_TEST=1 python3 -m pytest tests/ -v

# Run just the parser (no browser needed):
python3 -m pytest tests/test_specs.py -v -k "TestSpecParser"

# Try parsing the demo spec:
python3 -c "
from maestro_guard.specs.parser import parse_spec, format_assertion_summary
spec = parse_spec(open('demo/exec_spec.md').read())
print(format_assertion_summary(spec))
"

# Execute the spec against clean.html:
PLAYWRIGHT_TEST=1 python3 -c "
from maestro_guard.specs.parser import parse_spec
from maestro_guard.specs.executor import SpecExecutor

html = open('demo/clean.html').read()
spec = parse_spec(open('demo/exec_spec.md').read())

executor = SpecExecutor(html)
try:
    executor.setup()
    executor.load_html()
    result = executor.run_spec(spec)
    print(executor.format_results(result))
finally:
    executor.teardown()
"
```

---

## 13. Files Created/Modified

### New files:
- `maestro_guard/specs/__init__.py` — Package init
- `maestro_guard/specs/parser.py` — Markdown spec parser (320 lines)
- `maestro_guard/specs/executor.py` — Playwright assertion executor (400 lines)
- `tests/test_specs.py` — 23 tests for parser + executor
- `demo/exec_spec.md` — Example dynamic spec

### Existing files (unchanged):
- All original 72 tests still pass
- All original source files unchanged
