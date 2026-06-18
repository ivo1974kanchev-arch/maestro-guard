"""Check for basic JS syntax issues in inline <script> blocks from HTML."""

import re
from html.parser import HTMLParser


class _ScriptExtractor(HTMLParser):
    """Extract inline <script> block content using proper HTML parsing."""

    def __init__(self):
        super().__init__()
        self._blocks: list[str] = []
        self._in_script = False
        self._current = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            # Check if it has a src attribute (external script)
            has_src = any(name.lower() == "src" for name, _ in attrs)
            if not has_src:
                self._in_script = True
                self._current = ""

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            code = self._current.strip()
            if code:
                self._blocks.append(code)
            self._in_script = False
            self._current = ""

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._current += data

    def get_blocks(self) -> list[str]:
        return self._blocks


def _extract_script_blocks(html_content: str) -> list[str]:
    """Extract all inline <script> blocks from HTML content using proper parsing.

    Uses Python's stdlib html.parser to correctly handle edge cases
    like </script> inside JS string literals.
    """
    extractor = _ScriptExtractor()
    extractor.feed(html_content)
    extractor.close()
    return extractor.get_blocks()


def _check_balanced(code: str, open_char: str, close_char: str, name: str) -> tuple[bool, str]:
    """Check that brackets/parens/braces are balanced."""
    count = 0
    in_string = False
    string_char = None
    i = 0
    n = len(code)

    while i < n:
        ch = code[i]

        # Handle string literals (skip content inside strings)
        if ch in ('"', "'", '`') and not in_string:
            in_string = True
            string_char = ch
            i += 1
            continue
        if in_string:
            if ch == '\\':
                i += 2  # Skip escaped character
                continue
            if ch == string_char:
                in_string = False
                string_char = None
            i += 1
            continue

        # Handle comments (skip content inside comments)
        if ch == '/' and i + 1 < n:
            if code[i + 1] == '/':
                # Single-line comment: skip to end of line
                end = code.find('\n', i)
                if end == -1:
                    break  # rest of file is comment
                i = end + 1
                continue
            if code[i + 1] == '*':
                # Multi-line comment: skip to */
                end = code.find('*/', i + 2)
                if end == -1:
                    return False, f"Unterminated multi-line comment in {name} check"
                i = end + 2
                continue

        if ch == open_char:
            count += 1
        elif ch == close_char:
            count -= 1
            if count < 0:
                return False, f"Unmatched closing {close_char} in {name}"

        i += 1

    if count != 0:
        direction = "opening" if count > 0 else "closing"
        return False, f"Unmatched {direction} {name}: {abs(count)} unclosed"
    return True, ""


def _check_strings(code: str) -> tuple[bool, str]:
    """Check for broken/unterminated string literals."""
    in_single = False
    in_double = False
    in_backtick = False
    escape = False

    for i, ch in enumerate(code):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue

        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif ch == '`' and not in_single and not in_double:
            in_backtick = not in_backtick

    if in_single:
        return False, "Unterminated single-quoted string literal"
    if in_double:
        return False, "Unterminated double-quoted string literal"
    if in_backtick:
        return False, "Unterminated template literal (backtick string)"
    return True, ""


def _check_missing_semicolons(code: str) -> tuple[bool, str]:
    """A basic heuristic check for missing semicolons between statements.

    This is a lightweight heuristic, not a full parser. It looks for places
    where a new statement likely starts without a preceding semicolon.
    """
    # Remove strings and comments from consideration
    cleaned = _strip_strings_and_comments(code)

    # Heuristic: check for lines that look like they start a statement
    # but the previous line doesn't end with a semicolon, opening brace, or colon
    lines = cleaned.split('\n')
    statement_starters = {
        'return', 'throw', 'break', 'continue', 'var', 'let', 'const',
        'function', 'if', 'for', 'while', 'do', 'switch', 'try', 'class',
        'import', 'export', 'this', 'new', 'delete', 'typeof', 'void',
        'yield', 'await',
    }

    issues = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Skip comment-only lines (already stripped, but check for remnants)
        if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('<!--'):
            continue

        # Check if this line starts with a statement keyword
        first_word = stripped.split()[0] if stripped.split() else ''
        first_word = first_word.rstrip('(')

        if first_word in statement_starters and i > 0:
            prev_line = lines[i - 1].strip()
            # Skip empty/comment prev lines going backwards
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0:
                prev_line = lines[j].strip()
                # If previous line doesn't end with statement-ending chars,
                # but skip HTML comments and other false positives
                if prev_line and not prev_line.endswith(';') and not prev_line.endswith('{') and not prev_line.endswith('}') and not prev_line.endswith(':'):
                    if not prev_line.endswith(',') and not prev_line.endswith('(') and not prev_line.endswith('['):
                        if not prev_line.startswith('<!--'):
                            issues.append(f"Line {i + 1}: Possible missing semicolon before '{stripped[:40]}'")
    if issues:
        return False, "Missing semicolons detected: " + "; ".join(issues[:5])
    return True, ""


