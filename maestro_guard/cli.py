"""CLI entry point for maestro-guard — pure Python stdlib.

Usage:
    maestro-guard check <filepath> [--spec SPEC.md] [--json] [--verbose]
    maestro-guard check <directory> [--spec SPEC.md] [--json] [--verbose]
    maestro-guard review <filepath> [--roles ROLES] [--json] [--verbose] [--improve]
    maestro-guard --version
    maestro-guard --help
"""

import argparse
import json
import os
import sys

from maestro_guard.report import GuardianReport
from maestro_guard.checks.js_syntax import verify_js_syntax
from maestro_guard.checks.handlers import verify_handlers
from maestro_guard.checks.dom_refs import verify_dom_refs
from maestro_guard.checks.console_errors import verify_console_errors
from maestro_guard.checks.fulfillment import verify_fulfillment
from maestro_guard.checks.dynamic import verify_dynamic
from maestro_guard.review import ReviewOrchestrator
from maestro_guard.sandbox.runner import SandboxRunner, SandboxResult

VERSION = "0.2.0"
PROG = "maestro-guard"

# Weight and display-name configuration for each check
CHECK_CONFIG = [
    # (check_key, display_name, weight, verify_func, needs_spec, needs_exec_spec)
    ("js_syntax", "js_syntax", 25, verify_js_syntax, False, False),
    ("handlers_defined", "handlers", 25, verify_handlers, False, False),
    ("dom_refs", "dom_refs", 20, verify_dom_refs, False, False),
    ("no_console_errors", "console_errors", 15, verify_console_errors, False, False),
    ("fulfillment", "fulfillment", 10, verify_fulfillment, True, False),
    ("dynamic_spec", "dynamic_spec", 25, verify_dynamic, False, True),
]

# ── Pretty printer ──────────────────────────────────────────────────────

BANNER = (
    "  ╔══════════════════════════════════════════╗\n"
    "  ║         MAESTRO GUARD v{ver:<11}║\n"
    "  ║   AI Code Verification Tool             ║\n"
    "  ╚══════════════════════════════════════════╝"
)

SEPARATOR = "  " + "─" * 39


def _format_check(display_name: str, passed: bool, earned: int, total: int, detail: str, suggestion: str = "") -> str:
    """Format a single check line like: [PASS]  js_syntax:        25/25  ✓  ..."""
    status = "PASS" if passed else "FAIL"
    icon = "✓" if passed else "✗"
    score_str = f"{earned}/{total}"
    # Pad the name to align all scores
    padded_name = display_name.ljust(16)
    line = f"  [{status}]  {padded_name}{score_str}  {icon}  {detail}"
    if not passed and suggestion:
        line += "\n" + " " * 8 + suggestion
    return line


def _print_pretty(results: list[dict], earned: int, max_score: int) -> None:
    """Print the styled box + check results + score summary."""
    # Banner
    print(BANNER.format(ver=VERSION))
    print()

    # Each check
    for r in results:
        print(_format_check(
            r["display_name"],
            r["passed"],
            r["earned_weight"],
            r["max_weight"],
            r["detail"],
            r.get("suggestion", ""),
        ))

    # Separator
    print(SEPARATOR)

    # Score line
    failures = [r for r in results if not r["passed"]]
    if failures:
        failed_names = ", ".join(r["display_name"] for r in failures)
        if earned == max_score:
            print(f"  Score: {earned}/{max_score}  ❌ ISSUES DETECTED  (all weight lost to mandatory failures)")
        else:
            print(f"  Score: {earned}/{max_score}  ❌ ISSUES DETECTED")
        print(f"  Failed checks: {failed_names}")
    else:
        print(f"  Score: {earned}/{max_score}  ✅ ALL CHECKS PASSED")

    print()


def _output_json(results: list[dict], earned: int, max_score: int) -> None:
    """Print JSON output."""
    out = {
        "version": VERSION,
        "score": earned,
        "max_score": max_score,
        "all_passed": earned == max_score and all(r["passed"] for r in results),
        "checks": [
            {
                "name": r["display_name"],
                "passed": r["passed"],
                "earned_weight": r["earned_weight"],
                "max_weight": r["max_weight"],
                "detail": r["detail"],
                "suggestion": r.get("suggestion", ""),
                "issues": r.get("issues", []),
            }
            for r in results
        ],
        "failing_checks": [
            r["display_name"] for r in results if not r["passed"]
        ],
    }
    print(json.dumps(out, indent=2))


