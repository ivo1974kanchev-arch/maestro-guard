"""Basic spec fulfillment check via keyword matching."""

import re
import string


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


def _extract_visible_text(html_content: str) -> str:
    """Extract visible/meaningful text from HTML (stripping tags)."""
    # Remove script and style blocks
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    # Remove HTML tags
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    # Decode common entities
    cleaned = cleaned.replace('&nbsp;', ' ').replace('&amp;', '&')
    cleaned = cleaned.replace('&lt;', '<').replace('&gt;', '>')
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text.

    Removes common stop words and punctuation, returns lowercase keywords.
    """
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'has', 'have', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'shall', 'can', 'not',
        'no', 'nor', 'this', 'that', 'these', 'those', 'it', 'its', 'it\'s',
        'i', 'you', 'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us',
        'them', 'my', 'your', 'his', 'their', 'our', 'who', 'what', 'where',
        'when', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
        'most', 'some', 'any', 'none', 'one', 'two', 'other', 'such', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'just', 'because', 'if',
        'then', 'else', 'also', 'about', 'into', 'over', 'after', 'before',
        'between', 'under', 'above', 'below', 'up', 'down', 'out', 'off',
        'again', 'further', 'once', 'here', 'there', 'which', 'while',
        'please', 'click', 'button', 'page',
    }

    # Remove punctuation
    translator = str.maketrans('', '', string.punctuation)
    cleaned = text.translate(translator)
    # Split spec into keywords
    spec_words = set()
    for word in text.lower().split():
        strip_chars = ",.:;!?()[]{}'\"" + chr(0x22) + "'\""
        word = word.strip(strip_chars)
        # Skip hex codes, numbers, and single chars
        if word and len(word) > 2 and not word.startswith('#') and not word.startswith('0x'):
            try:
                int(word.replace('px', '').replace('ms', '').replace('em', '').replace('%', '').replace('s', ''))
                continue  # skip numeric values
            except ValueError:
                pass
            # Skip hex color codes (6 chars, hex digits)
            if len(word) == 6 and all(c in '0123456789abcdef' for c in word):
                continue
            spec_words.add(word)

    return spec_words


def _extract_identifiers(js_code: str) -> set[str]:
    """Extract function names, variable names, and string literals from JS code."""
    identifiers = set()

    # Function names: function foo(
    for match in re.finditer(r'function\s+([a-zA-Z_$][\w$]*)', js_code):
        identifiers.add(match.group(1).lower())

    # Variable/const/let assignments: var foo =, let foo =, const foo =
    for match in re.finditer(r'(?:var|let|const)\s+([a-zA-Z_$][\w$]*)', js_code):
        identifiers.add(match.group(1).lower())

    # String literals: '...' and "..."
    for match in re.finditer(r"""(["'])([^"']+)\1""", js_code):
        for word in match.group(2).lower().split():
            word = word.strip(string.punctuation)
            if word and len(word) > 2:
                identifiers.add(word)

    return identifiers


def verify_fulfillment(html_content: str, spec_text: str) -> tuple[bool, str, str]:
    """Basic spec fulfillment check using lightweight keyword matching.

    Extracts keywords from the spec text and checks whether those keywords
    appear in:
    - HTML visible text (headings, labels, paragraphs)
    - JS function/variable names
    - JS string literals and comments

    Returns:
        tuple[bool, str, str]: (passed, detail_message, fix_suggestion)
    """
    if not html_content:
        return False, "No HTML content provided", ""
    if not spec_text:
        return False, "No spec text provided for fulfillment checking", ""

    try:
        # Extract keywords from spec
        spec_keywords = _extract_keywords(spec_text)

        if not spec_keywords:
            return True, "No meaningful keywords found in spec (nothing to verify)", ""

        # Extract content from HTML
        visible_text = _extract_visible_text(html_content)
        html_keywords = _extract_keywords(visible_text)

        # Extract identifiers from JS
        script_blocks = _extract_script_blocks(html_content)
        all_js = '\n'.join(script_blocks)
        js_identifiers = _extract_identifiers(all_js)

        # Combine all content sources
        content_keywords = html_keywords | js_identifiers

        # Check which spec keywords are found in the content
        found_keywords = spec_keywords & content_keywords
        missing_keywords = spec_keywords - content_keywords

        # Calculate coverage ratio
        total = len(spec_keywords)
        found_count = len(found_keywords)

        if total == 0:
            return True, "No keywords to verify", ""

        coverage_pct = (found_count / total) * 100

        # Threshold: at least 15% of spec keywords should be found
        # (lightweight check, not an LLM)
        threshold = 15

        if coverage_pct >= threshold:
            if missing_keywords:
                missing_sample = sorted(missing_keywords)[:10]
                detail = (
                    f"Spec fulfillment: {found_count}/{total} keywords matched "
                    f"({coverage_pct:.0f}%). Missing: {', '.join(missing_sample)}"
                    + ("..." if len(missing_keywords) > 10 else "")
                )
                return True, detail, ""
            return True, (
                f"Spec fulfillment: All {total} spec keywords found in content"
            ), ""

        # Below threshold
        missing_sample = sorted(missing_keywords)[:15]
        found_sample = sorted(found_keywords)[:10]
        detail = (
            f"Spec fulfillment: only {found_count}/{total} keywords matched "
            f"({coverage_pct:.0f}%; threshold: {threshold:.0f}%). "
            f"Missing: {', '.join(missing_sample)}"
            + ("..." if len(missing_keywords) > 15 else "")
            + f". Found: {', '.join(found_sample)}"
            + ("..." if len(found_keywords) > 10 else "")
        )
        return False, detail, ""

    except Exception as e:
        return False, f"Error verifying spec fulfillment: {e}", ""
