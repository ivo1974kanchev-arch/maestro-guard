"""Check that JS function handlers are properly defined (no empty stubs)."""

import re


def _extract_script_blocks(html_content: str) -> list[str]:
    """Extract all inline <script> blocks from HTML content."""
    blocks = []
    pattern = re.compile(
        r'<script[^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_content):
        code = match.group(1).strip()
        if code:
            blocks.append(code)
    return blocks


def _remove_strings_and_comments(code: str) -> str:
    """Remove string literals and comments from JS code."""
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
                result.append(' ')
                i = j + 2
                continue

        # Handle strings
        if ch in ('"', "'", '`') and not in_string:
            in_string = True
            string_char = ch
            result.append(' ')
            i += 1
            continue

        if in_string:
            if ch == '\\':
                i += 2
                continue
            if ch == string_char:
                in_string = False
                string_char = None
                result.append(' ')
                i += 1
                continue
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _find_all_functions(code: str) -> dict[str, tuple[str, int, int]]:
    """Find all function declarations and return dict of func_name -> (body, start, end)."""
    functions = {}

    # Remove strings and comments first for accurate matching
    cleaned = _remove_strings_and_comments(code)

    # Match function declarations: function name() or function name(params)
    pattern = re.compile(r'function\s+([a-zA-Z_$][\w$]*)\s*\(([^)]*)\)\s*\{')
    for match in pattern.finditer(cleaned):
        name = match.group(1)
        start = match.end() - 1  # Position of the opening brace
        # Find matching closing brace by counting nesting
        brace_count = 1
        pos = start + 1
        while pos < len(cleaned) and brace_count > 0:
            if cleaned[pos] == '{':
                brace_count += 1
            elif cleaned[pos] == '}':
                brace_count -= 1
            pos += 1
        end = pos
        body_start = match.end()
        # Get the actual body from original code (approximately)
        body = code[body_start:end - 1].strip()
        functions[name] = (body, body_start, end - 1)

    return functions


def _find_all_calls(code: str) -> dict[str, list[int]]:
    """Find all function call expressions in code.

    Looks for identifier( pattern — these are function calls.
    Returns dict of func_name -> list of positions.
    """
    calls: dict[str, list[int]] = {}
    cleaned = _remove_strings_and_comments(code)

    # Match potential function calls: identifier(
    pattern = re.compile(r'([a-zA-Z_$][\w$]*)\s*\(')
    for match in pattern.finditer(cleaned):
        name = match.group(1)
        # Skip keywords that take parens
        if name in ('if', 'for', 'while', 'do', 'switch', 'catch', 'typeof',
                     'instanceof', 'return', 'throw', 'delete', 'void', 'new',
                     'function', 'var', 'let', 'const', 'class', 'import',
                     'export', 'try', 'yield', 'await', 'with', 'in', 'of'):
            continue
        if name not in calls:
            calls[name] = []
        calls[name].append(match.start())

    return calls


def verify_handlers(html_content: str) -> tuple[bool, str, str]:
    """Verify that all JS function handlers are properly defined (no empty stubs).

    Checks:
    - Find all function declarations
    - Check for empty function bodies (function foo() { })
    - Check for functions that are defined but called with different casing

    Returns:
        tuple[bool, str, str]: (passed, detail_message, fix_suggestion)
        Fails if any empty stubs are found.
    """
    if not html_content:
        return False, "No HTML content provided", ""

    try:
        script_blocks = _extract_script_blocks(html_content)
    except Exception as e:
        return False, f"Error extracting script blocks: {e}", ""

    if not script_blocks:
        return True, "No script blocks — nothing to verify", ""

    all_code = '\n'.join(script_blocks)
    functions = _find_all_functions(all_code)

    if not functions:
        return True, "No function declarations found to verify (no empty stubs)", ""

    empty_functions = []
    defined_funcs_lower = {}
    for name, (body, _, _) in functions.items():
        name_lower = name.lower()
        if name_lower not in defined_funcs_lower:
            defined_funcs_lower[name_lower] = []
        defined_funcs_lower[name_lower].append(name)
        stripped_body = body.strip()
        if not stripped_body or stripped_body == '':
            empty_functions.append(name)

    details = []
    if empty_functions:
        detail = f"Empty function stubs found: {', '.join(sorted(empty_functions))}"
        details.append(detail)

    calls = _find_all_calls(all_code)
    casing_issues = []
    for call_name, call_positions in calls.items():
        call_lower = call_name.lower()
        if call_lower in defined_funcs_lower:
            if call_name not in defined_funcs_lower[call_lower]:
                defined_names = defined_funcs_lower[call_lower]
                casing_issues.append(
                    f"'{call_name}' (called) != defined as {defined_names}"
                )

    if casing_issues:
        details.append(f"Casing mismatch: {'; '.join(casing_issues[:5])}")

    if not details:
        return True, f"All {len(functions)} function(s) have non-empty bodies", ""

    combined = " | ".join(details)
    suggestion = "💡 Fix: Replace empty function body with real implementation"
    return False, combined, suggestion
