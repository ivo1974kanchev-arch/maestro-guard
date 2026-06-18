"""
Maestro Guard — Standalone AI Code Verifier.

Minimal rebuild of the review system for PageRX.
Analyses HTML/CSS/JS content from 5 heuristic perspectives.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Data Types ─────────────────────────────────────────────────────────────

@dataclass
class ReviewReport:
    """Aggregated review result from all roles."""
    reviews: list[dict] = field(default_factory=list)
    overall_score: float = 0.0
    verdict: str = "FAIL"
    improvement_analysis: dict = field(default_factory=dict)
    total_reviewers: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary matching the expected API response shape."""
        issues = []
        suggestions = []
        for r in self.reviews:
            issues.extend(r.get("issues", []))
            suggestions.extend(r.get("suggestions", []))

        # Severity classification
        by_severity = {"critical": 0, "major": 0, "minor": 0}
        for issue in issues:
            if isinstance(issue, dict):
                s = issue.get("severity", "minor")
            else:
                s = "minor"
            if s in by_severity:
                by_severity[s] += 1

        return {
            "reviews": self.reviews,
            "overall_score": self.overall_score,
            "verdict": self.verdict,
            "improvement_analysis": {
                "total_issues": len(issues),
                "by_severity": by_severity,
                "issues": issues,
            },
            "total_reviewers": self.total_reviewers,
        }


# ── Review Roles ───────────────────────────────────────────────────────────

ROLES = ["security", "code_quality", "ux", "completeness", "business"]

ROLE_NAMES = {
    "security": "Security Auditor",
    "code_quality": "Code Quality Analyst",
    "ux": "UX Reviewer",
    "completeness": "Completeness Checker",
    "business": "Business Viability Reviewer",
}

WEIGHTS = {
    "security": 20,
    "code_quality": 20,
    "ux": 20,
    "completeness": 20,
    "business": 20,
}


# ── Heuristic Reviewers ────────────────────────────────────────────────────

def _review_security(content: str) -> dict:
    """Heuristic security review."""
    issues = []
    suggestions = []
    score = 10

    # Check for eval()
    if "eval(" in content:
        issues.append("eval() usage detected — XSS risk")
        suggestions.append("Replace eval() with JSON.parse() or Function constructor")
        score -= 2

    # Check for inline event handlers
    inline_handlers = re.findall(r'\bon\w+\s*=\s*["\']', content, re.I)
    if inline_handlers:
        issues.append(f"Inline event handlers detected ({len(inline_handlers)} occurrences) — XSS vector")
        suggestions.append("Use addEventListener() instead of inline event handlers")
        score -= 1.5

    # Check for document.write
    if "document.write" in content:
        issues.append("document.write() detected — security risk")
        suggestions.append("Use DOM manipulation methods instead of document.write()")
        score -= 1.5

    # Check for innerHTML
    inner_html_count = len(re.findall(r'\.innerHTML\s*=', content))
    if inner_html_count > 0:
        issues.append(f".innerHTML assignment detected ({inner_html_count} occurrences) — XSS risk")
        suggestions.append("Use .textContent or insertAdjacentHTML() with sanitization")
        score -= 1

    # Check for localStorage/sessionStorage with sensitive data patterns
    if "localStorage" in content or "sessionStorage" in content:
        issues.append("Client-side storage detected — ensure no sensitive data stored")
        suggestions.append("Avoid storing tokens or PII in localStorage/sessionStorage")
        score -= 0.5

    # Check for Content-Security-Policy
    if "Content-Security-Policy" not in content and "http-equiv" not in content.lower():
        issues.append("No Content-Security-Policy found")
        suggestions.append("Add a Content-Security-Policy meta tag or HTTP header")
        score -= 0.5

    # Check for script injection vectors
    if re.search(r'document\.(write|writeln)\s*\(\s*["\']<script', content, re.I):
        issues.append("Script injection via document.write detected")
        suggestions.append("Remove dynamic script injection")
        score -= 1.5

    score = max(0, round(score, 1))
    verdict = "pass" if score >= 6 else "fail"
    return {"score": score, "issues": issues[:5], "suggestions": suggestions[:5], "verdict": verdict}


