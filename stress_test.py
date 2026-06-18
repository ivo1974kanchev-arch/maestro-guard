#!/usr/bin/env python3
"""
maestro-guard Stress Test Suite — comprehensive fuzzing & edge-case testing.

Tests categories 1-10 as specified. Reports CRITICAL, MODERATE, MINOR issues.
"""

import os
import sys
import subprocess
import tempfile
import time
import json
import signal
import struct
import math
import zipfile
import io
import traceback

# Add project to path
BASE_DIR = "/root/maestro-guard"
sys.path.insert(0, BASE_DIR)

CLI_CMD = [sys.executable, "-m", "maestro_guard.cli", "check"]
RESULTS = {
    "critical": [],
    "moderate": [],
    "minor": [],
    "info": [],
}

def run_cli(filepath: str, extra_args: list = None) -> dict:
    """Run maestro-guard CLI and return results."""
    cmd = CLI_CMD + [filepath]
    if extra_args:
        cmd += extra_args
    
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=BASE_DIR,
        )
        elapsed = time.time() - start
        
        # Parse JSON output if present
        json_result = None
        stdout = proc.stdout
        stderr = proc.stderr
        
        # Try to find JSON in stdout
        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    json_result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        
        # Parse pretty output
        passed = None
        if json_result:
            passed = json_result.get("all_passed", False)
        else:
            passed = "ALL CHECKS PASSED" in stdout
        
        return {
            "exit_code": proc.returncode,
            "passed": passed,
            "stdout": stdout,
            "stderr": stderr,
            "json": json_result,
            "elapsed": elapsed,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "passed": None,
            "stdout": "",
            "stderr": "TIMEOUT",
            "json": None,
            "elapsed": 30,
            "timed_out": True,
        }
    except Exception as e:
        return {
            "exit_code": -2,
            "passed": None,
            "stdout": "",
            "stderr": f"EXCEPTION: {e}\n{traceback.format_exc()}",
            "json": None,
            "elapsed": 0,
            "timed_out": False,
            "exception": str(e),
        }


def record_issue(severity: str, category: str, test_name: str, issue: str, detail: str = ""):
    """Record a finding."""
    entry = {
        "test": test_name,
        "category": category,
        "issue": issue,
        "detail": detail,
    }
    RESULTS[severity].append(entry)
    icon = {"critical": "🔴", "moderate": "🟡", "minor": "🔵", "info": "ℹ️"}[severity]
    print(f"  {icon} [{severity.upper()}] {test_name}: {issue}")
    if detail:
        for line in detail.split('\n'):
            print(f"     {line}")


def analyze_result(test_name: str, result: dict, expected_fail: bool = None, expected_exit: int = None):
    """Analyze a test result for failures."""
    if result.get("timed_out"):
        record_issue("critical", "performance", test_name,
                     "Command timed out (30s) — hangs on input",
                     f"stdout: {result['stdout'][:200]}")
        return
    
    if result.get("exception"):
        record_issue("critical", "crash", test_name,
                     f"Unhandled exception: {result['exception']}",
                     result['stderr'][:500])
        return
    
    exit_code = result["exit_code"]
    passed = result["passed"]
    
    # Check for crash (exit code -2 or non-zero with traceback in stderr)
    if exit_code == -2:
        record_issue("critical", "crash", test_name,
                     "Process crashed with exception",
                     result['stderr'][:500])
        return
    
    # Check for unhandled exception in output
    stderr = result.get("stderr", "")
    stdout = result.get("stdout", "")
    if "Traceback (most recent call last)" in stderr or "Traceback (most recent call last)" in stdout:
        tb = (stderr + stdout)[:500]
        record_issue("critical", "crash", test_name,
                     "Unhandled traceback in output",
                     tb)
        return
    
    # Check exit code consistency
    if expected_exit is not None and exit_code != expected_exit:
        record_issue("moderate", "consistency", test_name,
                     f"Unexpected exit code: got {exit_code}, expected {expected_exit}",
                     f"passed={passed}")
    
    # Check logical correctness
    if expected_fail is not None:
        if expected_fail and passed:
            record_issue("critical", "logic", test_name,
                         "Should have FAILED but got PASS (false negative)",
                         f"Expected FAIL, got PASS. exit_code={exit_code}")
        elif not expected_fail and not passed:
            record_issue("moderate", "logic", test_name,
                         "Should have PASSED but got FAIL (false positive)",
                         f"Expected PASS, got FAIL. exit_code={exit_code}")
    
    # Check consistency: exit code should match pass/fail
    if passed is not None:
        if passed and exit_code != 0:
            record_issue("moderate", "consistency", test_name,
                         f"Exit code {exit_code} but result shows PASS",
                         f"stdout={stdout[:200]}")
        elif not passed and exit_code == 0:
            record_issue("moderate", "consistency", test_name,
                         f"Exit code 0 but result shows FAIL",
                         f"stdout={stdout[:200]}")


# ============================================================
# TEST GENERATORS
# ============================================================

