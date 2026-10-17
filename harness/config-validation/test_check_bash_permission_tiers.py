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

#350 extension: the checker must parse the bash posture of ALL agent
specs — block form, flow mapping (``bash: {"*": deny}``) and scalar
(``bash: deny``) — instead of only block-form headers in the four
allow-default specs (a flow-style ``bash: {"*": allow}`` header used to
be silently blessed). The shapes of the three non-inheritance agents
(scrum-master, code-reviewer, coach) are pinned order-sensitively: the
scrum-master pin requires the three trailing secret-file denies
(``*.env*``/``*.pem*``/``*.key*``) to sit AFTER its gh/git allows, because
agent rules append after the root deny tail (last-match-wins) — without
them an allow like ``gh pr *`` re-enables credential-file commands such
as ``gh pr edit 1 --body-file foo.env`` (the #350 append-override).

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
NON_INHERITANCE_NAMES = ("scrum-master", "code-reviewer", "coach")
ALL_AGENT_NAMES = AGENT_NAMES + NON_INHERITANCE_NAMES

# Expected bash shapes of the three non-inheritance agents (#350),
# order-sensitive (last-match-wins: agent rules append AFTER the root
# deny tail). The scrum-master shape carries the three trailing
# secret-file denies AFTER the gh/git allows — the #350 append-override
# guard. Taken from the checker's own pins (single source of truth,
# mirroring KNOWN_GOOD_RULES below).
SCRUM_MASTER_EXPECTED = CHECKER.NON_INHERITANCE_AGENTS["scrum-master.md"]
CODE_REVIEWER_EXPECTED = CHECKER.NON_INHERITANCE_AGENTS["code-reviewer.md"]
COACH_EXPECTED = CHECKER.NON_INHERITANCE_AGENTS["coach.md"]
NON_INH_DEFAULTS: dict[str, tuple[tuple[str, str], ...]] = {
    "scrum-master": SCRUM_MASTER_EXPECTED,
    "code-reviewer": CODE_REVIEWER_EXPECTED,
    "coach": COACH_EXPECTED,
}

# Known-good root bash block: built from the checker's own baseline pin
# (single source of truth): allow head + ask tier + frozen deny tail.
KNOWN_GOOD_RULES: tuple[tuple[str, str], ...] = tuple(CHECKER.BASELINE_ROOT_RULES)


def root_config_text(rules: tuple[tuple[str, str], ...]) -> str:
    """Minimal opencode.jsonc carrying one ordered bash block."""
    entries = ",\n".join(f'      "{pattern}": "{tier}"' for pattern, tier in rules)
    return '{\n  "permission": {\n    "bash": {\n' + entries + "\n    }\n  }\n}\n"


def agent_text(
    name: str,
    rules: tuple[tuple[str, str], ...] | None,
    bash_inline: str | None = None,
) -> str:
    """Minimal agent spec: YAML front-matter (optional bash block) + body.

    ``bash_inline`` (#350) writes a flow-style value — a scalar
    (``bash: deny``) or a flow mapping (``bash: {"*": deny}``) — instead
    of the block form; it takes precedence over ``rules``.
    """
    bash_block = ""
    if bash_inline is not None:
        bash_block = f"  bash: {bash_inline}\n"
    elif rules is not None:
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
    agent_bash_inline: dict[str, str] | None = None,
) -> Path:
    """Materialize a throwaway repo (opencode.jsonc + agents/) and return it.

    The four allow-default agents omit the bash block by default (the
    inherited posture); pass agent_bash entries to re-introduce blocks or
    None entries to keep a specific agent bash-free. The three
    non-inheritance agents (#350) default to their pinned shapes
    (scrum-master/code-reviewer block form, coach scalar deny);
    agent_bash_inline entries (#350) write a flow-style value instead and
    take precedence over agent_bash.
    """
    root = Path(tempfile.mkdtemp())
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (root / "opencode.jsonc").write_text(
        config_text if config_text is not None else root_config_text(root_rules),
        encoding="utf-8",
    )
    overrides = agent_bash or {}
    inlines = agent_bash_inline or {}
    for name in ALL_AGENT_NAMES:
        if name in drop_agents:
            continue
        if name in inlines:
            text = agent_text(name, None, bash_inline=inlines[name])
        elif name in NON_INH_DEFAULTS:
            text = agent_text(name, overrides.get(name, NON_INH_DEFAULTS[name]))
        else:
            text = agent_text(name, overrides.get(name))
        (agents_dir / f"{name}.md").write_text(text, encoding="utf-8")
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