def _strip_strings_and_comments(code: str) -> str:
    """Remove string literals and comments from code for heuristic analysis."""
    result = []
    i = 0
    in_string = False
    string_char = None

    while i < len(code):
        ch = code[i]

        # Handle comments
        if not in_string and ch == '/' and i + 1 < len(code):
            if code[i + 1] == '/':
                j = code.find('\n', i)
                if j == -1:
                    break
                result.append('\n')
                i = j + 1
                continue
            if code[i + 1] == '*':
                j = code.find('*/', i + 2)
                if j == -1:
                    break
                result.append(' ' * (j - i + 2))
                i = j + 2
                continue

        # Handle strings
        if ch in ('"', "'", '`') and not in_string:
            in_string = True
            string_char = ch
            result.append('"')  # Replace string with a placeholder
            i += 1
            continue

        if in_string:
            if ch == '\\':
                i += 2  # Skip escaped char
                continue
            if ch == string_char:
                in_string = False
                string_char = None
                result.append('"')
                i += 1
                continue
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def verify_js_syntax(html_content: str) -> tuple[bool, str, str]:
    """Extract inline <script> blocks from HTML and verify basic JS syntax.

    Checks performed:
    - Balanced braces {}
    - Balanced parentheses ()
    - Balanced brackets []
    - Unterminated string literals
    - Missing semicolons between statements (heuristic)

    Returns:
        tuple[bool, str, str]: (passed, detail_message, fix_suggestion)
    """
    if not html_content:
        return False, "No HTML content provided", ""

    try:
        script_blocks = _extract_script_blocks(html_content)
    except Exception as e:
        return False, f"Error extracting script blocks: {e}", ""

    if not script_blocks:
        return True, "No script blocks — nothing to verify", ""

    try:
        all_details = []
        for idx, code in enumerate(script_blocks):
            block_label = f"<script> block {idx + 1}" if len(script_blocks) > 1 else "<script> block"

            # Check balanced braces
            ok_braces, msg_braces = _check_balanced(code, '{', '}', "braces {}")
            if not ok_braces:
                all_details.append(f"{block_label}: {msg_braces}")

            # Check balanced parens
            ok_parens, msg_parens = _check_balanced(code, '(', ')', "parentheses ()")
            if not ok_parens:
                all_details.append(f"{block_label}: {msg_parens}")

            # Check balanced brackets
            ok_brackets, msg_brackets = _check_balanced(code, '[', ']', "brackets []")
            if not ok_brackets:
                all_details.append(f"{block_label}: {msg_brackets}")

            # Check string literals
            ok_strings, msg_strings = _check_strings(code)
            if not ok_strings:
                all_details.append(f"{block_label}: {msg_strings}")

            # Heuristic: missing semicolons
            ok_semicolons, msg_semicolons = _check_missing_semicolons(code)
            if not ok_semicolons:
                all_details.append(f"{block_label}: {msg_semicolons}")

        if all_details:
            return False, " | ".join(all_details), "💡 Fix: Check for missing } or ) in your JavaScript"

        return True, f"All {len(script_blocks)} <script> block(s) pass basic JS syntax checks", ""

    except Exception as e:
        return False, f"Error parsing JS syntax: {e}", ""