def test_1_pathological_html():
    """Pathological HTML tests."""
    print("\n# [1] Pathological HTML")
    
    # 1a: Deeply nested DOM (10K levels)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body>")
        for i in range(10000):
            f.write(f"<div id='d{i}'>")
        f.write("X")
        for i in range(10000):
            f.write("</div>")
        f.write("</body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("1a: 10K nested DOM levels", result, expected_fail=False)
    os.unlink(path)
    
    # 1b: Deeply nested with script blocks inside
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body>")
        for i in range(1000):
            f.write(f"<div><script>var x{i}=1;</script>")
        for i in range(1000):
            f.write("</div>")
        f.write("</body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("1b: 1000 nested script blocks", result, expected_fail=False)
    os.unlink(path)
    
    # 1c: Unclosed tags throughout
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><div><p><span><a><script>let x=1;</script>")
        path = f.name
    result = run_cli(path)
    analyze_result("1c: Unclosed tags", result, expected_fail=False)
    os.unlink(path)
    
    # 1d: Mixed encoding (Latin-1 chars)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let café = 1; let groß = 2;</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("1d: Mixed encoding / extended Latin", result, expected_fail=False)
    os.unlink(path)
    
    # 1e: BOM character at start
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'\xef\xbb\xbf<html><body><script>let x=1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1e: BOM character prefix", result, expected_fail=False)
    os.unlink(path)
    
    # 1f: Null bytes in HTML (binary embedded)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'<html><body><script>let x=\x00\x01\x02;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1f: Null bytes in HTML", result)
    os.unlink(path)
    
    # 1g: Unicode escapes in HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>let x = "\\u0041\\u0042";</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1g: Unicode escapes in JS strings", result, expected_fail=False)
    os.unlink(path)
    
    # 1h: Zero-width characters
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        zws = '\u200b\u200c\u200d\u2060\u2061\u2062\u2063'
        f.write(f'<html><body><script>let{zws}x{zws}=1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1h: Zero-width characters in JS", result, expected_fail=False)
    os.unlink(path)
    
    # 1i: Nested script-like strings in JS (embedded </script>)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>let x = "hello</script>"; let y = 1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1i: JS string containing </script>", result)
    os.unlink(path)
    
    # 1j: Script tag with self-closing syntax
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script src="test.js" /><script>let x=1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("1j: Self-closing script tag + inline script", result, expected_fail=False)
    os.unlink(path)
    
    # 1k: HTML with no <script> tags but valid HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Test</title></head>
<body><h1>Hello World</h1><p id="main">Content here</p></body>
</html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("1k: Valid HTML with no scripts", result, expected_fail=False)
    os.unlink(path)


def test_2_pathological_js():
    """Pathological JavaScript tests."""
    print("\n# [2] Pathological JavaScript")
    
    # 2a: 10K levels of nested braces
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        for i in range(10000):
            f.write("{")
        f.write("let x=1;")
        for i in range(10000):
            f.write("}")
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2a: 10K nested braces in JS", result, expected_fail=False)
    os.unlink(path)
    
    # 2b: eval() with complex code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>eval('let x = 1 + 2;');</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2b: eval() usage", result, expected_fail=False)
    os.unlink(path)
    
    # 2c: Function() constructor
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>const f = new Function('return 1+2;');</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2c: Function() constructor", result, expected_fail=False)
    os.unlink(path)
    
    # 2d: Template literals with nested expressions
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x = `hello ${`nested ${`deep ${1+2}`}`}`;</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2d: Nested template literals", result, expected_fail=False)
    os.unlink(path)
    
    # 2e: Unicode variable names
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let \u00e9\u00e0\u00fc = 1; let \u4e2d\u6587 = 2; let \u041f = 3;</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2e: Unicode variable names", result, expected_fail=False)
    os.unlink(path)
    
    # 2f: with() statement
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>with(Math) { let x = PI * 2; }</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2f: with() statement", result, expected_fail=False)
    os.unlink(path)
    
    # 2g: async/await
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>async function foo() { await bar(); }</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2g: async/await", result, expected_fail=False)
    os.unlink(path)
    
    # 2h: Generators
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>function* gen() { yield 1; yield 2; }</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2h: Generator functions", result, expected_fail=False)
    os.unlink(path)
    
    # 2i: Proxy object
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>const p = new Proxy({}, { get(t, k) { return k; } });</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("2i: Proxy objects", result, expected_fail=False)
    os.unlink(path)
    
    # 2j: JS regex literals that look like comments
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>let re = /abc/g; let re2 = /\\/\\//; let x = 1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("2j: Regex literals resembling comments", result, expected_fail=False)
    os.unlink(path)
    
    # 2k: JS with unbalanced braces inside strings (should pass)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>let x = "{unclosed"; let y = "}unmatched";</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("2k: Unbalanced braces inside JS strings", result, expected_fail=False)
    os.unlink(path)
    
    # 2l: Object destructuring with nested braces
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>const {a, b: {c, d}} = obj;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("2l: Nested destructuring", result, expected_fail=False)
    os.unlink(path)
    
    # 2m: Arrow functions with brace confusion
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>const f = x => ({ result: x * 2 }); const g = x => x * 2;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("2m: Arrow functions with object literal", result, expected_fail=False)
    os.unlink(path)
    
    # 2n: Classes with methods
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>class Foo { constructor() { this.x = 1; } bar() { return this.x; } }</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("2n: ES6 class definitions", result, expected_fail=False)
    os.unlink(path)


def test_3_empty_trivial():
    """Empty/trivial input tests."""
    print("\n# [3] Empty/Trivial Inputs")
    
    # 3a: Empty file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("")
        path = f.name
    result = run_cli(path)
    analyze_result("3a: Empty file", result)
    os.unlink(path)
    
    # 3b: Whitespace-only file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("   \n\n  \t  \r\n  ")
        path = f.name
    result = run_cli(path)
    analyze_result("3b: Whitespace-only file", result)
    os.unlink(path)
    
    # 3c: Single character
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("a")
        path = f.name
    result = run_cli(path)
    analyze_result("3c: Single character file", result)
    os.unlink(path)
    
    # 3d: DOCTYPE only
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<!DOCTYPE html>")
        path = f.name
    result = run_cli(path)
    analyze_result("3d: DOCTYPE only", result, expected_fail=False)
    os.unlink(path)
    
    # 3e: Comment only
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<!-- just a comment -->")
        path = f.name
    result = run_cli(path)
    analyze_result("3e: Comment only", result, expected_fail=False)
    os.unlink(path)
    
    # 3f: Just a script tag with no content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script></script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("3f: Empty script tag", result, expected_fail=False)
    os.unlink(path)
    
    # 3g: Script tag with only whitespace
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>   \n\n  </script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("3g: Whitespace-only script block", result, expected_fail=False)
    os.unlink(path)


def test_4_binary_non_html():
    """Binary/non-HTML input tests."""
    print("\n# [4] Binary / Non-HTML Inputs")
    
    # 4a: PNG file (valid PNG header)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        # Minimal valid PNG
        f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        path = f.name
    result = run_cli(path)
    analyze_result("4a: PNG binary (.html extension)", result)
    os.unlink(path)
    
    # 4b: ZIP file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        with zipfile.ZipFile(f, 'w') as zf:
            zf.writestr('test.txt', 'hello')
        f.flush()
        path = f.name
    result = run_cli(path)
    analyze_result("4b: ZIP binary (.html extension)", result)
    os.unlink(path)
    
    # 4c: JSON file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('{"key": "value", "array": [1, 2, 3]}')
        path = f.name
    result = run_cli(path)
    analyze_result("4c: JSON content (.html extension)", result, expected_fail=False)
    os.unlink(path)
    
    # 4d: Raw binary bytes (all 256 values)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(bytes(range(256)))
        path = f.name
    result = run_cli(path)
    analyze_result("4d: Raw bytes 0-255", result)
    os.unlink(path)
    
    # 4e: ELF header (executable file)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'\x7fELF' + b'\x00' * 100)
        path = f.name
    result = run_cli(path)
    analyze_result("4e: ELF executable header", result)
    os.unlink(path)
    
    # 4f: Pure null bytes
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'\x00' * 10000)
        path = f.name
    result = run_cli(path)
    analyze_result("4f: 10K null bytes", result)
    os.unlink(path)
    
    # 4g: UTF-16 encoded file (not valid UTF-8)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write('\u4e2d\u6587'.encode('utf-16-le'))
        path = f.name
    result = run_cli(path)
    analyze_result("4g: UTF-16 encoded (not valid UTF-8)", result)
    os.unlink(path)
    
    # 4h: File with no extension
    with tempfile.NamedTemporaryFile(mode='w', suffix='', delete=False) as f:
        f.write("<html><body><script>let x=1;</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("4h: File with no extension", result, expected_fail=False)
    os.unlink(path)


def test_5_massive_files():
    """Massive file tests."""
    print("\n# [5] Massive Files")
    
    # 5a: 10MB of repeated content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body>")
        chunk = "<div>" + "x" * 1000 + "</div>\n"
        for _ in range(10000):
            f.write(chunk)
        f.write("<script>let x = 1;</script></body></html>")
        path = f.name
    size = os.path.getsize(path)
    print(f"  5a file size: {size} bytes ({size/1024/1024:.1f} MB)")
    result = run_cli(path)
    analyze_result(f"5a: ~{size/1024/1024:.0f}MB file with repeated HTML", result, expected_fail=False)
    os.unlink(path)
    
    # 5b: Single <script> block with massive JS
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        f.write("let x=1;\n" * 100000)
        f.write("let y=2;\n")
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("5b: 100K lines of JS", result, expected_fail=False)
    os.unlink(path)
    
    # 5c: Many <script> tags
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body>")
        for i in range(1000):
            f.write(f"<script>var x{i}=1;</script>\n")
        f.write("</body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("5c: 1000 inline script tags", result, expected_fail=False)
    os.unlink(path)
    
    # 5d: Very long single line
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        f.write("let x=" + "a" * 50000 + ";")
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("5d: 50K char single line JS", result, expected_fail=False)
    os.unlink(path)
    
    # 5e: Massive string literal in JS
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        f.write("let x = '" + "A" * 100000 + "';")
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("5e: 100K char string literal", result, expected_fail=False)
    os.unlink(path)


def test_6_ai_garbage():
    """Real AI garbage simulation."""
    print("\n# [6] AI Garbage Simulation")
    
    # 6a: Hallucinated DOM refs (getElementById for non-existent ids)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<div id="real-id">Content</div>
<script>
document.getElementById('real-id');
document.getElementById('hallucinated-id');
document.getElementById('another-fake');
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6a: Hallucinated DOM references", result, expected_fail=True)
    os.unlink(path)
    
    # 6b: Inline event handlers mixed with addEventListener
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<button id="btn" onclick="handleClick()">Click</button>
<script>
function handleClick() { alert('clicked'); }
document.getElementById('btn').addEventListener('click', handleClick);
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6b: Mixed inline + addEventListener", result, expected_fail=False)
    os.unlink(path)
    
    # 6c: Script tags in body + head
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html>
<head><script>let headVar = 1;</script></head>
<body><script>let bodyVar = 2;</script></body>
</html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6c: Scripts in both head and body", result, expected_fail=False)
    os.unlink(path)
    
    # 6d: CDATA in script (XHTML style)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>
//<![CDATA[
let x = 1;
//]]>
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6d: CDATA in script block", result, expected_fail=False)
    os.unlink(path)
    
    # 6e: XHTML self-closing tags
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body><br/><hr/><img src="test.png"/><script>let x=1;</script></body>
</html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6e: XHTML self-closing tags", result, expected_fail=False)
    os.unlink(path)
    
    # 6f: SVG inside HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<svg width="100" height="100">
  <circle cx="50" cy="50" r="40" stroke="green" fill="yellow" />
  <script>let svgVar = 1;</script>
</svg>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6f: SVG with script inside", result, expected_fail=False)
    os.unlink(path)
    
    # 6g: MathML inside HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<math xmlns="http://www.w3.org/1998/Math/MathML">
  <mrow><mi>x</mi><mo>=</mo><mn>1</mn></mrow>
</math>
<script>let mathVar = 1;</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6g: MathML with script", result, expected_fail=False)
    os.unlink(path)
    
    # 6h: Empty function stubs (should FAIL handlers check)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>
function todoHandler() {
}
function anotherStub() {

}
function realHandler() {
    return 42;
}
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6h: Empty function stubs", result, expected_fail=True)
    os.unlink(path)
    
    # 6i: console.error calls (should FAIL console_errors check)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>
function handleError() {
    console.error('Something went wrong');
    console.warn('This is a warning');
}
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6i: console.error calls", result, expected_fail=True)
    os.unlink(path)
    
    # 6j: Hallucinated event handlers (calling undefined functions)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>
function realHandler() { return 42; }
handleClick(); // called but not defined
processData();  // called but not defined
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("6j: Calling undefined functions", result, expected_fail=False)
    os.unlink(path)


def test_7_unicode_attacks():
    """Unicode attack tests."""
    print("\n# [7] Unicode Attacks")
    
    # 7a: Homoglyph characters in function names
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>\n')
        f.write('function s\u0435tValue() { return 1; }  // Cyrillic "е" instead of Latin "e"\n')
        f.write('function setValue() { return 2; }\n')
        f.write('</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7a: Homoglyph in function names", result, expected_fail=False)
    os.unlink(path)
    
    # 7b: RTL override characters
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>\n')
        f.write('let \u202erole = "admin";  // RTL override\n')
        f.write('let \u202evar = 1;\n')
        f.write('</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7b: RTL override characters", result, expected_fail=False)
    os.unlink(path)
    
    # 7c: Zalgo text (combining characters)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        zalgo = "h" + "\u0300\u0301\u0302\u0303\u0304\u0305\u0306\u0307\u0308\u0309" * 100
        f.write(f'<html><body><script>let {zalgo} = 1;</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7c: Zalgo combining characters", result, expected_fail=False)
    os.unlink(path)
    
    # 7d: Very long unicode escape sequences in strings
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>\n')
        f.write('let x = "\\u{' + '0041' * 1000 + '}";\n')
        f.write('</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7d: Long unicode escape sequences", result, expected_fail=False)
    os.unlink(path)
    
    # 7e: Zero-width joiners/non-joiners in identifiers
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        zwnj = '\u200c'
        zwj = '\u200d'
        f.write(f'<html><body><script>\n')
        f.write(f'let a{zwnj}b = 1;\n')
        f.write(f'let c{zwj}d = 2;\n')
        f.write(f'</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7e: Zero-width joiners in identifiers", result, expected_fail=False)
    os.unlink(path)
    
    # 7f: BiDi overrides with mixed quotes
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>\n')
        f.write('let x = "\u202EHello\u202C";\n')
        f.write('</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("7f: BiDi overrides in strings", result, expected_fail=False)
    os.unlink(path)


def test_8_css_in_js():
    """CSS-in-JS tests."""
    print("\n# [8] CSS-in-JS")
    
    # 8a: Template literal with CSS that looks like JS
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const styles = {
    container: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(45deg, #000, #fff)',
    }
};
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8a: CSS-in-JS object syntax", result, expected_fail=False)
    os.unlink(path)
    
    # 8b: Template literal with CSS containing braces
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const css = `
    .container {
        display: flex;
        @media (max-width: 768px) {
            flex-direction: column;
        }
    }
`;
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8b: Template literal CSS with nested braces", result, expected_fail=False)
    os.unlink(path)
    
    # 8c: Styled components-like template literals
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const Button = styled.button`
    background: ${props => props.primary ? 'blue' : 'gray'};
    color: white;
    padding: ${props => props.size === 'large' ? '20px' : '10px'};
    &:hover {
        background: darkblue;
    }
`;
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8c: Styled-components-like syntax", result, expected_fail=False)
    os.unlink(path)
    
    # 8d: Template literal with syntax errors inside CSS
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const broken = \`
    .foo {
        background: url(http://example.com);
        /* unclosed comment
    }
\`;
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8d: Template literal with CSS syntax errors", result, expected_fail=False)
    os.unlink(path)
    
    # 8e: Template literal with mismatched braces that would normally fail
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const tmpl = \`
    {
        nested: {
            deeper: {
                data: "value"
            }
        }
    }
\`;
let x = 1;
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8e: Template with balanced braces in CSS", result, expected_fail=False)
    os.unlink(path)
    
    # 8f: CSS calc() with nested parens
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
const style = {
    width: 'calc(100% - 20px)',
    height: 'calc(50vh - (20px + 10px))',
    transform: 'translateX(calc(-50% + 10px))',
};
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("8f: CSS calc() with nested parens in strings", result, expected_fail=False)
    os.unlink(path)


def test_9_multiple_scripts():
    """Multiple script tag tests."""
    print("\n# [9] Multiple Script Tags")
    
    # 9a: 1000 inline script tags (already done in 5c, but add more variations)
    
    # 9b: Mixed external/inline scripts
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><head>")
        for i in range(20):
            f.write(f'<script src="app{i}.js"></script>\n')
        f.write('</head><body>')
        for i in range(20):
            f.write(f'<script>var inline{i}=1;</script>\n')
        f.write('</body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("9b: 20 external + 20 inline scripts", result, expected_fail=False)
    os.unlink(path)
    
    # 9c: Script tags with type="module"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script type="module">
import { foo } from './bar.js';
foo();
</script>
<script nomodule>
alert('Legacy browser');
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("9c: type=module and nomodule scripts", result, expected_fail=False)
    os.unlink(path)
    
    # 9d: Script tags with async/defer
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script async src="async.js"></script>
<script defer src="defer.js"></script>
<script>let x = 1;</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("9d: async/defer script attributes", result, expected_fail=False)
    os.unlink(path)
    
    # 9e: Script inside script (nested script tags)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>document.write("<script>let inner=1;<\\/script>");</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("9e: JS that writes <script> tags", result)
    os.unlink(path)
    
    # 9f: Multiple script blocks with complex inter-function dependencies
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>function step1() { return 1; }</script>
<script>function step2() { return step1() + 1; }</script>
<script>function step3() { return step2() + 1; }
function emptyStub() {
}
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("9f: Multi-block with cross-references + empty stub", result, expected_fail=True)
    os.unlink(path)


def test_10_edge_case_cli():
    """Edge case CLI usage tests."""
    print("\n# [10] Edge Case CLI Usage")
    
    # 10a: Non-existent file
    result = run_cli("/nonexistent/path/file.html")
    analyze_result("10a: Non-existent file", result, expected_fail=True)
    
    # 10b: Path is a directory (without .html files)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_cli(tmpdir)
        analyze_result("10b: Empty directory", result, expected_fail=True)
    
    # 10c: No arguments (run with no subcommand)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "maestro_guard.cli"],
            capture_output=True, text=True, timeout=10, cwd=BASE_DIR
        )
        if proc.returncode == 0:
            record_issue("minor", "cli", "10c: No arguments",
                        "Exit code 0 with no arguments (should be non-zero)")
        elif proc.returncode == 2:
            pass  # argparse default behavior
        else:
            record_issue("info", "cli", "10c: No arguments",
                        f"Exit code {proc.returncode}")
    except Exception as e:
        record_issue("moderate", "cli", "10c: No arguments",
                    f"Exception: {e}")
    
    # 10d: --json with bad output (check that JSON is parseable)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x=1;</script></body></html>")
        path = f.name
    result = run_cli(path, ["--json"])
    analyze_result("10d: --json flag output", result, expected_fail=False)
    # Verify JSON is valid
    if result["stdout"]:
        try:
            json.loads(result["stdout"])
        except json.JSONDecodeError:
            record_issue("critical", "cli", "10d: --json output",
                        "JSON output is not valid JSON",
                        f"stdout first 500 chars: {result['stdout'][:500]}")
    os.unlink(path)
    
    # 10e: --verbose --json together
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x=1;</script></body></html>")
        path = f.name
    result = run_cli(path, ["--verbose", "--json"])
    analyze_result("10e: --verbose --json combined", result, expected_fail=False)
    # Check that JSON is still valid (stderr may have verbose output)
    if result["stdout"]:
        try:
            json.loads(result["stdout"])
        except json.JSONDecodeError:
            record_issue("moderate", "cli", "10e: --verbose --json combined",
                        "JSON output is not valid JSON with --verbose flag",
                        f"stdout: {result['stdout'][:500]}")
    os.unlink(path)
    
    # 10f: --version flag
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "maestro_guard.cli", "--version"],
            capture_output=True, text=True, timeout=10, cwd=BASE_DIR
        )
        if proc.returncode != 0:
            record_issue("moderate", "cli", "10f: --version",
                        f"Non-zero exit code: {proc.returncode}")
    except Exception as e:
        record_issue("moderate", "cli", "10f: --version",
                    f"Exception: {e}")
    
    # 10g: Unicode file path
    try:
        unicode_name = "\u2603\u2600.html"  # ☃☀.html
        full_path = os.path.join(tempfile.gettempdir(), unicode_name)
        with open(full_path, 'w') as f:
            f.write("<html><body><script>let x=1;</script></body></html>")
        result = run_cli(full_path)
        analyze_result("10g: Unicode file path", result, expected_fail=False)
        os.unlink(full_path)
    except OSError as e:
        record_issue("minor", "cli", "10g: Unicode file path",
                    f"Could not create unicode file path: {e}")
    
    # 10h: Piped stdin (simulate piping)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "maestro_guard.cli", "check", "-"],
            capture_output=True, text=True, timeout=10, cwd=BASE_DIR,
            input="<html><body><script>let x=1;</script></body></html>"
        )
        # Should probably fail since '-' is not a real file
        if proc.returncode == 0:
            record_issue("info", "cli", "10h: stdin piping with '-'",
                        f"Exited 0 (may have read from file named '-')")
    except Exception as e:
        record_issue("info", "cli", "10h: stdin piping with '-'",
                    f"Exception: {e}")
    
    # 10i: File with very long path
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x=1;</script></body></html>")
        # Create a symlink with long path
        long_path = os.path.join(tempfile.gettempdir(), "a" * 200 + ".html")
        try:
            os.symlink(f.name, long_path)
            result = run_cli(long_path)
            analyze_result("10i: Very long file path", result, expected_fail=False)
            os.unlink(long_path)
        except OSError as e:
            record_issue("minor", "cli", "10i: Very long file path",
                        f"Could not create symlink: {e}")
    
    # 10j: Unknown flag
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "maestro_guard.cli", "check", "test.html", "--unknown-flag"],
            capture_output=True, text=True, timeout=10, cwd=BASE_DIR
        )
        if proc.returncode == 0:
            record_issue("moderate", "cli", "10j: Unknown flag",
                        "Exit code 0 with unknown flag (should be 2)")
    except Exception as e:
        record_issue("info", "cli", "10j: Unknown flag",
                    f"Exception: {e}")
    
    # 10k: Directory check with .html files
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(3):
            fp = os.path.join(tmpdir, f"test{i}.html")
            with open(fp, 'w') as f:
                f.write(f"<html><body><script>let x{i}=1;</script></body></html>")
        result = run_cli(tmpdir)
        analyze_result("10k: Directory with .html files", result, expected_fail=False)
    
    # 10l: --spec flag with non-existent spec file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x=1;</script></body></html>")
        path = f.name
    result = run_cli(path, ["--spec", "/nonexistent/spec.md"])
    analyze_result("10l: Non-existent spec file", result, expected_fail=True)
    os.unlink(path)


# ============================================================
# PERFORMANCE / MEMORY STRESS TESTS
# ============================================================

def test_memory_stress():
    """Memory/performance stress tests."""
    print("\n# [11] Memory & Performance Stress")
    
    # 11a: Catastrophic backtracking in regex
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        # Pattern designed to cause backtracking: many <script> openings without closing
        f.write("<html><body>")
        f.write("<script" * 500)
        f.write(">let x=1;</script>")
        f.write("</body></html>")
        path = f.name
    print("  11a: Testing regex backtracking with many <script openings...")
    result = run_cli(path)
    analyze_result("11a: Regex backtracking (many <script openings)", result, expected_fail=False)
    os.unlink(path)
    
    # 11b: Long unclosed string in JS
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        f.write("let x = '" + "a" * 50000)
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("11b: Unclosed long string literal", result, expected_fail=True)
    os.unlink(path)
    
    # 11c: Very deeply nested function calls
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>")
        for i in range(10000):
            f.write("foo(")
        f.write("1")
        for i in range(10000):
            f.write(")")
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("11c: 10K nested function calls", result, expected_fail=False)
    os.unlink(path)
    
    # 11d: Many repeated getElementById calls
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body>")
        f.write('<div id="target">Content</div>\n')
        f.write("<script>\n")
        for i in range(5000):
            f.write(f'document.getElementById("target");\n')
        f.write("</script></body></html>")
        path = f.name
    result = run_cli(path)
    analyze_result("11d: 5000 getElementById calls", result, expected_fail=False)
    os.unlink(path)


# ============================================================
# REGRESSION TESTS (edge-case combinations)
# ============================================================

def test_regression_edge_cases():
    """Regression edge cases."""
    print("\n# [12] Regression Edge Cases")
    
    # 12a: HTML with only getElementById in script, no matching id (should FAIL dom_refs)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script>document.getElementById('nonexistent');</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12a: Missing DOM ID target", result, expected_fail=True)
    os.unlink(path)
    
    # 12b: Multiple console.error should fail
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write('<html><body><script>console.error("err1"); console.error("err2");</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("12b: Multiple console.error", result, expected_fail=True)
    os.unlink(path)
    
    # 12c: Valid HTML with all good practices (should PASS all)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Perfect Page</title>
</head>
<body>
    <div id="app">
        <h1 id="title">Hello</h1>
        <button id="submitBtn">Submit</button>
    </div>
    <script>
        function initApp() {
            const app = document.getElementById('app');
            const title = document.getElementById('title');
            const btn = document.getElementById('submitBtn');
            btn.addEventListener('click', handleSubmit);
        }
        function handleSubmit() {
            return 'submitted';
        }
        initApp();
    </script>
</body>
</html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12c: Perfect valid HTML/JS (expect PASS)", result, expected_fail=False)
    os.unlink(path)
    
    # 12d: getElementById with variable (not string literal) — should not flag
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<div id="real-id">Content</div>
<script>
const id = 'real-id';
const el = document.getElementById(id);
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12d: getElementById with variable", result, expected_fail=False)
    os.unlink(path)
    
    # 12e: HTML with null byte in the middle of a script
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'<html><body><script>let x = "hello\x00world";</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("12e: Null byte inside JS string", result)
    os.unlink(path)
    
    # 12f: Interleaved encoding: Latin-1 bytes that look like UTF-8 continuation
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False) as f:
        f.write(b'<html><body><script>let x = 1;\x80\x81\x82</script></body></html>')
        path = f.name
    result = run_cli(path)
    analyze_result("12f: Invalid UTF-8 continuation bytes", result)
    os.unlink(path)
    
    # 12g: Unclosed <script> tag (no </script>)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<html><body><script>let x = 1;")
        path = f.name
    result = run_cli(path)
    analyze_result("12g: Unclosed script tag", result, expected_fail=False)
    os.unlink(path)
    
    # 12h: Script tag with HTML comments (old-style hiding)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<script type="text/javascript">
<!--
function oldWay() {
    var x = 1;
    return x;
}
//-->
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12h: HTML comments hiding JS (old style)", result, expected_fail=False)
    os.unlink(path)
    
    # 12i: Mixed single/double quotes causing confusion
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body>
<div id="it's">Content</div>
<div id='say "hello"'>Content</div>
<script>
document.getElementById("it's");
document.getElementById('say "hello"');
</script>
</body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12i: Quotes inside HTML id attributes", result, expected_fail=False)
    os.unlink(path)
    
    # 12j: Dynamic code patterns (setTimeout with string eval)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<html><body><script>
setTimeout('alert(1)', 1000);
setInterval('doSomething()', 500);
const f = new Function('a', 'b', 'return a + b');
</script></body></html>""")
        path = f.name
    result = run_cli(path)
    analyze_result("12j: setTimeout/setInterval with strings", result, expected_fail=False)
    os.unlink(path)


def test_interaction_stress():
    """Combined stress tests — all at once."""
    print("\n# [13] Combined Stress Tests")
    
    # 13a: Everything combined — deep nesting, many scripts, unicode, binary-ish
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("<!DOCTYPE html>\n")
        f.write('<html lang="\u202Eevil\u202C">\n')
        f.write("<head>\n")
        f.write('<meta charset="UTF-8">\n')
        f.write("<script>\n")
        f.write("let \u00e9\u00e0\u00fc = 1;\n")
        f.write("let \u200b = 2;\n")  # zero-width space
        f.write("</script>\n")
        f.write("</head>\n")
        f.write("<body>\n")
        # 500 nested divs
        for i in range(500):
            f.write(f"<div id='d{i}' class='{'x' * 100}'>\n")
        f.write("<script>\n")
        f.write("const css = `\n")
        f.write("  .foo {\n")
        f.write("    @media (max-width: 768px) {\n")
        f.write("      color: red;\n")
        f.write("    }\n")
        f.write("  }\n")
        f.write("`;\n")
        f.write("document.getElementById('nonexistent');\n")
        f.write("console.error('This is bad');\n")
        f.write("function emptyStub() {\n}\n")
        f.write("</script>\n")
        for i in range(500):
            f.write("</div>\n")
        f.write("</body>\n")
        f.write("</html>\n")
        path = f.name
    result = run_cli(path)
    analyze_result("13a: Combined stress (unicode + nesting + errors)", result, expected_fail=True)
    os.unlink(path)


# ============================================================
# MAIN RUNNER
# ============================================================

def print_summary():
    """Print final summary."""
    print("\n" + "=" * 70)
    print("  STRESS TEST RESULTS SUMMARY")
    print("=" * 70)
    
    critical = RESULTS["critical"]
    moderate = RESULTS["moderate"]
    minor = RESULTS["minor"]
    info = RESULTS["info"]
    
    print(f"\n  🔴 CRITICAL: {len(critical)}")
    for c in critical:
        print(f"    - [{c['test']}] {c['issue']}")
        if c['detail']:
            for line in c['detail'].split('\n')[:3]:
                print(f"      {line}")
    
    print(f"\n  🟡 MODERATE: {len(moderate)}")
    for m in moderate:
        print(f"    - [{m['test']}] {m['issue']}")
    
    print(f"\n  🔵 MINOR: {len(minor)}")
    for m in minor:
        print(f"    - [{m['test']}] {m['issue']}")
    
    print(f"\n  ℹ️ INFO: {len(info)}")
    for i in info:
        print(f"    - [{i['test']}] {i['issue']}")
    
    print("\n" + "=" * 70)


def generate_report():
    """Generate final markdown report."""
    critical = RESULTS["critical"]
    moderate = RESULTS["moderate"]
    minor = RESULTS["minor"]
    
    report = []
    report.append("# maestro-guard Stress Test Report")
    report.append("")
    report.append(f"Test date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Python: {sys.version}")
    report.append("")
    
    # Critical bugs
    report.append("## 🔴 Critical Bugs Found (Must Fix Before Ship)")
    report.append("")
    if critical:
        report.append("| # | Test | Category | Issue |")
        report.append("|---|---|---|---|")
        for i, c in enumerate(critical, 1):
            detail_short = c['detail'].replace('\n', ' ')[:100] if c['detail'] else ''
            report.append(f"| {i} | {c['test']} | {c['category']} | {c['issue']} |")
            if detail_short:
                report.append(f"|   |   |   | *Detail: {detail_short}* |")
    else:
        report.append("*No critical bugs found.*")
    report.append("")
    
    # Moderate issues
    report.append("## 🟡 Moderate Issues (Should Fix)")
    report.append("")
    if moderate:
        for i, m in enumerate(moderate, 1):
            report.append(f"{i}. **{m['test']}** ({m['category']}): {m['issue']}")
            if m['detail']:
                report.append(f"   - {m['detail'][:200]}")
    else:
        report.append("*No moderate issues found.*")
    report.append("")
    
    # Minor quirks
    report.append("## 🔵 Minor Quirks (Nice-to-Haves)")
    report.append("")
    if minor:
        for i, m in enumerate(minor, 1):
            report.append(f"{i}. **{m['test']}**: {m['issue']}")
            if m['detail']:
                report.append(f"   - {m['detail'][:200]}")
    else:
        report.append("*No minor quirks found.*")
    report.append("")
    
    # Overall verdict
    report.append("## Overall Verdict")
    report.append("")
    total_findings = len(critical) + len(moderate) + len(minor)
    if len(critical) > 0:
        report.append(f"**🚨 NOT SAFE TO SHIP** — {len(critical)} critical bug(s) found.")
    elif len(moderate) > 5:
        report.append(f"**⚠️  NOT SAFE TO SHIP** — {len(moderate)} moderate issues found (threshhold exceeded).")
    elif len(moderate) > 0:
        report.append(f"**⚠️  CONDITIONAL PASS** — {len(moderate)} moderate issues should be addressed before shipping.")
    else:
        report.append("**✅ SAFE TO SHIP** — No critical issues found.")
    
    report.append("")
    report.append("---")
    report.append(f"*Total findings: {total_findings} ({len(critical)} critical, {len(moderate)} moderate, {len(minor)} minor)*")
    
    return '\n'.join(report)


if __name__ == "__main__":
    print("=" * 70)
    print("  maestro-guard STRESS TEST SUITE")
    print("  Comprehensive fuzzing & edge-case analysis")
    print("=" * 70)
    print()
    
    tests = [
        test_1_pathological_html,
        test_2_pathological_js,
        test_3_empty_trivial,
        test_4_binary_non_html,
        test_5_massive_files,
        test_6_ai_garbage,
        test_7_unicode_attacks,
        test_8_css_in_js,
        test_9_multiple_scripts,
        test_10_edge_case_cli,
        test_memory_stress,
        test_regression_edge_cases,
        test_interaction_stress,
    ]
    
    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            record_issue("critical", "test_framework", test_fn.__name__,
                        f"Test harness exception: {e}",
                        traceback.format_exc())
    
    print_summary()
    
    # Generate and save report
    report = generate_report()
    report_path = "/root/maestro-guard/stress_test_report.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\n  Report saved to: {report_path}")
    
    # Print pass/fail summary
    total = sum(1 for r in RESULTS["critical"])
    total += sum(1 for r in RESULTS["moderate"])
    total += sum(1 for r in RESULTS["minor"])
    sys.exit(1 if RESULTS["critical"] else 0)
