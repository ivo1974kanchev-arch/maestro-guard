"""ScoreAggregator — Aggregates multi-reviewer scores into weighted results."""

from typing import Optional


class ScoreAggregator:
    """Aggregates scores from multiple reviewer perspectives.

    Each review has a weight (summing to 100 by default) and a score (0-10).
    The aggregated score is a weighted average scaled to 0-100.
    """

    def __init__(self):
        self._reviews: list[dict] = []

    def add_review(self, role_name: str, score: float, issues: list[str],
                   suggestions: list[str], verdict: str,
                   weight: Optional[int] = None) -> None:
        """Record a single reviewer's result.

        Args:
            role_name: Display name of the reviewer role.
            score: Numeric score out of 10.
            issues: List of issue descriptions.
            suggestions: List of fix suggestions.
            verdict: 'pass' or 'fail'.
            weight: Weight for this reviewer (default: 20).
        """
        if weight is None:
            weight = 20

        self._reviews.append({
            "role_name": role_name,
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
            "verdict": verdict,
            "weight": weight,
        })

    def calculate(self) -> float:
        """Calculate the weighted average score, scaled to 0-100.

        Returns:
            Float score out of 100.
        """
        if not self._reviews:
            return 0.0

        total_weight = 0
        earned_weight = 0

        for review in self._reviews:
            weight = review.get("weight", 20)
            score = review.get("score", 0)
            total_weight += weight
            # Score is out of 10, weight is out of total_weight
            earned_weight += (score / 10.0) * weight

        if total_weight == 0:
            return 0.0

        return round((earned_weight / total_weight) * 100, 1)

    @property
    def all_passed(self) -> bool:
        """True if every reviewer passed (score >= 6)."""
        if not self._reviews:
            return False
        return all(r.get("verdict") == "pass" for r in self._reviews)

    @property
    def failing_reviews(self) -> list[dict]:
        """Return list of reviews that failed."""
        return [r for r in self._reviews if r.get("verdict") != "pass"]

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return {
            "score": self.calculate(),
            "all_passed": self.all_passed,
            "reviews": list(self._reviews),
            "failing_reviews": [
                {"role_name": r["role_name"], "issues": r.get("issues", [])}
                for r in self.failing_reviews
            ],
        }

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = []
        score = self.calculate()
        lines.append(f"Overall Score: {score}/100")
        lines.append(f"Status: {'✅ ALL PASSED' if self.all_passed else '❌ SOME FAILED'}")
        lines.append("")
        for review in self._reviews:
            status = "✅ PASS" if review.get("verdict") == "pass" else "❌ FAIL"
            lines.append(f"  {status}  {review['role_name']}: {review['score']}/10")
        return "\n".join(lines)
