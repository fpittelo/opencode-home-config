# Harness Test Result Parsing & Closed-Loop Verification Design

**Issue:** fpittelo/opencode-home-config#35  
**Author:** @developer  
**Date:** 2026-09-07  
**Status:** Design / Ready for Review

---

## 1. Goal

Define how the HOME sandboxed execution harness parses test output, detects FAIL_TO_PASS and PASS_TO_PASS conditions, and returns a structured, agent-friendly result. The design covers both Python (`pytest`) and Rust (`cargo test`) projects in the HOME ecosystem.

---

## 2. Parsing Strategy

### 2.1 Principle

Do **not** rely on exit codes alone. Exit codes indicate *that* something failed, not *which* test failed or *why*. The harness must capture a structured test artifact first and fall back to stdout parsing only when a structured artifact is unavailable.

| Approach | Pros | Cons | Verdict |
| :--- | :--- | :--- | :--- |
| Exit codes only | Simple, universal | No per-test identity | **Insufficient** |
| JUnit XML / JSON | Per-test status, stable parsing, machine-readable | Requires tool support | **Primary** |
| stdout parsing | Universal, no extra deps | Fragile, format changes | **Fallback** |

### 2.2 Python / pytest

**Primary command:**

```bash
pytest -W error \
       --cov=. \
       --cov-report=term-missing \
       --tb=short \
       -q \
       --junitxml=/tmp/harness-pytest.xml \
       -m "not integration" \
       [optional selectors]
```

**Rationale:**

- `--junitxml` is built into pytest and emits stable per-testcase status.
- `-W error` enforces the HOME zero-warning policy.
- `--tb=short` keeps failure output concise while preserving stack traces.
- `-q` reduces noise but still emits the final summary.
- `-m "not integration"` excludes integration tests that need external services.

**Parsing:** Parse `/tmp/harness-pytest.xml`:

- `<testcase>` without `failure`, `error`, or `skipped` child → **passed**.
- `<testcase>` with `<failure>` or `<error>` → **failed**; capture `message` and text.
- `<testcase>` with `<skipped>` → **skipped**.
- Node ID = `classname` + `name` attributes.

**Fallback:** If JUnit XML is missing or malformed, parse the final summary line and the `--tb=short` failure blocks.

### 2.3 Rust / cargo test

`cargo test` stable has **no built-in per-test JSON output**. `cargo test --message-format=json` controls *Cargo build messages*, not libtest results.

**Primary command (with cargo-nextest):**

```bash
NEXTEST_JUNIT_PATH=/tmp/harness-nextest.xml \
cargo nextest run --profile ci --retries 2
```

**Rationale:**

- `cargo-nextest` produces machine-readable events and JUnit XML.
- It supports retries, timeouts, filtering, and stable per-test reporting.
- `NEXTEST_JUNIT_PATH` writes the same JUnit XML schema pytest uses.

**Fallback command (if nextest is unavailable):**

```bash
cargo test -- --nocapture
```

**Fallback parsing rules:**

- Per-test line: `test <name> ... ok|FAILED|ignored`.
- Summary line: `test result: ok. X passed; Y failed; Z ignored; ...`.
- Build failure: lines starting with `error:` and exit code `101`.

### 2.4 Exit Codes

Record the process exit code, but use it only as a cross-check:

- Non-zero exit + zero parsed failures → **build/compilation failure** (`build_failed=true`).
- Zero exit + parsed failures → treat parsed failures as authoritative.

---

## 3. FAIL_TO_PASS Detection

### 3.1 Recommended Approach: Hybrid A + B, Guarded by C

1. **Agent-provided selectors (Option A)** — The agent passes an explicit list of new/reproduction test selectors (pytest nodeids or cargo test names). This is the primary signal.
2. **Diff-derived new tests (Option B)** — The harness diffs the working tree against the base branch and extracts newly added test functions/classes. These are added to the candidate set.
3. **Baseline failure guard (Option C)** — Before applying the patch, the harness runs the candidate selectors and asserts each one fails. If a candidate does not fail, it is reported as `unreproduced_failures` and the harness halts.

### 3.2 Why Not Option C Alone?

Running the full suite before the patch yields a set of failing tests, but it cannot distinguish the intended reproduction test from unrelated pre-existing failures. An explicit signal (A) or diff signal (B) is required.

### 3.3 FAIL_TO_PASS Acceptance Criteria

- Every candidate test must fail before the patch.
- Every candidate test must pass after the patch.
- If no candidates are provided and no new tests are found in the diff, `fail_to_pass` is `false`.

---

## 4. PASS_TO_PASS Detection

### 4.1 Baseline Capture

Before applying the patch, run the full test suite (excluding integration tests) to capture:

- `baseline_passed`: set of tests that passed.
- `pre_existing_failures`: set of tests that failed.

### 4.2 After-Patch Comparison

After applying the patch, run the full suite again:

```text
regressions = baseline_passed - after_passed
still_failing = pre_existing_failures ∩ after_failed
```

- `regressions` are previously passing tests that now fail. These **block** PASS_TO_PASS.
- `still_failing` are pre-existing failures that remain broken. These are reported but do **not** block PASS_TO_PASS.
- A test that was failing before and passes after is a **fixed test**; if it is also a candidate, it contributes to `new_tests_passed`.