def _review_code_quality(content: str) -> dict:
    """Heuristic code quality review."""
    issues = []
    suggestions = []
    score = 10

    # Check for magic numbers
    magic_numbers = re.findall(r'\b[0-9]{4,}\b', content)
    if len(magic_numbers) > 5:
        issues.append(f"Magic numbers detected ({len(magic_numbers)} occurrences)")
        suggestions.append("Extract magic numbers into named constants")
        score -= 1

    # Check for commented out code
    commented = len(re.findall(r'//.*$|/\*.*?\*/', content, re.MULTILINE | re.DOTALL))
    if commented > 10:
        issues.append(f"Excessive commented code ({commented} lines)")
        suggestions.append("Remove commented-out code; use version control")
        score -= 1

    # Check for var usage
    if re.search(r'\bvar\s+\w+', content):
        issues.append("'var' keyword used — use 'let' or 'const' instead")
        suggestions.append("Replace 'var' with 'let' or 'const' for proper scoping")
        score -= 0.5

    # Check for console.log
    console_logs = len(re.findall(r'console\.(log|debug|info)\s*\(', content))
    if console_logs > 3:
        issues.append(f"Console.log statements found ({console_logs} occurrences)")
        suggestions.append("Remove or wrap console.log statements in production")
        score -= 0.5

    # Check for TODO/FIXME
    todos = len(re.findall(r'\b(TODO|FIXME|HACK|XXX)\b', content, re.I))
    if todos > 0:
        issues.append(f"Pending TODO/FIXME markers ({todos} found)")
        suggestions.append("Address TODO/FIXME items before production deployment")
        score -= 0.5

    # Check for deeply nested structures
    nesting_depth = 0
    max_nesting = 0
    for ch in content:
        if ch == '{':
            nesting_depth += 1
            max_nesting = max(max_nesting, nesting_depth)
        elif ch == '}':
            nesting_depth = max(0, nesting_depth - 1)
    if max_nesting > 6:
        issues.append(f"Deep nesting detected (max depth: {max_nesting})")
        suggestions.append("Refactor deeply nested structures into smaller functions")
        score -= 1

    # Check for empty functions
    empty_fns = len(re.findall(r'function\s+\w+\s*\(\s*\)\s*\{\s*\}', content))
    if empty_fns > 0:
        issues.append(f"Empty functions detected ({empty_fns} found)")
        suggestions.append("Implement or remove empty function stubs")
        score -= 0.5

    score = max(0, round(score, 1))
    verdict = "pass" if score >= 6 else "fail"
    return {"score": score, "issues": issues[:5], "suggestions": suggestions[:5], "verdict": verdict}


def _review_ux(content: str) -> dict:
    """Heuristic UX review."""
    issues = []
    suggestions = []
    score = 10

    # Check for viewport meta tag
    if '<meta name="viewport"' not in content.lower():
        issues.append("No viewport meta tag found")
        suggestions.append("Add <meta name='viewport' content='width=device-width, initial-scale=1'>")
        score -= 1.5

    # Check for alt attributes on images
    img_tags = re.findall(r'<img\s[^>]*>', content, re.I)
    imgs_without_alt = 0
    for img in img_tags:
        if 'alt=' not in img.lower():
            imgs_without_alt += 1
    if imgs_without_alt > 0:
        issues.append(f"Images without alt text ({imgs_without_alt} of {len(img_tags)})")
        suggestions.append("Add descriptive alt text to all images for accessibility")
        score -= 1

    # Check for form labels
    input_tags = re.findall(r'<input\s[^>]*>', content, re.I)
    inputs_with_labels = 0
    for inp in input_tags:
        if 'aria-label' in inp.lower() or 'id=' in inp.lower():
            inputs_with_labels += 1
    if input_tags and inputs_with_labels < len(input_tags) * 0.5:
        issues.append("Form inputs may lack proper labels")
        suggestions.append("Associate labels with inputs using 'for' attribute or aria-label")
        score -= 1

    # Check for semantic HTML
    semantic_elements = ['<nav', '<header', '<main', '<footer', '<article', '<section']
    found_semantic = sum(1 for el in semantic_elements if el in content.lower())
    if found_semantic < 2:
        issues.append("Limited use of semantic HTML elements")
        suggestions.append("Use <nav>, <header>, <main>, <footer> for better accessibility")
        score -= 0.5

    # Check for lang attribute on html tag
    if 'lang="' not in content[:500].lower():
        issues.append("No lang attribute on <html> element")
        suggestions.append("Add lang='en' (or appropriate language) to <html> tag")
        score -= 0.5

    # Check for color contrast (basic check)
    if 'color' in content.lower() and 'background' in content.lower():
        pass  # Hard to check programmatically, note it
    else:
        suggestions.append("Ensure sufficient color contrast (WCAG AA: 4.5:1 for normal text)")

    score = max(0, round(score, 1))
    verdict = "pass" if score >= 6 else "fail"
    return {"score": score, "issues": issues[:5], "suggestions": suggestions[:5], "verdict": verdict}


