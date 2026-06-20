"""
Dynamic Spec Parser — Converts markdown-based execution specs into structured assertions.

This module parses a simple markdown spec format (see demo/exec_spec.md)
into a list of Assertion objects that can be executed against a live HTML page
via Playwright or CDP.

Spec Format:
------------
The spec is markdown with sections delimited by ## headers.

# Title (optional)

## Description (optional)
Free-text description of the page being tested.

## Assertions (optional, but assertions can appear anywhere)
Assertions are defined as lines starting with ### and one of the following prefixes:

    ### DOM: `<js-expression>` == `<expected-value>`
    ### DOM: `<js-expression>` != `<expected-value>`
    ### DOM: `<js-expression>` >= `<expected-value>`
    ### DOM: `<js-expression>` matches `<regex>`

    ### JS: `<js-expression>` == `<expected-value>`
    ### JS: `typeof <name>` == "function"

    ### Console: no errors
    ### Console: no warnings
    ### Console: warn count <= 3

    ### Behavior: `<description>`
    Followed by a code block with steps.

    ### Style: `<selector>` `<property>` == `<value>`

    ### Async: page loads without uncaught errors

    ### Timeout: `<milliseconds>`

## Exemptions (optional)
Known issues that should not fail the spec.
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AssertionType(Enum):
    """Types of executable assertions."""
    DOM_EQUALS = auto()
    DOM_NOT_EQUALS = auto()
    DOM_GREATER_OR_EQ = auto()
    DOM_MATCHES = auto()
    JS_EQUALS = auto()
    JS_TYPE_OF = auto()
    CONSOLE_NO_ERRORS = auto()
    CONSOLE_NO_WARNINGS = auto()
    CONSOLE_WARN_COUNT = auto()
    BEHAVIOR = auto()
    STYLE_EQUALS = auto()
    ASYNC_NO_ERRORS = auto()
    TIMEOUT = auto()
    STRUCTURE_CHECK = auto()


@dataclass
class Assertion:
    """A single parsed assertion from the spec.

    Attributes:
        assert_type: The type of assertion.
        description: Human-readable description.
        js_expression: JavaScript expression to evaluate.
        expected: Expected value (comparison target).
        operator: Comparison operator: '==', '!=', '>=', 'matches', 'typeof'.
        selector: CSS selector (for style assertions).
        property: CSS property name (for style assertions).
        timeout_ms: Timeout in milliseconds for this assertion.
        line_number: Line number in the source spec file.
    """
    assert_type: AssertionType
    description: str = ""
    js_expression: str = ""
    expected: Any = None
    operator: str = "=="
    selector: str = ""
    property: str = ""
    timeout_ms: int = 5000
    line_number: int = 0


@dataclass
class ParsedSpec:
    """Result of parsing a spec file.

    Attributes:
        title: The spec title (from first # heading).
        description: Free-text description.
        assertions: List of parsed assertions.
        exemptions: List of known exemption descriptions.
        timeout_ms: Global timeout override (if specified).
    """
    title: str = ""
    description: str = ""
    assertions: list[Assertion] = field(default_factory=list)
    exemptions: list[str] = field(default_factory=list)
    timeout_ms: int = 5000


# ── Regex patterns ────────────────────────────────────────────────────

# Each pattern matches the FULL line (including the ### prefix)

# DOM assertion: ### DOM: `<js_expr>` == `<value>`
DOM_PATTERN = re.compile(
    r"###\s+DOM:\s*`([^`]+)`\s*(==|!=|>=|matches)\s*`([^`]+)`$"
)

# JS typeof assertion: ### JS: `typeof <name>` == `"function"`
JS_TYPEOF_PATTERN = re.compile(
    r"###\s+JS:\s*`typeof\s+([^`]+)`\s*==\s*`([^`]+)`$"
)

# JS equals assertion: ### JS: `<expr>` == `<value>`
JS_EQUALS_PATTERN = re.compile(
    r"###\s+JS:\s*`([^`]+)`\s*(==|!=|>=)\s*`([^`]+)`$"
)

# Console assertions
CONSOLE_NO_ERRORS_PATTERN = re.compile(r"###\s+Console:\s*no errors\s*$")
CONSOLE_NO_WARNINGS_PATTERN = re.compile(r"###\s+Console:\s*no warnings\s*$")
CONSOLE_WARN_PATTERN = re.compile(r"###\s+Console:\s*warn count\s*([<>=!]+)\s*(\d+)\s*$")

# Behavior assertion (has detailed steps in code block below)
BEHAVIOR_PATTERN = re.compile(r"###\s+Behavior:\s*(.+)$")

# Style assertion: ### Style: `selector` `property` == `value`
STYLE_PATTERN = re.compile(
    r"###\s+Style:\s*`([^`]+)`\s*`([^`]+)`\s*(==|!=)\s*`([^`]+)`$"
)

# Async assertion
ASYNC_PATTERN = re.compile(r"###\s+Async:\s*(.+)$")

# Timeout
TIMEOUT_PATTERN = re.compile(r"###\s+Timeout:\s*(\d+)\s*ms\s*$")

# Structure check (templated description, not executable)
STRUCTURE_PATTERN = re.compile(r"###\s+Structure$")


def _add_assertion(spec: ParsedSpec, assertion: Assertion) -> None:
    """Add an assertion to the spec, applying timeout."""
    assertion.timeout_ms = spec.timeout_ms
    spec.assertions.append(assertion)


def parse_spec(text: str, default_timeout: int = 5000) -> ParsedSpec:
    """Parse a markdown spec string into a ParsedSpec object.

    The parser works in two passes:
    1. Extract title, description, exemptions, and timeout from structured sections.
    2. Scan for `### ` lines that match assertion patterns (across the entire document).

    Args:
        text: The raw markdown spec content.
        default_timeout: Default timeout in ms for assertions.

    Returns:
        ParsedSpec with all parsed assertions.
    """
    spec = ParsedSpec(timeout_ms=default_timeout)
    lines = text.split("\n")

    # State for behavior blocks
    in_behavior_block = False
    behavior_steps: list[str] = []
    behavior_description = ""

    # Section tracking for description/exemptions
    current_section = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        line_no = i + 1

        # ── Track sections ──
        if stripped.startswith("## "):
            section_name = stripped[3:].strip().lower()
            current_section = section_name
            continue

        # ── Top-level title (only first #) ──
        if stripped.startswith("# ") and not spec.title:
            spec.title = stripped[2:].strip()
            continue

        # ── Description section ──
        if current_section == "description":
            if not stripped.startswith("#"):
                spec.description += stripped + " "
            continue

        # ── Exemptions section ──
        if current_section == "exemptions":
            if stripped.startswith("- ") or stripped.startswith("* "):
                spec.exemptions.append(stripped.lstrip("- *").strip())
            continue

        # ── Behavior code block tracking ──
        if stripped.startswith("```"):
            if in_behavior_block:
                # End of behavior block
                _add_assertion(spec, Assertion(
                    assert_type=AssertionType.BEHAVIOR,
                    description=behavior_description,
                    js_expression="\n".join(behavior_steps),
                    line_number=line_no,
                ))
                behavior_steps = []
                behavior_description = ""
                in_behavior_block = False
            else:
                in_behavior_block = True
            continue

        if in_behavior_block:
            behavior_steps.append(stripped)
            continue

        # ── Assertion matching (any ### line) ──
        if not stripped.startswith("### "):
            continue

        # Try each pattern in order of specificity

        # 1. Timeout
        m = TIMEOUT_PATTERN.match(stripped)
        if m:
            spec.timeout_ms = int(m.group(1))
            continue

        # 2. Style
        m = STYLE_PATTERN.match(stripped)
        if m:
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.STYLE_EQUALS,
                description=stripped[:80],
                selector=m.group(1),
                property=m.group(2),
                expected=m.group(4),
                operator=m.group(3),
                line_number=line_no,
            ))
            continue

        # 3. DOM assertions
        m = DOM_PATTERN.match(stripped)
        if m:
            op = m.group(2)
            atype = {
                "matches": AssertionType.DOM_MATCHES,
                "!=": AssertionType.DOM_NOT_EQUALS,
                ">=": AssertionType.DOM_GREATER_OR_EQ,
                "==": AssertionType.DOM_EQUALS,
            }[op]
            _add_assertion(spec, Assertion(
                assert_type=atype,
                description=stripped[:80],
                js_expression=m.group(1),
                expected=m.group(3),
                operator=op,
                line_number=line_no,
            ))
            continue

        # 4. JS typeof
        m = JS_TYPEOF_PATTERN.match(stripped)
        if m:
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.JS_TYPE_OF,
                description=stripped[:80],
                js_expression=m.group(1),
                expected=m.group(2),
                operator="typeof",
                line_number=line_no,
            ))
            continue

        # 5. JS equals
        m = JS_EQUALS_PATTERN.match(stripped)
        if m:
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.JS_EQUALS,
                description=stripped[:80],
                js_expression=m.group(1),
                expected=m.group(3),
                operator=m.group(2),
                line_number=line_no,
            ))
            continue

        # 6. Console assertions
        if CONSOLE_NO_ERRORS_PATTERN.match(stripped):
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.CONSOLE_NO_ERRORS,
                description="No console.error() calls during page load",
                line_number=line_no,
            ))
            continue

        if CONSOLE_NO_WARNINGS_PATTERN.match(stripped):
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.CONSOLE_NO_WARNINGS,
                description="No console.warn() calls during page load",
                line_number=line_no,
            ))
            continue

        m = CONSOLE_WARN_PATTERN.match(stripped)
        if m:
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.CONSOLE_WARN_COUNT,
                description=stripped,
                operator=m.group(1),
                expected=int(m.group(2)),
                line_number=line_no,
            ))
            continue

        # 7. Behavior (description only — steps follow in code block)
        m = BEHAVIOR_PATTERN.match(stripped)
        if m:
            behavior_description = m.group(1).strip()
            continue

        # 8. Async
        m = ASYNC_PATTERN.match(stripped)
        if m:
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.ASYNC_NO_ERRORS,
                description=m.group(1).strip(),
                line_number=line_no,
            ))
            continue

        # 9. Structure
        if STRUCTURE_PATTERN.match(stripped):
            _add_assertion(spec, Assertion(
                assert_type=AssertionType.STRUCTURE_CHECK,
                description=stripped,
                line_number=line_no,
            ))
            continue

    return spec


def assertion_to_dict(assertion: Assertion) -> dict[str, Any]:
    """Convert an Assertion to a JSON-serializable dict."""
    return {
        "type": assertion.assert_type.name,
        "description": assertion.description,
        "js_expression": assertion.js_expression,
        "expected": str(assertion.expected) if assertion.expected is not None else None,
        "operator": assertion.operator,
        "selector": assertion.selector,
        "property": assertion.property,
        "timeout_ms": assertion.timeout_ms,
    }


def spec_to_dict(spec: ParsedSpec) -> dict[str, Any]:
    """Convert a ParsedSpec to a JSON-serializable dict."""
    return {
        "title": spec.title,
        "description": spec.description.strip(),
        "assertion_count": len(spec.assertions),
        "timeout_ms": spec.timeout_ms,
        "exemptions": spec.exemptions,
        "assertions": [assertion_to_dict(a) for a in spec.assertions],
        "assertion_types": list({a.assert_type.name for a in spec.assertions}),
    }


def format_assertion_summary(spec: ParsedSpec) -> str:
    """Return a human-readable summary of the parsed spec."""
    lines = []
    lines.append(f"Spec: {spec.title}")
    if spec.description:
        lines.append(f"Description: {spec.description.strip()[:100]}...")
    lines.append(f"Assertions: {len(spec.assertions)}")
    lines.append(f"Global timeout: {spec.timeout_ms}ms")
    if spec.exemptions:
        lines.append(f"Exemptions: {len(spec.exemptions)}")

    # Group by type
    from collections import Counter
    type_counts = Counter(a.assert_type.name for a in spec.assertions)
    lines.append("Breakdown:")
    for atype, count in sorted(type_counts.items()):
        lines.append(f"  - {atype}: {count}")

    return "\n".join(lines)
