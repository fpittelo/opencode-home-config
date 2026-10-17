#!/usr/bin/env python3
"""Regression tests for check_bash_permission_tiers.py (#340, root inheritance).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
checker as a subprocess against a throwaway repository tree (tempfile), so
exit codes and failure context are covered end to end.

Design shift (#340): MADR-0004 five-file mirroring is superseded by root
inheritance. Verified opencode semantics (empirical probe, `opencode debug
agent`, opencode 1.19.0): an agent spec that omits the ``bash:`` key
receives every config-level bash rule of ``opencode.jsonc`` (last-match-wins
across the merged list); an agent that declares a (partial) bash map has its
rules appended AFTER all config-level rules, so a role allow re-stated there
can override the root deny tail. The checker therefore enforces:

  1. ROOT BASELINE INTEGRITY — the root ``permission.bash`` block of
     opencode.jsonc equals BASELINE_ROOT_RULES exactly (order-sensitive pin
     of the MADR-0015 delta: allow head + ask tier + frozen deny tail). The
     root block is the single source of truth.
  2. CLEAN AGENT INHERITANCE — each of the four allow-default agent specs
     either omits ``bash:`` entirely or carries ONLY its documented
     role-deviation patterns (devops: ``docker *`` allow; cyber-security:
     audit-tool allows). Re-stating any root tier pattern in an agent is now
     the defect, not the requirement.
  3. TRUTH TABLE — the static last-match-wins resolver over the root block
     must reproduce every expected verdict of the MADR-0015 delta.

The known-good fixture is built from the checker's own baseline constants
(single source of truth). Negative cases cover: root ask-tier removal,
root ask-tier reorder, deny-tail removal, deny-tail reorder, an allow rule
interleaved inside the deny tail, a truth-table ordering defect the pin
alone cannot distinguish, an agent re-stating one root pattern, an agent
mirroring the whole block, an undocumented role deviation, a
non-allow-tier deviation, a missing agent file, and invalid JSONC. A
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

# Known-good root bash block: built from the checker's own baseline pin
# (single source of truth): allow head + ask tier + frozen deny tail.
KNOWN_GOOD_RULES: tuple[tuple[str, str], ...] = tuple(CHECKER.BASELINE_ROOT_RULES)


def root_config_text(rules: tuple[tuple[str, str], ...]) -> str:
    """Minimal opencode.jsonc carrying one ordered bash block."""
    entries = ",\n".join(f'      "{pattern}": "{tier}"' for pattern, tier in rules)
    return '{\n  "permission": {\n    "bash": {\n' + entries + "\n    }\n  }\n}\n"


def agent_text(name: str, rules: tuple[tuple[str, str], ...] | None) -> str:
    """Minimal agent spec: YAML front-matter (optional bash block) + body."""
    bash_block = ""
    if rules is not None:
        body = "\n".join(f'    "{pattern}": {tier}' for pattern, tier in rules)
        bash_block = "  bash:\n" + f"{body}\n"
    return (
        "---\n"
        f'description: "{name} test spec"\n'
        "mode: subagent\n"
        "permission:\n"
        + bash_block
        + "  GITHUB_*: allow\n"
        "---\n"
        "\n"
        f"{name} test body.\n"
    )


def build_repo(
    root_rules: tuple[tuple[str, str], ...] = KNOWN_GOOD_RULES,
    agent_bash: dict[str, tuple[tuple[str, str], ...] | None] | None = None,
    config_text: str | None = None,
    drop_agents: tuple[str, ...] = (),
) -> Path:
    """Materialize a throwaway repo (opencode.jsonc + agents/) and return it.

    Agents omit the bash block by default (the inherited posture); pass
    agent_bash entries to re-introduce blocks or None entries to keep a
    specific agent bash-free.
    """
    root = Path(tempfile.mkdtemp())
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (root / "opencode.jsonc").write_text(
        config_text if config_text is not None else root_config_text(root_rules),
        encoding="utf-8",
    )
    overrides = agent_bash or {}
    for name in AGENT_NAMES:
        if name in drop_agents:
            continue
        (agents_dir / f"{name}.md").write_text(
            agent_text(name, overrides.get(name)), encoding="utf-8"
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


class RootBaselineIntegrityTests(unittest.TestCase):
    """The root permission.bash block is the pinned MADR-0015 baseline."""

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

    def test_root_ask_tier_removal_fails(self) -> None:
        drifted = remove_rule(KNOWN_GOOD_RULES, "pip3 install*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "baseline")

    def test_root_ask_tier_reorder_fails(self) -> None:
        drifted = swap_rules(KNOWN_GOOD_RULES, "rm *", "pip install*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "baseline")

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
        # The allow line moved BEFORE the ask rule: pin and resolver both
        # catch it; this case guards the truth table itself (semantic guard
        # against a baseline pin that is edited alongside the config).
        drifted = remove_rule(KNOWN_GOOD_RULES, "rm /tmp/opencode/*")
        drifted = insert_after(drifted, "*", ("rm /tmp/opencode/*", "allow"))
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "resolves to")

    def test_invalid_jsonc_fails(self) -> None:
        proc = run_checker(build_repo(config_text="{ not jsonc }"))
        self.assert_gate_fails(proc, "unreadable or invalid JSONC")

    def test_missing_agent_file_fails(self) -> None:
        proc = run_checker(build_repo(drop_agents=("cyber-security",)))
        self.assert_gate_fails(proc, "agents/cyber-security.md")


class AgentInheritanceTests(unittest.TestCase):
    """Agents inherit the root baseline; re-statement is the defect (#340)."""

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

    def test_agent_restating_one_root_pattern_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"developer": (("rm *", "ask"),)})
        )
        self.assert_gate_fails(proc, "agents/developer.md", "rm *")

    def test_agent_mirroring_whole_block_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"architect": KNOWN_GOOD_RULES})
        )
        self.assert_gate_fails(proc, "agents/architect.md")

    def test_undocumented_role_deviation_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("terraform *", "allow"),)})
        )
        self.assert_gate_fails(proc, "agents/devops.md", "terraform *")

    def test_non_allow_tier_deviation_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("docker *", "ask"),)})
        )
        self.assert_gate_fails(proc, "agents/devops.md")

    def test_documented_devops_deviation_passes(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("docker *", "allow"),)})
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_documented_cyber_security_deviation_passes(self) -> None:
        allowed = sorted(CHECKER.AGENT_DEVIATIONS["cyber-security.md"])
        rules = tuple((pattern, "allow") for pattern in allowed)
        proc = run_checker(
            build_repo(agent_bash={"cyber-security": rules})
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_docstring_reflects_root_inheritance_design(self) -> None:
        text = Path(CHECKER.__file__).resolve().read_text(encoding="utf-8")
        self.assertIn("#340", text)
        self.assertIn("inherit", text.lower())


class RealRepositoryTests(unittest.TestCase):
    """Positive control: the real repository satisfies all three invariants."""

    def test_real_repo_satisfies_tier_invariants(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_real_repo_agents_omit_bash_block(self) -> None:
        for name in AGENT_NAMES:
            front_matter = (REPO_ROOT / "agents" / f"{name}.md").read_text(
                encoding="utf-8"
            ).split("---", 2)[1]
            self.assertNotIn(
                "  bash:",
                front_matter,
                f"agents/{name}.md still re-states bash rules — run the "
                f"root-inheritance dedup (#340)",
            )


if __name__ == "__main__":
    unittest.main()