def _review_completeness(content: str) -> dict:
    """Heuristic completeness review."""
    issues = []
    suggestions = []
    score = 10

    # Check for title tag
    if '<title>' not in content.lower():
        issues.append("No <title> tag found")
        suggestions.append("Add a descriptive <title> tag within <head>")
        score -= 1.5
    else:
        title_match = re.search(r'<title>(.*?)</title>', content, re.I | re.DOTALL)
        if title_match and len(title_match.group(1).strip()) < 10:
            issues.append("Title tag is too short (under 10 characters)")
            suggestions.append("Use a descriptive title (40-60 characters recommended)")
            score -= 0.5

    # Check for meta description
    if 'name="description"' not in content.lower() and "name='description'" not in content.lower():
        issues.append("No meta description tag found")
        suggestions.append("Add a compelling meta description (150-160 characters)")
        score -= 1

    # Check for charset
    if 'charset' not in content.lower()[:1000]:
        issues.append("No charset declaration found")
        suggestions.append("Add <meta charset='UTF-8'> in <head>")
        score -= 0.5

    # Check for lang attribute
    if 'lang=' not in content[:500].lower():
        issues.append("No language declaration on <html> tag")
        suggestions.append("Add lang attribute to <html>: <html lang='en'>")
        score -= 0.5

    # Check for favicon
    if 'favicon' not in content.lower() and 'icon' not in content.lower()[:2000]:
        issues.append("No favicon detected")
        suggestions.append("Add a favicon with <link rel='icon' href='/favicon.ico'>")
        score -= 0.5

    # Check for placeholder/lorem ipsum content
    lorem_patterns = ['lorem ipsum', 'dolor sit amet', 'placeholder', 'todo:', 'coming soon']
    for pattern in lorem_patterns:
        if re.search(pattern, content, re.I):
            issues.append("Placeholder/lorem ipsum content detected")
            suggestions.append("Replace placeholder content with final copy")
            score -= 1
            break

    # Check for broken links (just looking for href="#")
    broken_links = len(re.findall(r'href=["\']#["\']', content))
    if broken_links > 1:
        issues.append(f"Broken or placeholder links detected ({broken_links})")
        suggestions.append("Replace # links with actual URLs or remove them")
        score -= 0.5

    # Check for empty sections
    empty_sections = len(re.findall(r'<section[^>]*>\s*</section>', content, re.I))
    empty_divs = len(re.findall(r'<div[^>]*>\s*</div>', content, re.I))
    if empty_sections + empty_divs > 2:
        issues.append(f"Empty containers found ({empty_sections + empty_divs})")
        suggestions.append("Remove or populate empty section/div elements")
        score -= 0.5

    score = max(0, round(score, 1))
    verdict = "pass" if score >= 6 else "fail"
    return {"score": score, "issues": issues[:5], "suggestions": suggestions[:5], "verdict": verdict}


