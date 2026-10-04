#!/usr/bin/env python3
"""Regression tests for check_coach_exclusivity.py (namespace-exclusivity gate).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
checker as a subprocess against a throwaway repository tree (tempfile), so
exit codes and failure context are covered end to end.

The checker enforces the namespace-exclusivity permission invariant for every
governed MCP namespace — global default-deny baseline in opencode.jsonc,
explicit per-agent restatement in agents/*.md, and "allow" reserved to the
designated whitelist agents:

  COACH_*   keys COACH_DEV_*/COACH_QA_*/COACH_MAIN_*, allow only coach.md
            (#150 AC1-AC3)
  BROWSER_* key BROWSER_*, allow only developer.md + devops.md
            (#207 AC3, MADR-0009)

Cases are parametrized over both namespaces (subTest) against a combined
two-namespace fixture, so a namespace must be enforced on its own merits —
a checker that silently ignores a namespace fails the negative cases. A
positive control pins the real repository state (the subject of the
run-config-gate.sh exclusivity gate and its ci.yml twin).

Run:
    python3 harness/config-validation/test_check_coach_exclusivity.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_coach_exclusivity.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Namespace under test -> (canonical permission keys, whitelist agent files).
NAMESPACE_CASES = {
    "COACH": (
        ("COACH_DEV_*", "COACH_QA_*", "COACH_MAIN_*"),
        ("coach.md",),
    ),
    "BROWSER": (
        ("BROWSER_*",),
        ("developer.md", "devops.md"),
    ),
}

AGENT_NAMES = (
    "architect",
    "coach",
    "code-reviewer",
    "cyber-security",
    "developer",
    "devops",
    "scrum-master",
)


def valid_permission() -> dict[str, str]:
    """Global baseline: every canonical key of every namespace denied."""
    permission: dict[str, str] = {}
    for keys, _ in NAMESPACE_CASES.values():
        for key in keys:
            permission[key] = "deny"
    return permission


def valid_agent_rules(name: str) -> dict[str, str]:
    """Per-agent posture: allow iff the agent is a whitelist agent."""
    rules: dict[str, str] = {}
    for keys, allow_agents in NAMESPACE_CASES.values():
        value = "allow" if f"{name}.md" in allow_agents else "deny"
        for key in keys:
            rules[key] = value
    return rules


def agent_spec_text(name: str, rules: dict[str, str]) -> str:
    """Minimal agent spec: YAML front-matter permission block + body."""
    lines = [
        "---",
        f'description: "{name} test spec"',
        "mode: subagent",
        "permission:",
    ]
    lines += [f"  {key}: {value}" for key, value in rules.items()]
    lines += ["---", "", f"{name} test body.", ""]
    return "\n".join(lines)


def build_repo(
    permission: dict[str, str],
    agent_rules: dict[str, dict[str, str]],
    config_text: str | None = None,
) -> Path:
    """Materialize a throwaway repo (opencode.jsonc + agents/) and return it."""
    root = Path(tempfile.mkdtemp())
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (root / "opencode.jsonc").write_text(
        config_text
        if config_text is not None
        else "{\n  \"permission\": {\n"
        + ",\n".join(
            f'    "{key}": "{value}"' for key, value in permission.items()
        )
        + "\n  }\n}\n",
        encoding="utf-8",
    )
    for name in AGENT_NAMES:
        rules = (
            agent_rules[name] if name in agent_rules else valid_agent_rules(name)
        )
        (agents_dir / f"{name}.md").write_text(
            agent_spec_text(name, rules), encoding="utf-8"
        )
    return root


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker CLI against a repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


class NamespaceExclusivityTests(unittest.TestCase):
    """Parametrized negative/positive cases for both governed namespaces."""

    def assert_gate_fails(
        self, proc: subprocess.CompletedProcess[str], *fragments: str
    ) -> None:
        output = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode,
            1,
            f"expected exit 1, got {proc.returncode}:\n{output}",
        )
        for fragment in fragments:
            self.assertIn(fragment, output)

    def test_valid_combined_config_passes(self) -> None:
        proc = run_checker(build_repo(valid_permission(), {}))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_missing_global_baseline_key_fails(self) -> None:
        for namespace, (keys, _) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                permission = valid_permission()
                del permission[keys[0]]
                proc = run_checker(build_repo(permission, {}))
                self.assert_gate_fails(proc, keys[0], "must be")

    def test_wrong_global_baseline_value_fails(self) -> None:
        for namespace, (keys, _) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                permission = valid_permission()
                permission[keys[0]] = "allow"
                proc = run_checker(build_repo(permission, {}))
                self.assert_gate_fails(proc, keys[0], "must be")

    def test_pattern_drift_key_in_config_fails(self) -> None:
        for namespace, (keys, _) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                permission = valid_permission()
                permission[f"{namespace}_LEGACY_*"] = "deny"
                proc = run_checker(build_repo(permission, {}))
                self.assert_gate_fails(proc, f"{namespace}_LEGACY_*", "unexpected")

    def test_missing_agent_key_fails(self) -> None:
        for namespace, (keys, _) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                rules = valid_agent_rules("scrum-master")
                del rules[keys[0]]
                proc = run_checker(
                    build_repo(valid_permission(), {"scrum-master": rules})
                )
                self.assert_gate_fails(proc, "scrum-master.md", keys[0])

    def test_allow_outside_whitelist_fails(self) -> None:
        for namespace, (keys, allow_agents) in NAMESPACE_CASES.items():
            outsider = next(
                name for name in AGENT_NAMES if f"{name}.md" not in allow_agents
            )
            with self.subTest(namespace=namespace, agent=outsider):
                rules = valid_agent_rules(outsider)
                rules[keys[0]] = "allow"
                proc = run_checker(
                    build_repo(valid_permission(), {outsider: rules})
                )
                self.assert_gate_fails(proc, f"{outsider}.md", keys[0])

    def test_deny_in_whitelist_agent_fails(self) -> None:
        for namespace, (keys, allow_agents) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                insider = sorted(allow_agents)[0].removesuffix(".md")
                rules = valid_agent_rules(insider)
                rules[keys[0]] = "deny"
                proc = run_checker(
                    build_repo(valid_permission(), {insider: rules})
                )
                self.assert_gate_fails(proc, f"{insider}.md", keys[0])

    def test_pattern_drift_key_in_agent_fails(self) -> None:
        for namespace, (keys, _) in NAMESPACE_CASES.items():
            with self.subTest(namespace=namespace):
                rules = valid_agent_rules("architect")
                rules[f"{namespace}_EXTRA_*"] = "deny"
                proc = run_checker(
                    build_repo(valid_permission(), {"architect": rules})
                )
                self.assert_gate_fails(proc, "architect.md", f"{namespace}_EXTRA_*")

    def test_agent_without_front_matter_fails(self) -> None:
        root = build_repo(valid_permission(), {})
        (root / "agents" / "devops.md").write_text(
            "# no front matter\n", encoding="utf-8"
        )
        proc = run_checker(root)
        self.assert_gate_fails(proc, "devops.md", "no YAML front-matter")

    def test_invalid_jsonc_config_fails(self) -> None:
        proc = run_checker(
            build_repo(valid_permission(), {}, config_text="{ not jsonc }")
        )
        self.assert_gate_fails(proc, "unreadable or invalid JSONC")


class RealRepositoryTests(unittest.TestCase):
    """Positive control: the real repository satisfies the invariant."""

    def test_real_repo_satisfies_namespace_invariant(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
