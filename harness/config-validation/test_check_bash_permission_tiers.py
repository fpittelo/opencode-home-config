#!/usr/bin/env python3
"""Regression tests for check_bash_permission_tiers.py (#320 Slice B, MADR-0015).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
checker as a subprocess against a throwaway repository tree (tempfile), so
exit codes and failure context are covered end to end.

The checker enforces three invariants over the mirrored bash permission
tiers (root opencode.jsonc + the four allow-default agent specs):

  1. DRIFT GUARD — the ask tier and the deny tier are identical
     (order-sensitive) across all five mirrored locations.
  2. DENY-TAIL FROZEN — the root deny tier equals BASELINE_DENY_TAIL, the
     ordered pattern list captured from origin/dev before the MADR-0015
     delta, with no allow/ask rule interleaved inside the tail.
  3. TRUTH TABLE — a static last-match-wins resolver over the root block
     must reproduce every expected verdict of the MADR-0015 delta.

The known-good fixture is built from the checker's own BASELINE_DENY_TAIL
constant (single source of truth) plus a minimal ask/allow head that
satisfies the truth table. Negative cases cover: ask-tier drift, deny-tier
drift, deny-tail removal, deny-tail reorder, an allow rule interleaved
inside the deny tail, a truth-table ordering defect that the drift and
freeze checks cannot see, a missing agent file, and invalid JSONC. A
positive control pins the real repository state.

Run:
    python3 harness/config-validation/test_check_bash_permission_tiers.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_bash_permission_tiers.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("check_bash_permission_tiers", SCRIPT)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load checker module from {SCRIPT}")
CHECKER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CHECKER)

AGENT_NAMES = ("architect", "developer", "devops", "cyber-security")

# Minimal known-good bash block: allow head + ask tier + the frozen deny tail.
KNOWN_GOOD_RULES: tuple[tuple[str, str], ...] = (
    ("*", "allow"),
    ("rm *", "ask"),
    ("rm /tmp/opencode/*", "allow"),
    ("rm -r /tmp/opencode/*", "allow"),
    ("pip install*", "ask"),
    ("pip3 install*", "ask"),
    ("uv pip install*", "ask"),
    ("*-m pip install*", "ask"),
    ("chmod *", "ask"),
    ("chmod 600 *", "allow"),
    ("chmod 700 *", "allow"),
) + tuple((pattern, "deny") for pattern in CHECKER.BASELINE_DENY_TAIL)


def root_config_text(rules: tuple[tuple[str, str], ...]) -> str:
    """Minimal opencode.jsonc carrying one ordered bash block."""
    entries = ",\n".join(f'      "{pattern}": "{tier}"' for pattern, tier in rules)
    return '{\n  "permission": {\n    "bash": {\n' + entries + "\n    }\n  }\n}\n"


def agent_text(name: str, rules: tuple[tuple[str, str], ...]) -> str:
    """Minimal agent spec: YAML front-matter bash block + body."""
    body = "\n".join(f'    "{pattern}": {tier}' for pattern, tier in rules)
    return (
        "---\n"
        f'description: "{name} test spec"\n'
        "mode: subagent\n"
        "permission:\n"
        "  bash:\n"
        f"{body}\n"
        "---\n"
        "\n"
        f"{name} test body.\n"
    )


def build_repo(
    root_rules: tuple[tuple[str, str], ...] = KNOWN_GOOD_RULES,
    agent_overrides: dict[str, tuple[tuple[str, str], ...]] | None = None,
    config_text: str | None = None,
    drop_agents: tuple[str, ...] = (),
) -> Path:
    """Materialize a throwaway repo (opencode.jsonc + agents/) and return it."""
    root = Path(tempfile.mkdtemp())
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (root / "opencode.jsonc").write_text(
        config_text if config_text is not None else root_config_text(root_rules),
        encoding="utf-8",
    )
    for name in AGENT_NAMES:
        if name in drop_agents:
            continue
        rules = (agent_overrides or {}).get(name, KNOWN_GOOD_RULES)
        (agents_dir / f"{name}.md").write_text(
            agent_text(name, rules), encoding="utf-8"
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


def remove_rule(
    rules: tuple[tuple[str, str], ...], pattern: str
) -> tuple[tuple[str, str], ...]:
    return tuple(rule for rule in rules if rule[0] != pattern)


def swap_rules(
    rules: tuple[tuple[str, str], ...], a: str, b: str
) -> tuple[tuple[str, str], ...]:
    pairs = [list(rule) for rule in rules]
    ia = next(i for i, (p, _) in enumerate(pairs) if p == a)
    ib = next(i for i, (p, _) in enumerate(pairs) if p == b)
    pairs[ia], pairs[ib] = pairs[ib], pairs[ia]
    return tuple((p, t) for p, t in pairs)


def insert_after(
    rules: tuple[tuple[str, str], ...], anchor: str, rule: tuple[str, str]
) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for pair in rules:
        out.append(pair)
        if pair[0] == anchor:
            out.append(rule)
    return tuple(out)


class TierInvariantTests(unittest.TestCase):
    """Negative/positive cases for the three tier invariants."""

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

    def test_known_good_fixture_passes(self) -> None:
        proc = run_checker(build_repo())
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        self.assertIn("PASS check_bash_permission_tiers", proc.stdout)

    def test_ask_tier_drift_fails(self) -> None:
        drifted = remove_rule(KNOWN_GOOD_RULES, "pip3 install*")
        proc = run_checker(build_repo(agent_overrides={"developer": drifted}))
        self.assert_gate_fails(proc, "agents/developer.md", "ask tier")

    def test_deny_tier_drift_fails(self) -> None:
        drifted = remove_rule(KNOWN_GOOD_RULES, "curl*")
        proc = run_checker(build_repo(agent_overrides={"devops": drifted}))
        self.assert_gate_fails(proc, "agents/devops.md", "deny tier")

    def test_deny_tail_removal_fails(self) -> None:
        drifted = remove_rule(KNOWN_GOOD_RULES, "*.key*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_deny_tail_reorder_fails(self) -> None:
        drifted = swap_rules(KNOWN_GOOD_RULES, "curl*", "wget*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_allow_interleaved_inside_deny_tail_fails(self) -> None:
        drifted = insert_after(KNOWN_GOOD_RULES, "sudo*", ("docker *", "allow"))
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_truth_table_ordering_defect_fails(self) -> None:
        # The allow line moved BEFORE the ask rule: drift and freeze stay
        # green, only the last-match-wins resolver catches the defect.
        drifted = remove_rule(KNOWN_GOOD_RULES, "rm /tmp/opencode/*")
        drifted = insert_after(drifted, "*", ("rm /tmp/opencode/*", "allow"))
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "resolves to")

    def test_missing_agent_file_fails(self) -> None:
        proc = run_checker(build_repo(drop_agents=("cyber-security",)))
        self.assert_gate_fails(proc, "agents/cyber-security.md")

    def test_invalid_jsonc_fails(self) -> None:
        proc = run_checker(build_repo(config_text="{ not jsonc }"))
        self.assert_gate_fails(proc, "unreadable or invalid JSONC")


class RealRepositoryTests(unittest.TestCase):
    """Positive control: the real repository satisfies all three invariants."""

    def test_real_repo_satisfies_tier_invariants(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
