# maestro-guard Stress Test Report

Test date: 2026-06-17 16:48:43
Python: 3.11.15 (main, May 10 2026, 19:28:18) [Clang 22.1.3 ]

## 🔴 Critical Bugs Found (Must Fix Before Ship)

*No critical bugs found.*

## 🟡 Moderate Issues (Should Fix)

1. **10d: --json flag output** (logic): Should have PASSED but got FAIL (false positive)
   - Expected PASS, got FAIL. exit_code=0
2. **10d: --json flag output** (consistency): Exit code 0 but result shows FAIL
   - stdout={
  "version": "0.1.0",
  "score": 85,
  "max_score": 85,
  "all_passed": true,
  "checks": [
    {
      "name": "js_syntax",
      "passed": true,
      "earned_weight": 25,
      "max_weight
3. **10e: --verbose --json combined** (logic): Should have PASSED but got FAIL (false positive)
   - Expected PASS, got FAIL. exit_code=0
4. **10e: --verbose --json combined** (consistency): Exit code 0 but result shows FAIL
   - stdout={
  "version": "0.1.0",
  "score": 85,
  "max_score": 85,
  "all_passed": true,
  "checks": [
    {
      "name": "js_syntax",
      "passed": true,
      "earned_weight": 25,
      "max_weight
5. **10i: Very long file path** (logic): Should have PASSED but got FAIL (false positive)
   - Expected PASS, got FAIL. exit_code=1

## 🔵 Minor Quirks (Nice-to-Haves)

*No minor quirks found.*

## Overall Verdict

**⚠️  CONDITIONAL PASS** — 5 moderate issues should be addressed before shipping.

---
*Total findings: 5 (0 critical, 5 moderate, 0 minor)*