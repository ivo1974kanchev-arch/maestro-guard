"""Sandbox runner — executes maestro-guard dynamic checks in isolated Docker containers.

Provides secure sandboxed execution for untrusted AI-generated HTML/JS:
- Network isolation (--network none)
- Read-only filesystem
- No root (non-root user)
- Memory/CPU limits
- Automatic cleanup

Usage:
    from maestro_guard.sandbox.runner import SandboxRunner

    runner = SandboxRunner()
    result = runner.run_check(html_content, spec_content)
    print(result.passed, result.detail, result.suggestion)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Path to the Dockerfile (relative to this file)
DOCKERFILE_DIR = Path(__file__).parent
DEFAULT_IMAGE_TAG = "maestro-guard-sandbox:latest"

# Resource limits for sandboxed containers
DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = 1.0
DEFAULT_TIMEOUT = 60  # seconds


@dataclass
class SandboxResult:
    """Result from a sandboxed check run.

    Attributes:
        passed: Whether all checks passed.
        detail: Human-readable result detail.
        suggestion: Fix suggestion (if failed).
        stdout: Raw container stdout.
        stderr: Raw container stderr.
        duration_ms: Wall clock time for the run.
    """
    passed: bool = False
    detail: str = ""
    suggestion: str = ""
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class SandboxRunner:
    """Runs maestro-guard dynamic checks in isolated Docker containers.

    Args:
        image_tag: Docker image tag to use.
        memory: Container memory limit (e.g., '512m', '1g').
        cpus: CPU limit (e.g., 1.0 = 1 core).
        timeout: Max seconds for container execution.
        docker_path: Path to docker binary.
    """

    def __init__(
        self,
        image_tag: str = DEFAULT_IMAGE_TAG,
        memory: str = DEFAULT_MEMORY,
        cpus: float = DEFAULT_CPUS,
        timeout: int = DEFAULT_TIMEOUT,
        docker_path: str = "docker",
    ):
        self.image_tag = image_tag
        self.memory = memory
        self.cpus = cpus
        self.timeout = timeout
        self.docker_path = docker_path

    # ── Image management ────────────────────────────────────────────────

    def build_image(self, force: bool = False) -> bool:
        """Build the sandbox Docker image.

        Args:
            force: If True, rebuild even if image exists.

        Returns:
            True if build succeeded, False otherwise.
        """
        if not force:
            # Check if image already exists
            result = subprocess.run(
                [self.docker_path, "images", "-q", self.image_tag],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout.strip():
                return True

        # Build the sdist first
        print("Building maestro-guard sdist...", file=sys.stderr)
        build_result = subprocess.run(
            [sys.executable, "-m", "build", "--sdist", str(DOCKERFILE_DIR.parent.parent)],
            capture_output=True, text=True, timeout=120,
        )
        if build_result.returncode != 0:
            print(f"Build failed: {build_result.stderr}", file=sys.stderr)
            return False

        # Find the .tar.gz in dist/
        dist_dir = Path(DOCKERFILE_DIR.parent.parent) / "dist"
        wheels = sorted(dist_dir.glob("maestro_guard-*.tar.gz"))
        if not wheels:
            print("No sdist found in dist/", file=sys.stderr)
            return False

        # Copy the sdist to the sandbox dir so Docker build context has it
        shutil.copy(str(wheels[-1]), str(DOCKERFILE_DIR / "dist"))

        try:
            result = subprocess.run(
                [self.docker_path, "build", "-t", self.image_tag, "-f",
                 str(DOCKERFILE_DIR / "Dockerfile"), str(DOCKERFILE_DIR)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                print(f"Docker build failed: {result.stderr}", file=sys.stderr)
                return False
            return True
        finally:
            # Clean up copied sdist
            whl_in_sandbox = DOCKERFILE_DIR / "dist"
            if whl_in_sandbox.exists():
                shutil.rmtree(whl_in_sandbox)

    def image_exists(self) -> bool:
        """Check if the sandbox image has been built."""
        result = subprocess.run(
            [self.docker_path, "images", "-q", self.image_tag],
            capture_output=True, text=True, timeout=15,
        )
        return bool(result.stdout.strip())

    # ── Execution ────────────────────────────────────────────────────────

    def run_check(
        self,
        html_content: str,
        spec_content: str,
        timeout: Optional[int] = None,
        quiet: bool = True,
    ) -> SandboxResult:
        """Run a dynamic spec check in a sandboxed container.

        Args:
            html_content: The HTML content to verify.
            spec_content: The markdown spec content.
            timeout: Override default timeout (seconds).
            quiet: If True, suppress subprocess output.

        Returns:
            SandboxResult with execution results.
        """
        import time
        start = time.time()

        if not self.image_exists():
            ok = self.build_image(force=False)
            if not ok:
                return SandboxResult(
                    passed=False,
                    detail="Sandbox image could not be built",
                    suggestion="Build the sandbox image first: python -m maestro_guard.sandbox.runner --build",
                    errors=["Docker image build failed"],
                )

        # Create temp directory with HTML + spec
        tmpdir = tempfile.mkdtemp(prefix="maestro-sandbox-")
        try:
            html_path = os.path.join(tmpdir, "index.html")
            spec_path = os.path.join(tmpdir, "spec.md")

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(spec_content)

            # Build Docker run command
            cmd = [
                self.docker_path, "run", "--rm",
                "--network", "none",
                "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "-m", self.memory,
                "--cpus", str(self.cpus),
                "-v", f"{tmpdir}:/work:ro",
                self.image_tag,
                "check", "/work/index.html",
                "--exec-spec", "/work/spec.md",
                "--json",
            ]

            # Add container timeout
            effective_timeout = timeout or self.timeout

            proc = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=effective_timeout,
            )

            duration_ms = (time.time() - start) * 1000
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            # Parse JSON output
            if proc.returncode in (0, 1) and stdout:
                try:
                    data = json.loads(stdout)
                    all_passed = data.get("all_passed", False)
                    checks = data.get("checks", [])
                    detail_parts = []
                    suggestion_parts = []
                    for check in checks:
                        name = check.get("name", "unknown")
                        passed = check.get("passed", False)
                        detail_parts.append(f"{name}: {'PASS' if passed else 'FAIL'}")
                        if not passed:
                            d = check.get("detail", "")
                            s = check.get("suggestion", "")
                            if d and d not in detail_parts:
                                detail_parts.append(f"  {d}")
                            if s:
                                suggestion_parts.append(s)

                    return SandboxResult(
                        passed=all_passed,
                        detail=" | ".join(detail_parts) if detail_parts else stdout,
                        suggestion=" | ".join(suggestion_parts) if suggestion_parts else "",
                        stdout=stdout,
                        stderr=stderr,
                        duration_ms=duration_ms,
                    )
                except json.JSONDecodeError:
                    # Try line-by-line JSON (directory mode outputs one JSON per line)
                    for line in stdout.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("all_passed") is False or data.get("summary"):
                                return SandboxResult(
                                    passed=False,
                                    detail=f"Check failed: {data.get('checks', [{}])}",
                                    stdout=stdout,
                                    stderr=stderr,
                                    duration_ms=duration_ms,
                                )
                        except json.JSONDecodeError:
                            continue
                    return SandboxResult(
                        passed=True,
                        detail=stdout[:200] if stdout else "No output",
                        stdout=stdout,
                        stderr=stderr,
                        duration_ms=duration_ms,
                    )
            elif proc.returncode == 124:
                # Timeout
                return SandboxResult(
                    passed=False,
                    detail="Sandbox execution timed out",
                    suggestion="The AI-generated code may contain an infinite loop or long-running operation",
                    stdout=stdout,
                    stderr=stderr,
                    errors=["Container timed out"],
                    duration_ms=duration_ms,
                )
            else:
                return SandboxResult(
                    passed=False,
                    detail=f"Container exited with code {proc.returncode}",
                    stderr=stderr or stdout,
                    errors=[stderr or stdout],
                    duration_ms=duration_ms,
                )

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start) * 1000
            return SandboxResult(
                passed=False,
                detail="Sandbox execution timed out",
                errors=["Container timed out"],
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            return SandboxResult(
                passed=False,
                detail="Docker not found",
                suggestion="Install Docker to use sandboxed execution",
                errors=["Docker binary not found"],
            )
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            return SandboxResult(
                passed=False,
                detail=f"Sandbox execution error: {exc}",
                errors=[str(exc)],
                duration_ms=duration_ms,
            )
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass


# ── CLI entry point ─────────────────────────────────────────────────────

def main():
    """CLI entry point for sandbox management."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="maestro-guard-sandbox",
        description="Manage the maestro-guard sandbox Docker image.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the sandbox Docker image",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild of sandbox image",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if sandbox image exists",
    )

    args = parser.parse_args()
    runner = SandboxRunner()

    if args.check:
        exists = runner.image_exists()
        print(f"Sandbox image exists: {exists}")
        sys.exit(0 if exists else 1)

    if args.build:
        print("Building sandbox image...")
        ok = runner.build_image(force=args.force)
        if ok:
            print(f"✅ Sandbox image built: {DEFAULT_IMAGE_TAG}")
        else:
            print("❌ Failed to build sandbox image")
            sys.exit(1)

    if not args.build and not args.check:
        parser.print_help()


if __name__ == "__main__":
    main()