def _read_file_safe(path: str, label: str) -> str:
    """Read a file and return its content, exiting on error."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        print(f"Error: {label} not found: {path}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied reading {label}: {path}", file=sys.stderr)
        sys.exit(1)
    except IsADirectoryError:
        print(f"Error: {label} path is a directory: {path}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError:
        print(f"Error: {label} is not valid UTF-8 text (possibly binary): {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"Error: Cannot read {label} '{path}': {exc}", file=sys.stderr)
        sys.exit(1)


def _run_single_check(filepath: str, spec_content: str | None, args: argparse.Namespace) -> tuple[list[dict], int, int]:
    """Run all checks on a single HTML file and return (results, earned, max_score)."""
    html_content = _read_file_safe(filepath, "HTML file")

    # Read exec spec content if provided
    exec_spec_content = None
    if hasattr(args, "exec_spec") and args.exec_spec:
        exec_spec_content = _read_file_safe(args.exec_spec, "Exec spec file")

    # ── Sandbox mode: run entire check inside Docker ──
    if getattr(args, "sandbox", False):
        return _run_sandbox_check(filepath, html_content, spec_content, exec_spec_content, args)

    results: list[dict] = []
    earned = 0
    max_score = 0

    for check_key, display_name, weight, verify_func, needs_spec, needs_exec_spec in CHECK_CONFIG:
        # Skip fulfillment if no spec provided
        if needs_spec and spec_content is None:
            if args.verbose:
                print(f"  [SKIP]  {display_name}  (no spec provided)", file=sys.stderr)
            continue

        # Skip dynamic spec check if no exec-spec provided
        if needs_exec_spec and exec_spec_content is None:
            if args.verbose:
                print(f"  [SKIP]  {display_name}  (no --exec-spec provided)", file=sys.stderr)
            continue

        max_score += weight

        try:
            if needs_spec:
                passed, detail, suggestion = verify_func(html_content, spec_content)
            elif needs_exec_spec:
                passed, detail, suggestion = verify_func(html_content, exec_spec_content)
            else:
                passed, detail, suggestion = verify_func(html_content)
        except Exception as exc:
            passed = False
            detail = f"Check raised an exception: {exc}"
            suggestion = ""

        earned_weight = weight if passed else 0
        earned += earned_weight

        results.append({
            "check_key": check_key,
            "display_name": display_name,
            "passed": passed,
            "earned_weight": earned_weight,
            "max_weight": weight,
            "detail": detail,
            "suggestion": suggestion,
            "issues": [detail] if not passed and detail else [],
        })

    return results, earned, max_score


def _run_sandbox_check(
    filepath: str,
    html_content: str,
    spec_content: str | None,
    exec_spec_content: str | None,
    args: argparse.Namespace,
) -> tuple[list[dict], int, int]:
    """Run checks inside a Docker sandbox."""
    runner = SandboxRunner()

    if exec_spec_content:
        # Dynamic spec check inside sandbox
        result = runner.run_check(html_content, exec_spec_content)
    else:
        # Static checks inside sandbox (run maestro-guard without --exec-spec)
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="maestro-sandbox-cli-")
        import os
        html_path = os.path.join(tmpdir, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        spec_arg = ""
        if spec_content:
            spec_path = os.path.join(tmpdir, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(spec_content)
            spec_arg = " --spec /work/spec.md"
        import subprocess
        import shutil
        cmd = (
            f"{runner.docker_path} run --rm --network none --read-only "
            f"--cap-drop ALL --security-opt no-new-privileges "
            f"-m {runner.memory} --cpus {runner.cpus} "
            f"-v {tmpdir}:/work:ro "
            f"{runner.image_tag} check /work/index.html{spec_arg} --json"
        )
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=runner.timeout,
        )
        shutil.rmtree(tmpdir, ignore_errors=True)

        if proc.returncode not in (0, 1):
            return _sandbox_error_result(proc.stderr or proc.stdout)

        import json
        try:
            data = json.loads(proc.stdout)
            checks = data.get("checks", [])
            max_score = data.get("max_score", 100)
            earned = data.get("score", 0)
            results = []
            for c in checks:
                results.append({
                    "check_key": c.get("name", "unknown"),
                    "display_name": c.get("name", "unknown"),
                    "passed": c.get("passed", False),
                    "earned_weight": c.get("earned_weight", c.get("max_weight", 0) if c.get("passed") else 0),
                    "max_weight": c.get("max_weight", 0),
                    "detail": c.get("detail", ""),
                    "suggestion": c.get("suggestion", ""),
                    "issues": c.get("issues", []),
                })
            return results, earned, max_score
        except (json.JSONDecodeError, KeyError) as exc:
            return _sandbox_error_result(f"Failed to parse sandbox output: {exc}")

    # Parse SandboxResult into check results
    results = []
    max_score = 0
    earned = 0

    # If we got structured JSON from the sandbox result
    if result.stdout:
        try:
            data = json.loads(result.stdout)
            checks = data.get("checks", [])
            max_score = data.get("max_score", 100)
            earned = data.get("score", 0)
            for c in checks:
                results.append({
                    "check_key": c.get("name", "unknown"),
                    "display_name": c.get("name", "unknown"),
                    "passed": c.get("passed", False),
                    "earned_weight": c.get("earned_weight", c.get("max_weight", 0) if c.get("passed") else 0),
                    "max_weight": c.get("max_weight", 0),
                    "detail": c.get("detail", ""),
                    "suggestion": c.get("suggestion", ""),
                    "issues": c.get("issues", []),
                })
            return results, earned, max_score
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: reconstruct from SandboxResult
    dynamic_weight = 25
    max_score = dynamic_weight
    passed = result.passed
    earned = dynamic_weight if passed else 0
    results.append({
        "check_key": "dynamic_spec",
        "display_name": "dynamic_spec",
        "passed": passed,
        "earned_weight": earned,
        "max_weight": dynamic_weight,
        "detail": result.detail,
        "suggestion": result.suggestion,
        "issues": [] if passed else [result.detail],
    })
    return results, earned, max_score


def _sandbox_error_result(error_msg: str) -> tuple[list[dict], int, int]:
    """Return an error result when sandbox execution fails."""
    results = [{
        "check_key": "sandbox",
        "display_name": "sandbox",
        "passed": False,
        "earned_weight": 0,
        "max_weight": 100,
        "detail": f"Sandbox execution failed: {error_msg[:200]}",
        "suggestion": "Ensure Docker is running and the sandbox image is built",
        "issues": [error_msg],
    }]
    return results, 0, 100


# ── Commands ────────────────────────────────────────────────────────────

def cmd_check(args: argparse.Namespace) -> None:
    """Run the ``check`` subcommand."""

    filepath = args.filepath

    # 1. Check if path is a directory
    if os.path.isdir(filepath):
        _cmd_check_dir(args, filepath)
        return

    # 2. Optionally read spec file
    spec_content = None
    if args.spec:
        spec_content = _read_file_safe(args.spec, "Spec file")

    # 3. Run all checks on single file
    results, earned, max_score = _run_single_check(filepath, spec_content, args)

    # 4. Output
    if args.json:
        _output_json(results, earned, max_score)
    else:
        print(f"\n  File: {filepath}")
        _print_pretty(results, earned, max_score)

    # 5. Exit code
    failures = [r for r in results if not r["passed"]]
    sys.exit(1 if failures else 0)


def cmd_review(args: argparse.Namespace) -> None:
    """Run the ``review`` subcommand."""

    filepath = args.filepath

    # 1. Check it's a file
    if os.path.isdir(filepath):
        print(f"Error: review requires a single file, not a directory: {filepath}", file=sys.stderr)
        sys.exit(1)

    # 2. Read HTML content
    html_content = _read_file_safe(filepath, "HTML file")

    # 3. Parse roles
    roles = None
    if args.roles:
        roles = [r.strip() for r in args.roles.split(",") if r.strip()]

    # 4. Run orchestrator
    try:
        orchestrator = ReviewOrchestrator(html_content, roles=roles)
        report = orchestrator.run_all()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Output
    if args.json:
        print(report.to_json())
    elif args.improve:
        d = report.to_dict()
        analysis = d.get("improvement_analysis", {})
        print(json.dumps(analysis, indent=2))
    else:
        print(f"\n  File: {filepath}")
        print(report.summary())

    # 6. Exit code
    sys.exit(0 if report.aggregator.all_passed else 1)


def _cmd_check_dir(args: argparse.Namespace, dirpath: str) -> None:
    """Run checks on all .html files in a directory recursively."""
    # Find all .html files recursively
    html_files = []
    for root, dirs, files in os.walk(dirpath):
        for fname in files:
            if fname.endswith(".html"):
                html_files.append(os.path.join(root, fname))

    html_files.sort()

    if not html_files:
        print(f"No .html files found in {dirpath}", file=sys.stderr)
        sys.exit(1)

    # Read spec once (shared across all files)
    spec_content = None
    if args.spec:
        spec_content = _read_file_safe(args.spec, "Spec file")

    passed_count = 0
    failed_count = 0

    for html_file in html_files:
        results, earned, max_score = _run_single_check(html_file, spec_content, args)
        failures = [r for r in results if not r["passed"]]

        if failures:
            failed_count += 1
        else:
            passed_count += 1

        if args.json:
            # For JSON mode, print each file's results as a JSON array element
            out = {
                "file": html_file,
                "score": earned,
                "max_score": max_score,
                "all_passed": not failures,
                "checks": [
                    {
                        "name": r["display_name"],
                        "passed": r["passed"],
                        "earned_weight": r["earned_weight"],
                        "max_weight": r["max_weight"],
                        "detail": r["detail"],
                        "suggestion": r.get("suggestion", ""),
                        "issues": r.get("issues", []),
                    }
                    for r in results
                ],
            }
            print(json.dumps(out))
        else:
            print(f"\n  File: {html_file}")
            _print_pretty(results, earned, max_score)

    # Print summary
    total = len(html_files)
    if args.json:
        # Already printed individual JSON, now print summary as a JSON line
        summary = {
            "summary": True,
            "total_files": total,
            "passed": passed_count,
            "failed": failed_count,
        }
        print(json.dumps(summary))
    else:
        print(f"  Checked {total} files: {passed_count} passed, {failed_count} failed")
        print()

    sys.exit(1 if failed_count > 0 else 0)


# ── Argument parser ─────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="AI Code Verification Tool — validates HTML/JS against quality and spec checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s check index.html\n"
            "  %(prog)s check index.html --spec spec.md --verbose\n"
            "  %(prog)s check index.html --json\n"
            "  %(prog)s check ./dir/          # check all .html files recursively\n"
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True  # Actually no, we make it not required so --version/--help work standalone

    # ``check`` subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Run all verification checks on an HTML file or directory.",
        description="Run all verification checks on an HTML file or directory and print results.",
    )
    check_parser.add_argument(
        "filepath",
        metavar="FILEPATH",
        help="Path to the HTML file or directory to verify.",
    )
    check_parser.add_argument(
        "--spec",
        metavar="SPEC.md",
        default=None,
        help="Path to a spec/markdown file for fulfillment checking.",
    )
    check_parser.add_argument(
        "--exec-spec",
        metavar="EXEC_SPEC.md",
        default=None,
        help="Path to a dynamic execution spec to verify runtime behavior (requires Playwright).",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of pretty-printed text.",
    )
    check_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional diagnostic information (e.g., skipped checks).",
    )

    # ``review`` subcommand
    review_parser = subparsers.add_parser(
        "review",
        help="Run multi-perspective review on an HTML file.",
        description="Analyze HTML/JS from 5 expert perspectives (security, code quality, UX, completeness, business viability).",
    )
    review_parser.add_argument(
        "filepath",
        metavar="FILEPATH",
        help="Path to the HTML file to review.",
    )
    review_parser.add_argument(
        "--roles",
        metavar="ROLES",
        default=None,
        help="Comma-separated list of roles: security,code_quality,ux,completeness,business",
    )
    review_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of pretty-printed text.",
    )
    review_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional diagnostic information.",
    )
    review_parser.add_argument(
        "--improve",
        action="store_true",
        help="Output improvement analysis (prints structured report of what to change).",
    )

    return parser


def main() -> None:
    """Main CLI entry point.  Called by setuptools console_scripts or ``python -m``."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "review":
        cmd_review(args)
    else:
        # Should not happen with argparse normally, but guard anyway
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