class NonInheritanceAgentShapeTests(unittest.TestCase):
    """The three non-inheritance agents carry their pinned bash shapes (#350).

    scrum-master, code-reviewer and coach declare an explicit bash posture
    instead of inheriting the root baseline. The shapes are pinned
    order-sensitively (last-match-wins: agent rules append AFTER the root
    deny tail), the scrum-master pin requires the three trailing
    secret-file denies AFTER its gh/git allows, and flow-style bash values
    (scalar / flow mapping) must be parsed everywhere — a flow-style
    ``bash: {"*": allow}`` header must not be silently blessed.
    """

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

    def assert_gate_passes(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_scrum_master_pinned_shape_passes(self) -> None:
        self.assert_gate_passes(run_checker(build_repo()))

    def test_scrum_master_missing_trailing_denies_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"scrum-master": SCRUM_MASTER_EXPECTED[:4]})
        )
        self.assert_gate_fails(proc, "agents/scrum-master.md", "pinned")

    def test_scrum_master_trailing_denies_before_allows_fails(self) -> None:
        # Order-sensitive: denies placed BEFORE the allows defeat the guard
        # (the allows would still be the last match for credential commands).
        reordered = (
            ("*", "deny"),
            ("*.env*", "deny"),
            ("*.pem*", "deny"),
            ("*.key*", "deny"),
            ("gh issue *", "allow"),
            ("gh pr *", "allow"),
            ("git push origin --delete *", "allow"),
        )
        proc = run_checker(build_repo(agent_bash={"scrum-master": reordered}))
        self.assert_gate_fails(proc, "agents/scrum-master.md", "pinned")

    def test_scrum_master_bash_key_absent_fails(self) -> None:
        # Omitting bash inherits the root "*": allow head — a widening.
        proc = run_checker(build_repo(agent_bash={"scrum-master": None}))
        self.assert_gate_fails(proc, "agents/scrum-master.md", "bash posture missing")

    def test_scrum_master_flow_style_allow_header_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash_inline={"scrum-master": '{"*": allow}'})
        )
        self.assert_gate_fails(proc, "agents/scrum-master.md", "pinned")

    def test_code_reviewer_pinned_shape_passes(self) -> None:
        self.assert_gate_passes(run_checker(build_repo()))

    def test_code_reviewer_missing_deny_head_fails(self) -> None:
        headless = tuple(rule for rule in CODE_REVIEWER_EXPECTED if rule[0] != "*")
        proc = run_checker(build_repo(agent_bash={"code-reviewer": headless}))
        self.assert_gate_fails(proc, "agents/code-reviewer.md", "pinned")

    def test_code_reviewer_secret_file_class_allow_fails(self) -> None:
        widened = CODE_REVIEWER_EXPECTED + (("*.env*", "allow"),)
        proc = run_checker(build_repo(agent_bash={"code-reviewer": widened}))
        self.assert_gate_fails(proc, "agents/code-reviewer.md", "pinned")

    def test_coach_scalar_deny_passes(self) -> None:
        self.assert_gate_passes(run_checker(build_repo()))

    def test_coach_flow_mapping_deny_equivalent_passes(self) -> None:
        # "bash: deny scalar or equivalent": the flow mapping {"*": deny}
        # normalizes to the same single catch-all deny rule.
        proc = run_checker(build_repo(agent_bash_inline={"coach": '{"*": deny}'}))
        self.assert_gate_passes(proc)

    def test_coach_scalar_allow_fails(self) -> None:
        proc = run_checker(build_repo(agent_bash_inline={"coach": "allow"}))
        self.assert_gate_fails(proc, "agents/coach.md", "pinned")

    def test_coach_flow_mapping_allow_fails(self) -> None:
        proc = run_checker(build_repo(agent_bash_inline={"coach": '{"*": allow}'}))
        self.assert_gate_fails(proc, "agents/coach.md", "pinned")

    def test_coach_bash_key_absent_fails(self) -> None:
        proc = run_checker(build_repo(agent_bash={"coach": None}))
        self.assert_gate_fails(proc, "agents/coach.md", "bash posture missing")

    def test_missing_non_inheritance_agent_fails(self) -> None:
        proc = run_checker(build_repo(drop_agents=("coach",)))
        self.assert_gate_fails(proc, "agents/coach.md")

    def test_inheritance_agent_flow_style_allow_header_fails(self) -> None:
        # The #350 coverage gap: a flow-style bash header in an allow-default
        # agent spec used to be silently blessed (only block forms parsed).
        proc = run_checker(build_repo(agent_bash_inline={"architect": '{"*": allow}'}))
        self.assert_gate_fails(
            proc, "agents/architect.md", "re-states the root baseline"
        )

    def test_inheritance_agent_scalar_deny_header_fails(self) -> None:
        # A scalar bash value is parsed and normalized to the catch-all
        # rule, which re-states the root baseline pattern "*".
        proc = run_checker(build_repo(agent_bash_inline={"developer": "deny"}))
        self.assert_gate_fails(
            proc, "agents/developer.md", "re-states the root baseline"
        )


class RealRepositoryTests(unittest.TestCase):
    """Positive control: the real repository satisfies all the invariants."""

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