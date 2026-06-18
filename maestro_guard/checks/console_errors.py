"""Check for console.error() and console.warn() calls in JS."""

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
    """Remove string literals and comments from JS code for accurate matching."""
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


def verify_console_errors(html_content: str) -> tuple[bool, str, str]:
    """Check for console.error() calls in inline <script> blocks.

    Returns:
        tuple[bool, str, str]: (passed, detail_message, fix_suggestion)
        Fails if any console.error() calls are found (console.warn is allowed as graceful degradation).
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
    cleaned = _remove_strings_and_comments(all_code)

    # Look for console.error( (but NOT console.warn - it's legitimate)
    errors = []
    pattern = re.compile(r'console\.error\s*\(')
    for match in pattern.finditer(cleaned):
        errors.append(match.group())

    if errors:
        return False, f"Found {len(errors)} console.error/warn call(s): {', '.join(errors[:10])}", "💡 Fix: Remove console.error('...') — use proper error handling"

    return True, "No console.error or console.warn calls found", ""
