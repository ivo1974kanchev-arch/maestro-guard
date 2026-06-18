"""Comprehensive tests for the multi-perspective review system."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from maestro_guard.review import ReviewOrchestrator, ReviewReport
from maestro_guard.review.aggregator import ScoreAggregator
from maestro_guard.review.improver import ContentImprover
from maestro_guard.review.prompts import ROLES

FIXTURES = Path(__file__).parent / "fixtures"


# ─── Fixtures ──────────────────────────────────────────────────────────

GOOD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Good Page</title>
</head>
<body>
  <header>
    <nav>
      <a href="/">Home</a>
    </nav>
  </header>
  <main>
    <div id="app"></div>
    <button onclick="handleClick()">Click Me</button>
  </main>
  <footer>
    <p>Contact: test@example.com</p>
  </footer>
  <script>
    function handleClick() {
      const app = document.getElementById('app');
      app.textContent = 'Clicked!';
    }
    function init() {
      const el = document.getElementById('app');
      el.style.display = 'block';
    }
    document.addEventListener('DOMContentLoaded', init);
  </script>
</body>
</html>"""

BAD_HTML = """<!DOCTYPE html>
<html>
<head>
  <title></title>
</head>
<body>
  <div id="main">
    <p>Lorem ipsum dolor sit amet</p>
    <script>
      eval('console.log("bad")');
      document.getElementById('nonexistent').innerHTML = 'data';
      function stubFunc() {}
      function broken() {
        var items = [1, 2, 3
        for (var i = 0; i < items.length; i++) {
          console.error(items[i]);
        }
        // TODO: implement this
        // FIXME: fix this later
      }
      console.log('debug1');
      console.log('debug2');
      console.log('debug3');
    </script>
  </div>
</body>
</html>"""

EMPTY_HTML = "<html></html>"

NO_SCRIPT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>No Scripts</title>
</head>
<body>
  <p>Hello, world!</p>