def _review_business(content: str) -> dict:
    """Heuristic business viability review."""
    issues = []
    suggestions = []
    score = 10

    # Check for clear CTA
    cta_patterns = [
        r'get\s+started', r'sign\s+up', r'try\s+(now|free)', r'buy\s+now',
        r'book\s+(now|a\s+demo)', r'contact\s+us', r'learn\s+more',
        r'subscribe', r'download', r'start\s+free',
    ]
    found_cta = any(re.search(p, content, re.I) for p in cta_patterns)
    if not found_cta:
        issues.append("No clear call-to-action detected")
        suggestions.append("Add a prominent CTA button (e.g., 'Get Started', 'Try Free')")
        score -= 2

    # Check for pricing indication
    pricing_patterns = [r'\$[\d,]+', r'price', r'pricing', r'plan', r'month', r'/mo']
    has_pricing = any(re.search(p, content, re.I) for p in pricing_patterns)
    if not has_pricing:
        issues.append("No pricing information found")
        suggestions.append("Add pricing information or a clear 'Free' / 'Contact for pricing' indicator")
        score -= 1.5

    # Check for social proof
    social_proof = [
        r'testimonial', r'review', r'rating', r'star', r'customer', r'client',
        r'users?\s+(love|trust|recommend)', r'case\s+stud', r'logo',
    ]
    has_social = any(re.search(p, content, re.I) for p in social_proof)
    if not has_social:
        issues.append("No social proof elements found")
        suggestions.append("Add testimonials, client logos, or user count as social proof")
        score -= 1.5

    # Check for navigation
    nav_patterns = [r'<nav', r'menu', r'navigation', r'class=["\'].*nav', r'id=["\'].*nav']
    has_nav = any(re.search(p, content, re.I) for p in nav_patterns)
    if not has_nav:
        issues.append("No navigation structure detected")
        suggestions.append("Add clear navigation menu for multi-page sites")
        score -= 0.5

    # Check for contact info
    contact_patterns = [
        r'contact', r'email', r'@\w+\.\w+', r'phone', r'twitter\.com',
        r'linkedin', r'github\.com',
    ]
    has_contact = any(re.search(p, content, re.I) for p in contact_patterns)
    if not has_contact:
        issues.append("No contact information found")
        suggestions.append("Add contact email or social links for credibility")
        score -= 0.5

    # Check for analytics/tracking
    if 'gtag' not in content and 'analytics' not in content.lower() and 'plausible' not in content.lower():
        suggestions.append("Consider adding analytics to track user behavior and conversions")

    # Check for value proposition
    vp_patterns = [
        r'value\s+propos', r'we\s+(help|build|create|provide)', r'solve',
        r'benefit', r'feature', r'why\s+\w+',
    ]
    has_vp = any(re.search(p, content, re.I) for p in vp_patterns)
    if not has_vp:
        issues.append("Unclear value proposition")
        suggestions.append("State your value proposition clearly above the fold")
        score -= 1

    score = max(0, round(score, 1))
    verdict = "pass" if score >= 6 else "fail"
    return {"score": score, "issues": issues[:5], "suggestions": suggestions[:5], "verdict": verdict}


# ── Reviewer Registry ──────────────────────────────────────────────────────

REVIEWERS = {
    "security": _review_security,
    "code_quality": _review_code_quality,
    "ux": _review_ux,
    "completeness": _review_completeness,
    "business": _review_business,
}


# ── Orchestrator ───────────────────────────────────────────────────────────

class ReviewOrchestrator:
    """Run heuristic reviews across multiple roles."""

    def __init__(self, content: str, roles: Optional[list[str]] = None):
        self.content = content
        self.roles = roles or ROLES

    def run_all(self) -> ReviewReport:
        """Run all specified reviewers and aggregate results."""
        reviews = []

        for role in self.roles:
            if role in REVIEWERS:
                result = REVIEWERS[role](self.content)
                reviews.append({
                    "role": role,
                    "role_name": ROLE_NAMES.get(role, role),
                    "score": result["score"],
                    "issues": result["issues"],
                    "suggestions": result["suggestions"],
                    "verdict": result["verdict"],
                    "weight": WEIGHTS.get(role, 20),
                })

        # Calculate weighted overall score
        if reviews:
            total_weight = sum(r.get("weight", 20) for r in reviews)
            earned_weight = sum(
                (r.get("score", 5) / 10.0) * r.get("weight", 20)
                for r in reviews
            )
            overall_score = round((earned_weight / total_weight) * 100, 1) if total_weight > 0 else 0
            all_passed = all(r.get("verdict") == "pass" for r in reviews)
            verdict = "PASS" if all_passed else "FAIL"
        else:
            overall_score = 0
            verdict = "FAIL"

        return ReviewReport(
            reviews=reviews,
            overall_score=overall_score,
            verdict=verdict,
            total_reviewers=len(reviews),
        )
