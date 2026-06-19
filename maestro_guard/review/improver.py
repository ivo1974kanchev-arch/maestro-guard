"""ContentImprover — Analyzes reviews and suggests content improvements."""

from typing import Any


class ContentImprover:
    """Analyzes review feedback and categorizes issues for improvement.

    For now, this is an analysis-only tool. It categorizes issues from
    reviews by severity and provides a structured improvement report.
    Auto-fix support can be added in future versions.
    """

    SEVERITY_CRITICAL = "critical"
    SEVERITY_MAJOR = "major"
    SEVERITY_MINOR = "minor"
    SEVERITY_INFO = "info"

    # Words/phrases that should not trigger false positive severity keyword matches
    _CRITICAL_EXCLUDE = {"content-security-policy"}

    def __init__(self):
        self._issues: list[dict] = []

    def analyze(self, content: str, reviews: list[dict]) -> None:
        """Analyze content against all review results and categorize issues.

        Args:
            content: The original HTML/JS content.
            reviews: List of review result dicts from all reviewers.
        """
        self._issues = []

        for review in reviews:
            role_name = review.get("role_name", "Unknown")
            role_key = review.get("role", "unknown")
            issues = review.get("issues", [])
            suggestions = review.get("suggestions", [])

            for i, issue in enumerate(issues):
                severity = self._classify_severity(issue, role_key)
                suggestion = suggestions[i] if i < len(suggestions) else ""
                self._issues.append({
                    "role": role_key,
                    "role_name": role_name,
                    "issue": issue,
                    "suggestion": suggestion,
                    "severity": severity,
                })

    def _classify_severity(self, issue: str, role: str) -> str:
        """Classify an issue by severity based on content and role."""
        critical_keywords = [
            "xss", "injection", "eval", "vulnerability", "security",
            "broken", "empty function", "no content",
        ]
        major_keywords = [
            "missing", "no label", "no alt", "no viewport", "no nav",
            "no title", "no description", "no charset", "stub",
            "placeholder", "magic number", "deeply nested",
        ]
        minor_keywords = [
            "consider", "could", "may want", "suggestion", "comment density",
            "analytics", "pricing", "social proof",
        ]

        issue_lower = issue.lower()
        # Strip known false-positive phrases before keyword matching
        stripped = issue_lower
        for exclude in self._CRITICAL_EXCLUDE:
            stripped = stripped.replace(exclude, "")

        for kw in critical_keywords:
            if kw in stripped:
                return self.SEVERITY_CRITICAL
        for kw in major_keywords:
            if kw in issue_lower:
                return self.SEVERITY_MAJOR

        return self.SEVERITY_MINOR

    @property
    def critical_issues(self) -> list[dict]:
        """Return only critical-severity issues."""
        return [i for i in self._issues if i["severity"] == self.SEVERITY_CRITICAL]

    @property
    def major_issues(self) -> list[dict]:
        """Return only major-severity issues."""
        return [i for i in self._issues if i["severity"] == self.SEVERITY_MAJOR]

    @property
    def minor_issues(self) -> list[dict]:
        """Return only minor-severity issues."""
        return [i for i in self._issues if i["severity"] == self.SEVERITY_MINOR]

    def analyze_summary(self) -> dict:
        """Return a summary of the analysis."""
        return {
            "total_issues": len(self._issues),
            "by_severity": {
                "critical": len(self.critical_issues),
                "major": len(self.major_issues),
                "minor": len(self.minor_issues),
            },
            "issues": list(self._issues),
        }
