"""ReviewOrchestrator — Multi-perspective review system for Maestro Guard.

Runs HTML/JS content through 5 expert reviewer roles using heuristic analysis
(no API keys required). Produces structured review reports.
"""

import json
import re
from typing import Optional

from maestro_guard.review.prompts import ROLES
from maestro_guard.review.aggregator import ScoreAggregator
from maestro_guard.review.improver import ContentImprover


class ReviewReport:
    """Structured output from a multi-perspective review.

    Attributes:
        reviews: List of individual reviewer results.
        aggregator: ScoreAggregator with combined scores.
        improver: ContentImprover with improvement analysis.
    """

    def __init__(self, reviews: list[dict], aggregator: ScoreAggregator,
                 improver: ContentImprover):
        self.reviews = reviews
        self.aggregator = aggregator
        self.improver = improver

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return {
            "overall_score": self.aggregator.calculate(),
            "all_passed": self.aggregator.all_passed,
            "total_reviewers": len(self.reviews),
            "reviews": self.reviews,
            "verdict": "PASS" if self.aggregator.all_passed else "FAIL",
            "improvement_analysis": self.improver.analyze_summary(),
        }

    def to_json(self) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=2)

    def summary(self) -> str:
        """Return a human-readable summary string."""
        lines = []
        lines.append("=" * 60)
        lines.append("  MULTI-PERSPECTIVE REVIEW REPORT")
        lines.append("=" * 60)
        lines.append("")

        for review in self.reviews:
            role_name = review.get("role_name", "Unknown")
            score = review.get("score", 0)
            verdict = "✅ PASS" if review.get("verdict") == "pass" else "❌ FAIL"
            lines.append(f"  {verdict}  {role_name}  ({score}/10)")
            issues = review.get("issues", [])
            if issues:
                for issue in issues:
                    lines.append(f"       ⚠ {issue}")
            suggestions = review.get("suggestions", [])
            if suggestions:
                for sug in suggestions:
                    lines.append(f"       💡 {sug}")
            lines.append("")

        lines.append("  " + "─" * 39)
        lines.append("")
        overall = self.aggregator.calculate()
        passed = self.aggregator.all_passed
        status = "✅ ALL REVIEWS PASSED" if passed else "❌ SOME REVIEWS FAILED"
        lines.append(f"  Overall Score: {overall:.1f}/100")
        lines.append(f"  Status: {status}")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


