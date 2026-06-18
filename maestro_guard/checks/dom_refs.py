"""Check that DOM references (getElementById) match actual HTML elements."""

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


def _find_all_get_element_by_id(js_code: str) -> set[str]:
    """Find all id references in getElementById('...') calls.

    Handles: getElementById('id'), getElementById("id") but NOT
    getElementById(idVar) (variable references).
    """
    ids = set()
    # Match getElementById('...') or getElementById("...")
    pattern = re.compile(
        r"""getElementById\s*\(\s*(["'])([^"']+)\1\s*\)""",
    )
    for match in pattern.finditer(js_code):
        ids.add(match.group(2))
    return ids


def _find_all_html_ids(html_content: str) -> set[str]:
    """Find all id attributes in HTML elements."""
    ids = set()
    # Match id="..." or id='...' with various quoting
    pattern = re.compile(
        r"""\bid\s*=\s*(["'])(.+?)\1""",
        re.IGNORECASE,
    )
    for match in pattern.finditer(html_content):
        ids.add(match.group(2))
    return ids


def verify_dom_refs(html_content: str) -> tuple[bool, str, str]:
    """Verify that all getElementById('...') references match existing HTML id attributes.

    Extracts all getElementById('id') calls from inline JS and checks
    that matching id="id" exists in the HTML.

    Returns:
        tuple[bool, str, str]: (passed, detail_message, fix_suggestion)
        Fails if any referenced id does not exist in the HTML.
    """
    if not html_content:
        return False, "No HTML content provided", ""

    try:
        script_blocks = _extract_script_blocks(html_content)
        all_code = '\n'.join(script_blocks)

        # Find all referenced IDs in JS
        js_ids = _find_all_get_element_by_id(all_code)

        if not js_ids:
            return True, "No getElementById() calls found (nothing to verify)", ""

        # Find all defined IDs in HTML
        html_ids = _find_all_html_ids(html_content)

        # Check for missing IDs
        missing_ids = sorted(js_ids - html_ids)

        if missing_ids:
            detail = (
                f"getElementById() references not found in HTML: "
                f"{', '.join(missing_ids)}"
            )
            suggestion = (
                f"💡 Fix: Add <div id=\"{missing_ids[0]}\"> to your HTML"
                + (f" and other missing id(s)" if len(missing_ids) > 1 else "")
            )
            return False, detail, suggestion

        return True, f"All {len(js_ids)} getElementById() reference(s) match existing HTML id(s)", ""

    except Exception as e:
        return False, f"Error verifying DOM refs: {e}", ""
