"""GuardianReport — Core verification reporting for maestro-guard."""

import json


# Default weights for the five verification checks (must sum to 100)
DEFAULT_WEIGHTS = {
    "js_syntax": 25,
    "handlers_defined": 25,
    "dom_refs": 20,
    "no_console_errors": 15,
    "fulfillment": 15,
}

# Checks that must pass for all_passed to be True
MANDATORY_CHECKS = {"js_syntax", "handlers_defined"}


class GuardianReport:
    """Verification report that tracks check results and auto-fixes.

    Score system (100 total points):
        js_syntax        = 25
        handlers_defined = 25
        dom_refs         = 20
        no_console_errors = 15
        fulfillment      = 15

    Mandatory checks (must all pass): js_syntax, handlers_defined
    """

    def __init__(self):
        self._checks: dict[str, dict] = {}
        self._fixes: list[dict] = []
        self._weights: dict[str, int] = dict(DEFAULT_WEIGHTS)
        self._mandatory: set[str] = set(MANDATORY_CHECKS)

    def add_check(self, name: str, passed: bool, detail: str = "", weight: int | None = None) -> None:
        """Record a check result.

        Args:
            name: Check identifier (e.g., 'js_syntax').
            passed: Whether the check passed.
            detail: Descriptive message about the check result.
            weight: Point value for this check. If None, uses the default
                    weight for known checks or distributes evenly.
        """
        if weight is None:
            weight = self._weights.get(name, 0)

        self._checks[name] = {
            "passed": passed,
            "detail": detail,
            "weight": weight,
        }

    def add_fix(self, fix_type: str, detail: str) -> None:
        """Record an auto-fix that was applied (for future use).

        Args:
            fix_type: Type/category of the fix applied.
            detail: Description of what was fixed.
        """
        self._fixes.append({
            "type": fix_type,
            "detail": detail,
        })

    @property
    def score(self) -> float:
        """Calculate weighted score out of 100."""
        if not self._checks:
            return 0.0

        total_weight = 0
        earned_weight = 0

        for name, check in self._checks.items():
            weight = check.get("weight", 0)
            total_weight += weight
            if check.get("passed", False):
                earned_weight += weight

        if total_weight == 0:
            return 0.0

        return round((earned_weight / total_weight) * 100, 1)

    @property
    def all_passed(self) -> bool:
        """True only when score == 100 AND all mandatory checks passed."""
        if not self._checks:
            return False

        # All mandatory checks must be present and passed
        for mandatory in self._mandatory:
            check = self._checks.get(mandatory)
            if check is None or not check.get("passed", False):
                return False

        # Score must be 100
        return self.score == 100.0

    @property
    def failing_checks(self) -> list[tuple[str, dict]]:
        """Return list of (name, check_dict) for failing/missing checks."""
        failures = []

        # Check for mandatory checks that are missing entirely
        for mandatory in self._mandatory:
            if mandatory not in self._checks:
                failures.append((
                    mandatory,
                    {"passed": False, "detail": "Check not executed", "weight": self._weights.get(mandatory, 0)},
                ))

        # Check for checks that failed
        for name, check in self._checks.items():
            if not check.get("passed", False):
                failures.append((name, check))

        return failures

    def summary(self) -> str:
        """Return a pretty terminal summary string with PASS/FAIL icons."""
        lines = []
        lines.append("=" * 60)
        lines.append("  GUARDIAN VERIFICATION REPORT")
        lines.append("=" * 60)
        lines.append("")

        if not self._checks:
            lines.append("  ⚠  No checks executed.")
            lines.append("")
            lines.append("=" * 60)
            return "\n".join(lines)

        # Show each check
        for name, check in self._checks.items():
            passed = check.get("passed", False)
            detail = check.get("detail", "")
            weight = check.get("weight", 0)
            icon = "✅ PASS" if passed else "❌ FAIL"
            mandatory_mark = " [MANDATORY]" if name in self._mandatory else ""
            lines.append(f"  {icon}{mandatory_mark}  {name}  ({weight} pts)")
            if detail:
                lines.append(f"      {detail}")
            lines.append("")

        # Show missing mandatory checks
        for mandatory in self._mandatory:
            if mandatory not in self._checks:
                weight = self._weights.get(mandatory, 0)
                lines.append(f"  ❌ FAIL [MANDATORY]  {mandatory}  ({weight} pts)")
                lines.append(f"      Check was not executed")
                lines.append("")

        # Show fixes
        if self._fixes:
            lines.append("  ── Auto-fixes applied ──")
            for fix in self._fixes:
                lines.append(f"    🔧 {fix.get('type', 'unknown')}: {fix.get('detail', '')}")
            lines.append("")

        # Score and status
        score_val = self.score
        lines.append(f"  Score: {score_val}/100")

        if self.all_passed:
            lines.append("  Status: ✅ ALL CHECKS PASSED")
        elif score_val == 100 and not self.all_passed:
            # Score is 100 but mandatory checks failed — shouldn't happen, but handle it
            lines.append("  Status: ⚠  PERFECT SCORE BUT MANDATORY CHECK(S) FAILED")
        else:
            failing = self.failing_checks
            lines.append(f"  Status: ❌  {len(failing)} check(s) failing")

            if score_val > 0:
                passing_count = sum(
                    1 for c in self._checks.values() if c.get("passed", False)
                )
                lines.append(f"  {passing_count}/{len(self._checks)} check(s) passing")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation."""
        return {
            "score": self.score,
            "all_passed": self.all_passed,
            "checks": dict(self._checks),
            "fixes": list(self._fixes),
            "failing_checks": [
                {"name": name, "details": check}
                for name, check in self.failing_checks
            ],
        }

    def to_json(self) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=2)