class ReviewOrchestrator:
    """Orchestrates multi-perspective review of HTML/JS content.

    Runs content through multiple reviewer roles using built-in heuristic
    analysis. No API keys required.

    Args:
        html_content: The HTML/JS content to review.
        roles: List of role keys to use (default: all 5 roles).
    """

    def __init__(self, html_content: str, roles: Optional[list[str]] = None):
        self.html_content = html_content
        self.aggregator = ScoreAggregator()
        self.improver = ContentImprover()

        if roles is None:
            self.role_keys = list(ROLES.keys())
        else:
            # Validate roles
            valid_roles = set(ROLES.keys())
            for role in roles:
                if role not in valid_roles:
                    raise ValueError(f"Unknown role: '{role}'. Valid roles: {sorted(valid_roles)}")
            self.role_keys = roles

    def run_all(self) -> ReviewReport:
        """Run all reviewers and produce a ReviewReport."""
        reviews = []

        for role_key in self.role_keys:
            role_config = ROLES[role_key]
            review_result = self._run_single_review(role_key, role_config)
            reviews.append(review_result)

            self.aggregator.add_review(
                role_name=role_config["name"],
                score=review_result["score"],
                issues=review_result["issues"],
                suggestions=review_result["suggestions"],
                verdict=review_result["verdict"],
                weight=role_config.get("weight", 20),
            )

        self.improver.analyze(self.html_content, reviews)

        return ReviewReport(
            reviews=reviews,
            aggregator=self.aggregator,
            improver=self.improver,
        )

    def _run_single_review(self, role_key: str, role_config: dict) -> dict:
        """Run a single reviewer role using heuristic analysis."""
        content = self.html_content
        issues: list[str] = []
        suggestions: list[str] = []

        if role_key == "security":
            issues, suggestions = self._analyze_security(content)
        elif role_key == "code_quality":
            issues, suggestions = self._analyze_code_quality(content)
        elif role_key == "ux":
            issues, suggestions = self._analyze_ux(content)
        elif role_key == "completeness":
            issues, suggestions = self._analyze_completeness(content)
        elif role_key == "business":
            issues, suggestions = self._analyze_business(content)

        # Calculate severity-weighted score: start at 10
        # critical=-3pts, major=-2pts, minor=-1pt (min 0)
        severity_points = 0
        for issue in issues:
            sev = ContentImprover()._classify_severity(issue, role_key)
            if sev == ContentImprover.SEVERITY_CRITICAL:
                severity_points -= 3
            elif sev == ContentImprover.SEVERITY_MAJOR:
                severity_points -= 2
            else:
                severity_points -= 1
        score = max(0, 10 + severity_points)
        verdict = "pass" if score >= 5 else "fail"

        return {
            "role": role_key,
            "role_name": role_config["name"],
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "verdict": verdict,
            "weight": role_config.get("weight", 20),
        }

    # ── Heuristic analysis methods ────────────────────────────────────

    def _analyze_security(self, content: str) -> tuple[list[str], list[str]]:
        """Security heuristic analysis — XSS, injection, data exposure."""
        issues: list[str] = []
        suggestions: list[str] = []
        lower = content.lower()

        # Check for inline event handlers (XSS vector)
        inline_handlers = [
            "onclick", "onload", "onerror", "onmouseover", "onfocus",
            "onchange", "onsubmit", "onkeydown", "onkeypress", "onkeyup",
            "onblur", "onunload", "onresize", "onscroll",
        ]
        found_handlers = [h for h in inline_handlers if h in lower]
        if found_handlers:
            issues.append(f"Inline event handlers found: {', '.join(found_handlers[:5])} — potential XSS vector")
            suggestions.append("Move event handlers to JS using addEventListener() instead of inline attributes")

        # Check for eval()
        if "eval(" in content and "eval(" not in content.replace("'", "").replace('"', ''):
            # Only flag if it looks like actual eval use (not in a string)
            if _looks_like_real_call(content, "eval"):
                issues.append("Use of eval() detected — allows arbitrary code execution")
                suggestions.append("Replace eval() with safer alternatives like JSON.parse() or Function constructor")

        # Check for innerHTML assignments (XSS vector)
        inner_html_patterns = [".innerhtml =", ".innerhtml=", ".innerhtml  ="]
        if any(p in lower for p in inner_html_patterns):
            issues.append("Use of innerHTML detected — potential XSS vulnerability")
            suggestions.append("Use textContent or createElement() + appendChild() instead of innerHTML")

        # Check for document.write
        if "document.write" in lower:
            issues.append("Use of document.write() detected — can overwrite entire page")
            suggestions.append("Replace document.write() with DOM manipulation methods")

        # Check for data URIs in scripts
        if "data:text/javascript" in lower or "data:text/html" in lower:
            issues.append("Data URIs in script context detected — potential XSS vector")
            suggestions.append("Avoid data URIs; serve scripts from external files instead")

        # Check for missing CSP meta tag
        if 'http-equiv="content-security-policy"' not in lower and 'http-equiv="Content-Security-Policy"' not in lower:
            issues.append("No Content-Security-Policy meta tag found")
            suggestions.append('Add a Content-Security-Policy meta tag: <meta http-equiv="Content-Security-Policy" content="default-src \'self\';">')

        # Check for localStorage/sessionStorage with sensitive data patterns
        storage_refs = ["localstorage", "sessionstorage"]
        if any(s in lower for s in storage_refs):
            issues.append("Client-side storage detected — ensure no sensitive data is stored")
            suggestions.append("Avoid storing tokens, passwords, or PII in localStorage/sessionStorage")

        # Check for fetch() without .catch() — unhandled promise rejection
        if re.search(r'\.fetch\s*\(', content) and not re.search(r'\.fetch\s*\([^)]*\)\s*\.\s*catch\s*\(', content, re.DOTALL):
            # Only flag if there's a .fetch( but no .catch( in the content
            if '.fetch(' in content and '.catch(' not in content:
                issues.append("fetch() detected without .catch() — unhandled promise rejection")
                suggestions.append("Add .catch() to handle fetch failures: fetch(url).then(...).catch(err => ...)")

        # Check for addEventListener without removeEventListener — memory leaks
        add_count = len(re.findall(r'\.addEventListener\s*\(', content))
        remove_count = len(re.findall(r'\.removeEventListener\s*\(', content))
        if add_count > remove_count:
            issues.append(f"addEventListener() called {add_count}x but removeEventListener() only {remove_count}x — potential memory leak")
            suggestions.append("Always pair addEventListener() with removeEventListener() in cleanup/teardown")

        # Check for JSON.parse() without try/catch — crash on malformed data
        if 'JSON.parse(' in content or 'json.parse(' in lower:
            # Check if there's a try block anywhere near the JSON.parse call
            has_protection = False
            for match in re.finditer(r'JSON\s*\.\s*parse\s*\(', content, re.IGNORECASE):
                start = max(0, match.start() - 200)
                context = content[start:match.end()].lower()
                if 'try' in context or 'catch' in context:
                    has_protection = True
                    break
            if not has_protection:
                issues.append("JSON.parse() detected without try/catch — can crash on malformed JSON")
                suggestions.append("Wrap JSON.parse() in try/catch: try { JSON.parse(data) } catch(e) { ... }")

        # Check for setInterval without clearInterval — resource leak
        interval_count = len(re.findall(r'setInterval\s*\(', content))
        clear_count = len(re.findall(r'clearInterval\s*\(', content))
        if interval_count > clear_count:
            issues.append(f"setInterval() called {interval_count}x but clearInterval() only {clear_count}x — potential resource leak")
            suggestions.append("Always store setInterval() return value and call clearInterval() in cleanup")

        # Check for prototype pollution patterns
        proto_patterns = [
            r'__proto__\s*=',
            r'__proto__\s*:',
            r'prototype\s*\[',
            r'Object\.assign\s*\([^)]*__proto__',
            r'Object\.setPrototypeOf\s*\(',
            r'\.constructor\.prototype',
        ]
        for pattern in proto_patterns:
            if re.search(pattern, content):
                issues.append("Prototype pollution pattern detected — can lead to object tampering")
                suggestions.append("Avoid modifying Object.prototype directly; use Map/WeakMap for dynamic properties")
                break

        return issues, suggestions

    def _analyze_code_quality(self, content: str) -> tuple[list[str], list[str]]:
        """Code quality heuristic analysis — patterns, edge cases, performance."""
        issues: list[str] = []
        suggestions: list[str] = []
        lower = content.lower()
        lines = content.split("\n")

        # Check for commented-out code
        comment_count = 0
        todo_count = 0
        fixme_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                comment_count += 1
                if "todo" in stripped.lower():
                    todo_count += 1
                if "fixme" in stripped.lower() or "fix me" in stripped.lower():
                    fixme_count += 1

        if comment_count > 5:
            issues.append(f"High comment density: {comment_count} comment lines found — may indicate unused code")
            suggestions.append("Remove commented-out code; use version control for history instead")

        if todo_count > 0:
            issues.append(f"TODO/FIXME markers found: {todo_count} — incomplete code detected")
            suggestions.append("Resolve all TODO/FIXME items before deployment")

        # Check for magic numbers
        import re
        magic_number_pattern = re.compile(r'\b\d{4,}\b')
        magic_numbers = magic_number_pattern.findall(content)
        # Filter out years and common values
        magic_numbers = [n for n in magic_numbers if n not in ['1000', '2000', '3000', '5000']]
        if magic_numbers:
            issues.append(f"Magic numbers detected: {', '.join(magic_numbers[:5])} — consider named constants")
            suggestions.append("Extract magic numbers into named constants for better maintainability")

        # Check function length (rough heuristic)
        func_start_pattern = re.compile(r'function\s+\w+\s*\(')
        func_starts = list(func_start_pattern.finditer(content))
        large_functions = 0
        for m in func_starts:
            brace_count = 0
            pos = m.end()
            # Find opening brace
            while pos < len(content) and content[pos] != '{':
                pos += 1
            if pos >= len(content):
                continue
            brace_count = 1
            start_line = content[:pos].count("\n")
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            end_line = content[:pos].count("\n")
            func_lines = end_line - start_line
            if func_lines > 30:
                large_functions += 1

        if large_functions > 0:
            issues.append(f"{large_functions} function(s) exceed 30 lines — consider refactoring")
            suggestions.append("Break large functions into smaller, single-purpose functions")

        # Check for var usage
        if re.search(r'\bvar\s+', content):
            issues.append("Use of 'var' keyword detected — prefer const/let for block scoping")
            suggestions.append("Replace 'var' with 'const' (immutable) or 'let' (mutable)")

        # Check for console.log (debugging leftovers)
        log_count = len(re.findall(r'console\.log\s*\(', content))
        if log_count > 2:
            issues.append(f"Excessive console.log calls: {log_count} — debugging leftovers")
            suggestions.append("Remove console.log statements before production")

        # Check for deep nesting (nested conditionals/loops)
        nesting_count = 0
        current_nesting = 0
        for ch in content:
            if ch == '{':
                current_nesting += 1
                if current_nesting > 4:
                    nesting_count += 1
            elif ch == '}':
                current_nesting -= 1

        if nesting_count > 0:
            issues.append("Deeply nested code blocks detected (> 4 levels) — readability concern")
            suggestions.append("Extract nested logic into separate functions")

        return issues, suggestions

    def _analyze_ux(self, content: str) -> tuple[list[str], list[str]]:
        """UX heuristic analysis — accessibility, clarity, mobile-friendliness."""
        issues: list[str] = []
        suggestions: list[str] = []
        lower = content.lower()

        # Check for viewport meta tag
        if "name=\"viewport\"" not in lower and "name='viewport'" not in lower:
            issues.append("No viewport meta tag found — page may not be mobile-friendly")
            suggestions.append('Add <meta name="viewport" content="width=device-width, initial-scale=1">')

        # Check for alt text on images
        img_count = lower.count("<img")
        alt_count = lower.count("alt=")
        if img_count > 0 and alt_count < img_count:
            issues.append(f"Missing alt text on images ({alt_count} alt attributes for {img_count} images)")
            suggestions.append("Add descriptive alt text to all images for accessibility")

        # Check for semantic HTML elements
        semantic_elements = ["<header", "<nav", "<main", "<article", "<section", "<aside", "<footer"]
        found_semantic = sum(1 for e in semantic_elements if e in lower)
        if found_semantic < 2:
            issues.append("Limited use of semantic HTML elements — poor accessibility")
            suggestions.append("Use <header>, <nav>, <main>, <article>, <section>, <footer> for screen readers")

        # Check for form labels
        input_count = lower.count("<input")
        label_count = lower.count("<label")
        if input_count > 0 and label_count < input_count:
            issues.append(f"Missing form labels ({label_count} labels for {input_count} inputs)")
            suggestions.append("Each input should have an associated <label> element")

        # Check for aria attributes
        if input_count > 0 and "aria-" not in lower:
            issues.append("No ARIA attributes found — accessibility could be improved")
            suggestions.append("Add ARIA labels/roles to interactive elements for screen readers")

        # Check for loading/error states
        loading_patterns = ["loading", "spinner", "skeleton", "progress"]
        if not any(p in lower for p in loading_patterns):
            issues.append("No loading state indicators detected")
            suggestions.append("Add loading spinners or skeleton screens for async operations")

        error_patterns = ["error message", "error-message", "error_message", "error alert"]
        if not any(p in lower for p in error_patterns) and input_count > 0:
            issues.append("No error message patterns found — forms may lack user feedback")
            suggestions.append("Implement inline error messages for form validation")

        # Check for focus styles
        if ":focus" not in content:
            issues.append("No :focus CSS styles found — keyboard navigation may be invisible")
            suggestions.append("Add :focus-visible or :focus styles for keyboard accessibility")

        return issues, suggestions

    def _analyze_completeness(self, content: str) -> tuple[list[str], list[str]]:
        """Completeness heuristic analysis — missing features, broken links."""
        issues: list[str] = []
        suggestions: list[str] = []
        lower = content.lower()

        # Check for placeholder/lorem ipsum text
        placeholder_patterns = ["lorem", "ipsum", "placeholder text", "sample text", "todo", "fixme"]
        for pattern in placeholder_patterns:
            if pattern in lower:
                issues.append(f"Placeholder content detected: '{pattern}' — page appears incomplete")
                suggestions.append("Replace placeholder content with real, meaningful content")
                break

        # Check for page title
        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if not title_match or not title_match.group(1).strip():
            issues.append("Missing or empty <title> tag")
            suggestions.append("Add a descriptive <title> tag for SEO and browser tabs")
        elif len(title_match.group(1).strip()) < 5:
            issues.append(f"Title too short: '{title_match.group(1).strip()}'")
            suggestions.append("Use a more descriptive title (10-60 characters recommended)")

        # Check for meta description
        if 'name="description"' not in lower and "name='description'" not in lower:
            issues.append("Missing meta description tag")
            suggestions.append('Add <meta name="description" content="..."> for SEO')

        # Check for charset
        if 'charset=' not in lower:
            issues.append("Missing charset meta tag")
            suggestions.append('<meta charset="UTF-8"> is required for proper text rendering')

        # Check for favicon
        if "favicon" not in lower and "icon" not in lower:
            issues.append("No favicon detected")
            suggestions.append("Add a favicon for browser tab identification")

        # Check for empty or stub functions
        empty_func_pattern = re.compile(r'function\s+\w+\s*\([^)]*\)\s*\{\s*\}')
        empty_funcs = empty_func_pattern.findall(content)
        if empty_funcs:
            names = []
            for f in empty_funcs:
                name_match = re.search(r'function\s+(\w+)', f)
                if name_match:
                    names.append(name_match.group(1))
            issues.append(f"Empty/stub functions found: {', '.join(names[:5])}")
            suggestions.append("Implement all stub functions with real logic")

        # Check for hardcoded URLs that might be broken
        url_pattern = url_pattern = re.compile(r'href=["\'](https?://[^"\']+)["\']')
        urls = url_pattern.findall(content)
        if urls:
            localhost_urls = [u for u in urls if "localhost" in u or "127.0.0.1" in u]
            if localhost_urls:
                issues.append(f"Hardcoded localhost URLs: {', '.join(localhost_urls[:3])}")
                suggestions.append("Replace localhost URLs with production-relative paths or config variables")

        # Check for lang attribute on html tag
        if 'lang="' not in lower and "lang='" not in lower:
            issues.append("Missing lang attribute on <html> tag")
            suggestions.append('Add lang="en" (or appropriate language) to <html> tag for accessibility')

        return issues, suggestions

    def _analyze_business(self, content: str) -> tuple[list[str], list[str]]:
        """Business viability heuristic analysis."""
        issues: list[str] = []
        suggestions: list[str] = []
        lower = content.lower()

        # Check for call-to-action
        cta_patterns = ["sign up", "subscribe", "get started", "buy now", "learn more",
                        "contact us", "register", "try free", "start free", "download",
                        "join", "book now", "order now"]
        found_cta = [p for p in cta_patterns if p in lower]
        if not found_cta:
            issues.append("No clear call-to-action (CTA) found — may reduce conversion")
            suggestions.append("Add a prominent CTA button (e.g., 'Get Started', 'Sign Up', 'Contact Us')")

        # Check for contact/company info
        contact_patterns = ["email", "phone", "contact", "about us", "address", "@"]
        if not any(p in lower for p in contact_patterns):
            issues.append("No contact information or 'About Us' section found")
            suggestions.append("Add contact information (email, phone) and an About section for credibility")

        # Check for value proposition
        value_patterns = ["benefit", "feature", "solution", "why choose", "trusted by",
                         "award", "guarantee", "results", "proven"]
        if not any(p in lower for p in value_patterns):
            issues.append("Weak value proposition — benefits/features not clearly stated")
            suggestions.append("Clearly articulate what problem you solve and why users should care")

        # Check for social proof
        social_patterns = ["testimonial", "review", "rating", "customers", "clients",
                          "users", "case study", "as seen on", "partner"]
        if not any(p in lower for p in social_patterns):
            issues.append("No social proof elements found (testimonials, reviews, customer logos)")
            suggestions.append("Add testimonials, case studies, or customer logos to build trust")

        # Check for pricing indication
        pricing_patterns = ["pricing", "price", "plan", "free", "premium", "pro", "enterprise",
                           "month", "yearly", "subscription", "cost"]
        if not any(p in lower for p in pricing_patterns):
            issues.append("No pricing information or plan details found")
            suggestions.append("Clearly display pricing information or indicate if the product is free")

        # Check for navigation structure
        nav_patterns = ["<nav", "menu", "navbar", "navigation"]
        if not any(p in lower for p in nav_patterns):
            issues.append("No navigation menu detected — poor site structure")
            suggestions.append("Add a clear navigation menu with links to key sections")

        # Check for footer
        if "<footer" not in lower and "footer" not in lower:
            issues.append("No footer section detected")
            suggestions.append("Add a footer with links, copyright, and legal information")

        # Check for analytics/tracking
        analytics_patterns = ["analytics", "gtag", "google analytics", "tracking", "pixel",
                             "facebook", "conversion"]
        if not any(p in lower for p in analytics_patterns):
            issues.append("No analytics or conversion tracking detected")
            suggestions.append("Add analytics (e.g., Google Analytics) to measure user engagement")

        return issues, suggestions


def _looks_like_real_call(content: str, func_name: str) -> bool:
    """Check if a function call looks like real usage (not in a string)."""
    pattern = re.compile(r'\b' + re.escape(func_name) + r'\s*\(')
    return bool(pattern.search(content))