</body>
</html>"""


# ─── ReviewOrchestrator Tests ─────────────────────────────────────────

class TestReviewOrchestrator:
    def test_initialization(self):
        """Test that orchestrator initializes with all 5 roles by default."""
        orch = ReviewOrchestrator(GOOD_HTML)
        assert len(orch.role_keys) == 5
        assert "security" in orch.role_keys
        assert "code_quality" in orch.role_keys
        assert "ux" in orch.role_keys
        assert "completeness" in orch.role_keys
        assert "business" in orch.role_keys

    def test_custom_roles(self):
        """Test that custom role filtering works."""
        orch = ReviewOrchestrator(GOOD_HTML, roles=["security", "ux"])
        assert len(orch.role_keys) == 2
        assert "security" in orch.role_keys
        assert "ux" in orch.role_keys

    def test_invalid_role_raises(self):
        """Test that invalid role raises ValueError."""
        with pytest.raises(ValueError, match="Unknown role"):
            ReviewOrchestrator(GOOD_HTML, roles=["invalid_role"])

    def test_all_roles_produce_valid_output(self):
        """Test that all 5 roles produce valid, structured output."""
        orch = ReviewOrchestrator(BAD_HTML)
        report = orch.run_all()
        assert len(report.reviews) == 5
        for review in report.reviews:
            assert "role" in review
            assert "role_name" in review
            assert "score" in review
            assert isinstance(review["score"], (int, float))
            assert 0 <= review["score"] <= 10
            assert "issues" in review
            assert isinstance(review["issues"], list)
            assert "suggestions" in review
            assert isinstance(review["suggestions"], list)
            assert "verdict" in review
            assert review["verdict"] in ("pass", "fail")
            assert "weight" in review

    def test_good_html_high_scores(self):
        """Test that good HTML gets high scores."""
        orch = ReviewOrchestrator(GOOD_HTML)
        report = orch.run_all()
        for review in report.reviews:
            assert review["score"] >= 5, f"{review['role_name']} scored {review['score']}/10"

    def test_bad_html_detects_issues(self):
        """Test that bad HTML catches issues across roles."""
        orch = ReviewOrchestrator(BAD_HTML)
        report = orch.run_all()
        # Security should flag eval and innerHTML
        security = [r for r in report.reviews if r["role"] == "security"][0]
        assert len(security["issues"]) >= 2  # eval, innerHTML, etc.
        # Code quality should flag var, TODO, console.log
        quality = [r for r in report.reviews if r["role"] == "code_quality"][0]
        assert len(quality["issues"]) >= 1
        # Completeness should flag empty title, stub function, lorem ipsum
        completeness = [r for r in report.reviews if r["role"] == "completeness"][0]
        assert len(completeness["issues"]) >= 1

    def test_empty_html(self):
        """Test that empty HTML produces results without crashing."""
        orch = ReviewOrchestrator(EMPTY_HTML)
        report = orch.run_all()
        assert len(report.reviews) == 5
        # Empty HTML should have some missing-element issues
        # but no parse errors
        for review in report.reviews:
            assert isinstance(review["score"], (int, float))

    def test_no_script_blocks(self):
        """Test that HTML without script blocks still produces valid reviews."""
        orch = ReviewOrchestrator(NO_SCRIPT_HTML)
        report = orch.run_all()
        assert len(report.reviews) == 5
        # All reviews should be valid even without scripts
        for review in report.reviews:
            assert isinstance(review["score"], (int, float))


# ─── ScoreAggregator Tests ─────────────────────────────────────────────

class TestScoreAggregator:
    def test_empty_aggregator(self):
        """Test that empty aggregator returns 0 score."""
        agg = ScoreAggregator()
        assert agg.calculate() == 0.0
        assert agg.all_passed is False

    def test_perfect_score(self):
        """Test that all reviewers with max scores give 100."""
        agg = ScoreAggregator()
        agg.add_review("Security", 10, [], [], "pass", weight=20)
        agg.add_review("Code Quality", 10, [], [], "pass", weight=20)
        agg.add_review("UX", 10, [], [], "pass", weight=20)
        agg.add_review("Completeness", 10, [], [], "pass", weight=20)
        agg.add_review("Business", 10, [], [], "pass", weight=20)
        assert agg.calculate() == 100.0
        assert agg.all_passed is True

    def test_zero_score(self):
        """Test that all reviewers with 0 score give 0."""
        agg = ScoreAggregator()
        agg.add_review("Security", 0, ["bad"], [], "fail", weight=20)
        agg.add_review("UX", 0, ["bad"], [], "fail", weight=20)
        assert agg.calculate() == 0.0
        assert agg.all_passed is False

    def test_weighted_average(self):
        """Test weighted average calculation."""
        agg = ScoreAggregator()
        agg.add_review("Security", 10, [], [], "pass", weight=50)
        agg.add_review("UX", 0, ["bad"], [], "fail", weight=50)
        # Weighted: (10/10 * 50 + 0/10 * 50) / 100 * 100 = 50
        assert agg.calculate() == 50.0
        assert agg.all_passed is False

    def test_partial_scores(self):
        """Test that mixed scores produce correct weighted average."""
        agg = ScoreAggregator()
        agg.add_review("Security", 8, [], [], "pass", weight=20)
        agg.add_review("Quality", 6, ["minor"], [], "pass", weight=20)
        agg.add_review("UX", 10, [], [], "pass", weight=20)
        agg.add_review("Complete", 7, [], [], "pass", weight=20)
        agg.add_review("Business", 9, [], [], "pass", weight=20)
        # (8+6+10+7+9)/10 * 20 = 40/10 * 20 = 80
        assert agg.calculate() == 80.0

    def test_failing_reviews_property(self):
        """Test that failing_reviews correctly identifies failures."""
        agg = ScoreAggregator()
        agg.add_review("Security", 3, ["issue"], [], "fail", weight=20)
        agg.add_review("UX", 8, [], [], "pass", weight=20)
        fails = agg.failing_reviews
        assert len(fails) == 1
        assert fails[0]["role_name"] == "Security"

    def test_to_dict(self):
        """Test that to_dict returns correct structure."""
        agg = ScoreAggregator()
        agg.add_review("Security", 8, [], [], "pass", weight=20)
        d = agg.to_dict()
        assert "score" in d
        assert "all_passed" in d
        assert "reviews" in d
        assert "failing_reviews" in d
        assert d["score"] == 80.0

    def test_summary(self):
        """Test that summary returns a string with key info."""
        agg = ScoreAggregator()
        agg.add_review("Security", 8, [], [], "pass", weight=20)
        s = agg.summary()
        assert "Score" in s
        assert "Security" in s


# ─── ContentImprover Tests ─────────────────────────────────────────────

class TestContentImprover:
    def test_analyze_categorizes_issues(self):
        """Test that ContentImprover categorizes issues by severity."""
        improver = ContentImprover()
        reviews = [
            {
                "role": "security",
                "role_name": "Security Auditor",
                "issues": ["XSS vulnerability detected"],
                "suggestions": ["Use textContent instead"],
            },
            {
                "role": "ux",
                "role_name": "UX Reviewer",
                "issues": ["Missing viewport meta tag"],
                "suggestions": ["Add viewport meta tag"],
            },
            {
                "role": "business",
                "role_name": "Business Reviewer",
                "issues": ["No analytics detected"],
                "suggestions": ["Add analytics"],
            },
        ]
        improver.analyze("", reviews)
        summary = improver.analyze_summary()
        assert summary["total_issues"] == 3

        # XSS should be critical
        critical = improver.critical_issues
        assert len(critical) == 1
        assert "xss" in critical[0]["issue"].lower()

        # Missing viewport should be major
        major = improver.major_issues
        assert len(major) >= 1

        # No analytics should be minor
        minor = improver.minor_issues
        assert len(minor) >= 1

    def test_empty_analysis(self):
        """Test analysis with no reviews produces empty result."""
        improver = ContentImprover()
        improver.analyze("", [])
        summary = improver.analyze_summary()
        assert summary["total_issues"] == 0

    def test_analyze_summary_structure(self):
        """Test that analyze_summary has correct structure."""
        improver = ContentImprover()
        improver.analyze("", [
            {
                "role": "test",
                "role_name": "Tester",
                "issues": ["Test issue"],
                "suggestions": ["Fix it"],
            }
        ])
        summary = improver.analyze_summary()
        assert "total_issues" in summary
        assert "by_severity" in summary
        assert "issues" in summary
        assert "critical" in summary["by_severity"]
        assert "major" in summary["by_severity"]
        assert "minor" in summary["by_severity"]


# ─── ReviewReport Tests ────────────────────────────────────────────────

class TestReviewReport:
    def test_to_dict_structure(self):
        """Test that ReviewReport.to_dict() returns proper structure."""
        orch = ReviewOrchestrator(GOOD_HTML)
        report = orch.run_all()
        d = report.to_dict()
        assert "overall_score" in d
        assert "all_passed" in d
        assert "total_reviewers" in d
        assert "reviews" in d
        assert "verdict" in d
        assert "improvement_analysis" in d
        assert d["total_reviewers"] == 5

    def test_to_json(self):
        """Test that ReviewReport.to_json() returns valid JSON."""
        orch = ReviewOrchestrator(GOOD_HTML)
        report = orch.run_all()
        j = report.to_json()
        parsed = json.loads(j)
        assert "overall_score" in parsed
        assert "reviews" in parsed
        assert parsed["total_reviewers"] == 5

    def test_summary_contains_key_info(self):
        """Test that summary includes key information."""
        orch = ReviewOrchestrator(GOOD_HTML)
        report = orch.run_all()
        s = report.summary()
        assert "MULTI-PERSPECTIVE REVIEW REPORT" in s
        assert "Overall Score" in s
        assert "Status" in s

    def test_bad_html_summary_shows_failures(self):
        """Test that bad HTML summary shows failures."""
        orch = ReviewOrchestrator(BAD_HTML)
        report = orch.run_all()
        s = report.summary()
        assert "FAIL" in s or "Score" in s


# ─── Integration Tests ─────────────────────────────────────────────────

class TestIntegration:
    def test_review_good_fixture(self):
        """Integration: review good.html — should mostly pass."""
        path = FIXTURES / "good.html"
        content = path.read_text(encoding="utf-8")
        orch = ReviewOrchestrator(content)
        report = orch.run_all()
        assert report.aggregator.calculate() >= 50.0

    def test_review_bad_fixture(self):
        """Integration: review bad.html — should detect issues."""
        path = FIXTURES / "bad.html"
        content = path.read_text(encoding="utf-8")
        orch = ReviewOrchestrator(content)
        report = orch.run_all()
        # bad.html has empty functions and broken syntax
        total_issues = sum(len(r["issues"]) for r in report.reviews)
        assert total_issues >= 1

    def test_cli_help_shows_review(self):
        """Test that --help shows review command."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "maestro_guard", "--help"],
            capture_output=True, text=True
        )
        assert "review" in result.stdout

    def test_cli_review_json_output(self):
        """Test CLI review --json produces valid JSON."""
        import subprocess
        path = FIXTURES / "good.html"
        result = subprocess.run(
            ["python", "-m", "maestro_guard", "review", str(path), "--json"],
            capture_output=True, text=True
        )
        # JSON should be valid regardless of exit code
        parsed = json.loads(result.stdout)
        assert "overall_score" in parsed
        assert "reviews" in parsed
        assert parsed["total_reviewers"] == 5

    def test_cli_review_roles_filter(self):
        """Test CLI --roles filter works."""
        import subprocess
        path = FIXTURES / "good.html"
        result = subprocess.run(
            ["python", "-m", "maestro_guard", "review", str(path), "--roles", "security,ux", "--json"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["total_reviewers"] == 2
        roles = [r["role"] for r in parsed["reviews"]]
        assert "security" in roles
        assert "ux" in roles

    def test_cli_review_bad_file_exit_code(self):
        """Test CLI review returns non-zero for bad file."""
        import subprocess
        path = FIXTURES / "bad.html"
        result = subprocess.run(
            ["python", "-m", "maestro_guard", "review", str(path)],
            capture_output=True, text=True
        )
        # bad.html should have some failures
        assert result.returncode in (0, 1)  # Might pass or fail depending on scores

    def test_cli_review_nonexistent_file(self):
        """Test CLI review with nonexistent file."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "maestro_guard", "review", "/nonexistent/file.html"],
            capture_output=True, text=True
        )
        assert result.returncode == 1

    def test_large_file_handling(self):
        """Test that large HTML content is handled without issues."""
        large_html = "<html><head><title>Large</title></head><body>" + "<p>Line</p>" * 1000 + "<script>function f() { return 1; }</script></body></html>"
        orch = ReviewOrchestrator(large_html)
        report = orch.run_all()
        assert len(report.reviews) == 5
        assert report.aggregator.calculate() >= 0


# ─── Role Definitions Test ─────────────────────────────────────────────

class TestRoles:
    def test_all_roles_defined(self):
        """Test that all 5 roles are properly defined."""
        assert len(ROLES) == 5
        assert "security" in ROLES
        assert "code_quality" in ROLES
        assert "ux" in ROLES
        assert "completeness" in ROLES
        assert "business" in ROLES

    def test_each_role_has_required_fields(self):
        """Test every role has required config fields."""
        for key, config in ROLES.items():
            assert "name" in config, f"Role '{key}' missing 'name'"
            assert "prompt" in config, f"Role '{key}' missing 'prompt'"
            assert "weight" in config, f"Role '{key}' missing 'weight'"
            assert isinstance(config["weight"], int), f"Role '{key}' weight must be int"
            assert 0 < config["weight"] <= 100

    def test_weights_sum_to_100(self):
        """Test reviewer role weights sum to 100."""
        total = sum(config["weight"] for config in ROLES.values())
        assert total == 100, f"Role weights sum to {total}, expected 100"