### 4.3 Empty Test Suite

If the repository has no tests:

- `passed = 0`, `failed = 0`, `skipped = 0`.
- `pass_to_pass = true` (vacuously true).
- `fail_to_pass` depends on whether any candidate was expected.

---

## 5. Structured Output Schema

### 5.1 JSON Schema (Draft-07)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "HarnessVerificationResult",
  "type": "object",
  "required": [
    "exit_code",
    "passed",
    "failed",
    "skipped",
    "new_tests_passed",
    "regressions",
    "stdout_tail",
    "stderr_tail",
    "duration_seconds"
  ],
  "properties": {
    "exit_code": {
      "type": "integer",
      "description": "Process exit code of the final full suite run. -1 if the run timed out."
    },
    "build_failed": {
      "type": "boolean",
      "description": "True when compilation/build failed before tests ran."
    },
    "timeout": {
      "type": "boolean",
      "description": "True when the test command exceeded the configured timeout."
    },
    "passed": {
      "type": "integer",
      "minimum": 0
    },
    "failed": {
      "type": "integer",
      "minimum": 0
    },
    "skipped": {
      "type": "integer",
      "minimum": 0
    },
    "new_tests_passed": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Candidate tests that failed before the patch and passed after."
    },
    "regressions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Tests that passed in the baseline but failed after the patch."
    },
    "pre_existing_failures": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Tests that failed before and after the patch."
    },
    "unreproduced_failures": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Candidate tests that did NOT fail before the patch."
    },
    "fail_to_pass": {
      "type": "boolean",
      "description": "True when all candidate tests failed before and passed after."
    },
    "pass_to_pass": {
      "type": "boolean",
      "description": "True when no baseline-passing test regressed."
    },
    "stdout_tail": {
      "type": "string",
      "description": "Truncated stdout from the final test run."
    },
    "stderr_tail": {
      "type": "string",
      "description": "Truncated stderr from the final test run."
    },
    "duration_seconds": {
      "type": "number",
      "minimum": 0
    },
    "command": {
      "type": "string",
      "description": "The exact test command executed."
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### 5.2 Pydantic v2 Model

```python
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HarnessVerificationResult(BaseModel):
    exit_code: int = Field(..., description="Process exit code of the final full suite run.")
    build_failed: bool = False
    timeout: bool = False
    passed: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    skipped: int = Field(..., ge=0)
    new_tests_passed: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    pre_existing_failures: list[str] = Field(default_factory=list)
    unreproduced_failures: list[str] = Field(default_factory=list)
    fail_to_pass: bool = False
    pass_to_pass: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_seconds: float = Field(..., ge=0.0)
    command: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 6. Truncation Strategy

1. Keep full logs inside the container at `/tmp/harness-logs/<run_id>/stdout.log` and `/tmp/harness-logs/<run_id>/stderr.log`.
2. Return only a tail to the agent to respect context-window limits.
3. Algorithm:
   - If total lines ≤ 520, return the full stream.
   - Otherwise return the first 20 lines, an ellipsis marker, and the last 500 lines.
   - Cap each returned stream at 64 KiB; truncate at a line boundary and append `[...truncated...]`.

**Rationale:** Stack traces and final summaries live at the end; the first lines provide command and environment context.

---

## 7. Edge Cases

| Scenario | Handling |
| :--- | :--- |
| **Suite runs > 30 min** | Configurable `timeout_seconds` (default 600, max 1800). On timeout, kill the process, set `timeout=true`, `exit_code=-1`. |
| **Integration tests need DB/API** | Exclude by default. Python: `-m "not integration"`. Rust: mark with `#[ignore]` or use nextest filters. Allow `integration_marker` override. |
| **Flaky tests** | Retry failed tests up to `max_retries` (default 2). Python: `pytest-rerunfailures --reruns 2`. Rust: `cargo nextest` `retries = 2`. A test passing on retry counts as passed but is flagged in `flaky_passed` if the field is exposed. |
| **No tests exist** | Return zero counts. `pass_to_pass=true`. `fail_to_pass=false` if a candidate was expected. |
| **Build/compilation failure** | Set `build_failed=true`, do not attempt test comparison, return captured compiler/linter output. |
| **Pre-existing failures** | Capture in `pre_existing_failures`; do not block PASS_TO_PASS. |

---

## 8. Verification Algorithm

```text
function verify(repo, lang, candidates, timeout=600, max_retries=2, integration_marker="integration"):
    start = now()

    # 1. Baseline: full suite BEFORE patch
    baseline = run_full_suite(repo, lang, timeout, integration_marker)
    if baseline.build_failed:
        return result(build_failed=true,
                      stdout_tail=tail(baseline.stdout),
                      stderr_tail=tail(baseline.stderr),
                      duration_seconds=elapsed(start))

    baseline_passed = set(baseline.passed)
    pre_existing_failed = set(baseline.failed)

    # 2. FAIL_TO_PASS reproduction: run candidates BEFORE patch
    reproduce = run_selected(repo, lang, candidates, timeout, integration_marker)
    if reproduce.build_failed:
        return result(build_failed=true, ...)

    unreproduced = [c for c in candidates if c not in set(reproduce.failed)]
    if unreproduced:
        return result(fail_to_pass=false,
                      unreproduced_failures=unreproduced,
                      stdout_tail=tail(reproduce.stdout),
                      stderr_tail=tail(reproduce.stderr),
                      duration_seconds=elapsed(start))

    # 3. Apply the patch (caller-provided step)
    apply_patch(repo)

    # 4. Full suite AFTER patch (with flaky retries)
    after = run_full_suite(repo, lang, timeout, integration_marker, retries=max_retries)
    if after.build_failed:
        return result(build_failed=true, ...)

    after_passed = set(after.passed)
    after_failed = set(after.failed)

    # 5. Evaluate FAIL_TO_PASS
    new_still_failing = [c for c in candidates if c not in after_passed]
    new_passed = [c for c in candidates
                  if c in after_passed and c in set(reproduce.failed)]

    # 6. Evaluate PASS_TO_PASS
    regressions = baseline_passed - after_passed
    still_failing = pre_existing_failed ∩ after_failed

    return HarnessVerificationResult(
        exit_code=after.exit_code,
        passed=len(after_passed),
        failed=len(after_failed),
        skipped=len(after.skipped),
        new_tests_passed=sorted(new_passed),
        regressions=sorted(regressions),
        pre_existing_failures=sorted(still_failing),
        fail_to_pass=(len(new_still_failing) == 0),
        pass_to_pass=(len(regressions) == 0),
        stdout_tail=tail(after.stdout),
        stderr_tail=tail(after.stderr),
        duration_seconds=elapsed(start),
        command=after.command,
    )
```

### 8.1 Helper: `run_full_suite`

```text
function run_full_suite(repo, lang, timeout, integration_marker, retries=0):
    if lang == python:
        cmd = "pytest -W error --cov=. --cov-report=term-missing --tb=short -q --junitxml=/tmp/harness-pytest.xml"
        cmd += f" -m 'not {integration_marker}'"
        if retries > 0 and plugin_available("pytest-rerunfailures"):
            cmd += f" --reruns {retries} --reruns-delay 1"
    elif lang == rust:
        if nextest_available():
            env = {"NEXTEST_JUNIT_PATH": "/tmp/harness-nextest.xml"}
            cmd = "cargo nextest run --profile ci"
            if retries > 0:
                cmd += f" --retries {retries}"
        else:
            cmd = "cargo test -- --nocapture"

    process = subprocess.run(cmd, timeout=timeout, capture_output=True, env=env)
    parsed = parse_output(lang, process)
    return TestRun(
        exit_code=process.returncode,
        build_failed=(process.returncode != 0 and len(parsed.failures) == 0 and not is_test_summary_present(parsed)),
        passed=parsed.passed,
        failed=parsed.failed,
        skipped=parsed.skipped,
        stdout=process.stdout,
        stderr=process.stderr,
        command=cmd,
    )
```

---

## 9. Recommended Command Reference

### Python Pre-Flight / Harness Test Command

```bash
ruff check . && \
black --check . && \
isort --check-only . && \
mypy --strict . && \
pytest -W error --cov=. --cov-report=term-missing --tb=short -q --junitxml=/tmp/harness-pytest.xml -m "not integration"
```

### Rust Pre-Flight / Harness Test Command

```bash
cargo fmt --check && \
cargo clippy -- -D warnings && \
cargo nextest run --profile ci --retries 2
```

Fallback if `cargo-nextest` is not installed:

```bash
cargo fmt --check && \
cargo clippy -- -D warnings && \
cargo test -- --nocapture
```

---

## 10. Alignment with Existing Harness Runners

The current HOME harness Dockerfiles (`harness/docker/Dockerfile.python` and `harness/docker/Dockerfile.rust`) run:

```bash
uv run pytest -W error --cov=.
```

and

```bash
cargo fmt --check && cargo clippy -- -D warnings && cargo test
```

This design is compatible with those commands:

- For Python, add `--junitxml=/tmp/harness-pytest.xml --tb=short -q -m "not integration"` to the existing pytest invocation.
- For Rust, the human-output parser covers the existing `cargo test -- --nocapture` command. Installing `cargo-nextest` in the Rust runner is recommended as a future enhancement for machine-readable JUnit output and built-in retries.

## 11. Recommendation Summary

- **Parsing:** Use JUnit XML as the primary structured artifact for both pytest and cargo-nextest. Fall back to regex-based stdout parsing only when nextest is unavailable.
- **FAIL_TO_PASS:** Require explicit agent-provided selectors, augment with diff-derived new tests, and guard by running them before the patch to confirm failure.
- **PASS_TO_PASS:** Capture a baseline passing set before the patch; after the patch, any previously passing test that fails is a regression.
- **Output:** Return a Pydantic-validated JSON result with counts, per-test lists, truncated tails, and clear boolean gates.
- **Edge cases:** Timeouts, integration-test exclusion, flaky-test retries, empty suites, and build failures are all explicitly modeled in the result schema.
