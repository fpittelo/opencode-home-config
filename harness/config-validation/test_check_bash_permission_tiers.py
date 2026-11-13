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
     role-deviation patterns (cyber-security: audit-tool allows; devops:
     the MADR-0022 gh CI-triage carve-out). Re-stating any root tier pattern
     in an agent is now the defect, not the requirement.
  3. TRUTH TABLE — the static last-match-wins resolver over the root block
     must reproduce every expected verdict of the MADR-0015 delta.

The known-good fixture is built from the checker's own baseline constants
(single source of truth). Negative cases cover: root ask-tier removal,
root ask-tier reorder, deny-tail removal, the #352 release-delete deny
removal, deny-tail reorder, an allow rule
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

#419 extension (MADR-0024 C1-C4/C8, Podman runtime reconciliation): the
container-runtime deviation is reconciled with the migrated runtime. C1/C2 add
root deny-tail entries `podman system service*` (Docker-API-compatible socket —
the long-lived daemon pattern the migration exists to remove) and
`podman machine*` (VM spawn / guest root), each with a truth-table row and a
per-segment compound-command bypass proof (one denied segment blocks the whole
line). C3 records that a scoped *allow* set is NOT the tightening mechanism (the
root `"*": allow` head already permits every sub-command and an agent bash map
appends AFTER the deny tail, so such allows would be a no-op that trips the #340
duplicate-root defect) — the lever is a root deny plus scoped carve-outs. C4
deletes the dead MADR-0004 `docker *` registry row: posture-neutral, not a
tightening. C8 pins the `--env-file` deny parity as form-dependent (the filename
appears in the command text) and keeps the Podman-only secret-injection evasions
as an explicitly recorded residual rather than a silent widening.

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
        "permission:\n" + bash_block + "  GITHUB_*: allow\n"
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

    def test_root_release_delete_deny_removal_fails(self) -> None:
        # #352 negative case: a root config WITHOUT the `gh release delete*`
        # deny (the pre-#352 deny tail) fails the baseline pin — the MADR-0020
        # no-delete guardrail is machine-enforced, not optional.
        drifted = remove_rule(KNOWN_GOOD_RULES, "gh release delete*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_root_gh_api_deny_removal_fails(self) -> None:
        # MADR-0022 (#401, C5) negative case: a root config WITHOUT the
        # `gh api *` deny fails the baseline pin — the gh guardrail is
        # machine-enforced. `gh run delete*` alone would be bypassable via
        # raw REST (`gh api -X DELETE ...`) while "*" is allow (MADR-0008
        # review on PR #402: the gh api deny is decisive).
        drifted = remove_rule(KNOWN_GOOD_RULES, "gh api *")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "baseline")

    def test_root_gh_workflow_carve_out_deny_removal_fails(self) -> None:
        # MADR-0022 (#401, C6) negative case: removing the `gh workflow *`
        # root deny removes the baseline for the @devops-only write carve-out
        # (the retired actions_run_trigger equivalent) — baseline pin fails.
        drifted = remove_rule(KNOWN_GOOD_RULES, "gh workflow *")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "baseline")

    def test_deny_tail_reorder_fails(self) -> None:
        drifted = swap_rules(KNOWN_GOOD_RULES, "curl*", "wget*")
        proc = run_checker(build_repo(root_rules=drifted))
        self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_allow_interleaved_inside_deny_tail_fails(self) -> None:
        # AC1/C3 (MADR-0024 #419): a blanket `podman *` allow may not be
        # introduced, and no allow may sit inside the deny tail — the pin
        # rejects both (deny rules go LAST, MADR-0004).
        drifted = insert_after(KNOWN_GOOD_RULES, "sudo*", ("podman *", "allow"))
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
        proc = run_checker(build_repo(agent_bash={"developer": (("rm *", "ask"),)}))
        self.assert_gate_fails(proc, "agents/developer.md", "rm *")

    def test_agent_mirroring_whole_block_fails(self) -> None:
        proc = run_checker(build_repo(agent_bash={"architect": KNOWN_GOOD_RULES}))
        self.assert_gate_fails(proc, "agents/architect.md")

    def test_undocumented_role_deviation_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("terraform *", "allow"),)})
        )
        self.assert_gate_fails(proc, "agents/devops.md", "terraform *")

    def test_non_allow_tier_deviation_fails(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("gh workflow *", "ask"),)})
        )
        self.assert_gate_fails(proc, "agents/devops.md", "must be allow-tier")

    def test_documented_devops_deviation_passes(self) -> None:
        proc = run_checker(
            build_repo(agent_bash={"devops": (("gh run rerun*", "allow"),)})
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_documented_cyber_security_deviation_passes(self) -> None:
        allowed = sorted(CHECKER.AGENT_DEVIATIONS["cyber-security.md"])
        rules = tuple((pattern, "allow") for pattern in allowed)
        proc = run_checker(build_repo(agent_bash={"cyber-security": rules}))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_docstring_reflects_root_inheritance_design(self) -> None:
        script_path = CHECKER.__file__
        assert script_path is not None  # module always has a file (mypy strict)
        text = Path(script_path).resolve().read_text(encoding="utf-8")
        self.assertIn("#340", text)
        self.assertIn("inherit", text.lower())


class GhCiTriageCarveOutTests(unittest.TestCase):
    """MADR-0022 (#401) C6/C7: gh CI-triage surface, merged resolution.

    The GITHUB_ACTIONS MCP server is retired (MADR-0022); CI triage is
    re-homed on the pinned gh CLI. The root deny tail denies every CI write
    command (gh workflow *, gh run cancel*, gh run rerun* — the retired
    actions_run_trigger equivalent — plus the C5 destructive/bypass set).
    agents/devops.md carries the @devops-only write carve-out (agent rules
    append AFTER the root deny tail, so its allows re-enable the commands
    for @devops alone); agents/developer.md carries the read-only legibility
    allows (gh run list/view/watch). Both are registered in AGENT_DEVIATIONS
    and allow-tier (the checker rejects anything else).
    """

    def _agent_rules(self, name: str) -> tuple[tuple[str, str], ...]:
        """The documented agent deviations as (pattern, "allow") pairs."""
        return tuple(
            (pattern, "allow")
            for pattern in sorted(CHECKER.AGENT_DEVIATIONS[f"{name}.md"])
        )

    def test_devops_write_carve_out_resolves(self) -> None:
        # C6: @devops regains the retired actions_run_trigger surface via
        # the documented agent append (last-match-wins over the root tail).
        merged = list(CHECKER.BASELINE_ROOT_RULES) + list(self._agent_rules("devops"))
        self.assertEqual(CHECKER.resolve(merged, "gh workflow run ci.yml"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh workflow enable ci.yml"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh workflow disable ci.yml"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh run cancel 12345"), "allow")
        self.assertEqual(
            CHECKER.resolve(merged, "gh run rerun --failed 12345"), "allow"
        )

    def test_devops_carve_out_scoped_no_root_widening(self) -> None:
        # The carve-out does NOT re-enable the C5 destructive/bypass set or
        # the MADR-0020 no-delete parity — @devops's merged posture keeps
        # them denied (scope review: root tail sits before the agent map).
        merged = list(CHECKER.BASELINE_ROOT_RULES) + list(self._agent_rules("devops"))
        self.assertEqual(CHECKER.resolve(merged, "gh run delete 12345"), "deny")
        self.assertEqual(CHECKER.resolve(merged, "gh cache delete --all"), "deny")
        self.assertEqual(CHECKER.resolve(merged, "gh auth token"), "deny")
        self.assertEqual(
            CHECKER.resolve(merged, "gh api -X DELETE repos/o/r/x"), "deny"
        )
        self.assertEqual(CHECKER.resolve(merged, "gh release delete v1.0.0"), "deny")

    def test_developer_read_only_posture_resolves(self) -> None:
        # C7: @developer's explicit posture — read-only CI triage only
        # (gh run list/view/watch); every CI write command stays root-denied
        # (the retired MCP partial-allow guarantee is preserved on gh).
        merged = list(CHECKER.BASELINE_ROOT_RULES) + list(
            self._agent_rules("developer")
        )
        self.assertEqual(CHECKER.resolve(merged, "gh run list"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh run view --log 12345"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh run watch 12345"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "gh workflow run ci.yml"), "deny")
        self.assertEqual(CHECKER.resolve(merged, "gh run cancel 12345"), "deny")
        self.assertEqual(CHECKER.resolve(merged, "gh run rerun 12345"), "deny")
        self.assertEqual(CHECKER.resolve(merged, "gh run delete 12345"), "deny")

    def test_root_baseline_denies_gh_writes_for_inheriting_agents(self) -> None:
        # Agents with NO bash block (architect, cyber-security) inherit the
        # root tail: zero CI-write capability (the retired MCP namespace
        # wildcard deny is preserved as a root bash deny tail append).
        for command in (
            "gh workflow run ci.yml",
            "gh run cancel 12345",
            "gh run rerun 12345",
            "gh run delete 12345",
            "gh cache delete --all",
            "gh auth token",
            "gh api -X DELETE repos/o/r/x",
        ):
            self.assertEqual(
                CHECKER.resolve(list(CHECKER.BASELINE_ROOT_RULES), command),
                "deny",
                f"{command!r} must stay root-denied for inheriting agents",
            )
        # The read surface is untouched: list/view/watch stay allowed by the
        # root "*" head (C7 read-only posture; path-reviewed `gh run download`
        # also stays allowed — read-only artifact fetch, MADR-0022 C7).
        for command in ("gh run list", "gh run view --log 1", "gh run download 1"):
            self.assertEqual(
                CHECKER.resolve(list(CHECKER.BASELINE_ROOT_RULES), command),
                "allow",
                f"{command!r} must stay root-allowed",
            )

    def test_devops_developer_deviation_patterns_registered(self) -> None:
        # The carve-out/legibility patterns are exactly the documented
        # deviations — no other pattern may appear in the agent maps, and
        # agents that inherit the root baseline carry none. MADR-0024 (#419,
        # C4): the dead MADR-0004 `docker *` row is gone; C3: no podman
        # pattern is registered in either direction.
        self.assertEqual(
            CHECKER.AGENT_DEVIATIONS["devops.md"],
            frozenset({"gh workflow *", "gh run cancel*", "gh run rerun*"}),
        )
        self.assertEqual(
            CHECKER.AGENT_DEVIATIONS["developer.md"],
            frozenset({"gh run list*", "gh run view*", "gh run watch*"}),
        )
        self.assertEqual(CHECKER.AGENT_DEVIATIONS["architect.md"], frozenset())
        # cyber-security.md keeps its MADR-0004 audit-tool deviations,
        # untouched by the MADR-0022 gh CI-triage change (#401).
        self.assertIn("gitleaks*", CHECKER.AGENT_DEVIATIONS["cyber-security.md"])


class PodmanRuntimeReconciliationTests(unittest.TestCase):
    """MADR-0024 (#419) C1-C4/C8: the Podman permission reconciliation.

    C1/C2 — `podman system service*` (Docker-API-compatible socket: the
    long-lived daemon pattern the migration exists to remove) and
    `podman machine*` (VM spawn / guest root) are root deny-tail entries
    with truth-table rows; neither is escalation above uid 1000 under
    rootless mode. C3 — no podman pattern is registered in
    AGENT_DEVIATIONS: a scoped *allow* set tightens nothing (the root
    `"*": allow` head already permits every sub-command and an agent bash
    map appends AFTER the deny tail) and would trip the #340
    duplicate-root defect. C4 — the MADR-0004 `docker *` row was a DEAD
    REGISTRY ROW (no such rule in agents/devops.md); deleting it is
    posture-neutral. C8 — the `--env-file` deny parity is form-dependent
    (the filename appears in the command text), and the Podman-only
    secret-injection evasions stay a recorded residual.
    """

    PODMAN_DENIES = ("podman system service*", "podman machine*")

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

    def test_deny_tail_entries_are_appended_last(self) -> None:
        # Order is semantic (deny rules LAST, MADR-0004): the two new entries
        # are the final rules of the pinned root block.
        self.assertEqual(CHECKER.BASELINE_DENY_TAIL[-2:], self.PODMAN_DENIES)
        self.assertEqual(
            [pattern for pattern, _ in CHECKER.BASELINE_ROOT_RULES][-2:],
            list(self.PODMAN_DENIES),
        )

    def test_system_service_and_machine_are_denied(self) -> None:
        merged = list(CHECKER.BASELINE_ROOT_RULES)
        for command in (
            "podman system service",
            "podman system service --time=0 unix:///run/user/1000/podman.sock",
            "podman machine init",
            "podman machine ssh",
            "podman machine ls",
        ):
            self.assertEqual(
                CHECKER.resolve(merged, command),
                "deny",
                f"{command!r} must be root-denied (MADR-0024 C1/C2)",
            )

    def test_deny_is_subcommand_scoped_not_a_blanket(self) -> None:
        # Only the API-socket escape was taken; the deny is not a
        # `podman system *` blanket (the remainder is the recorded residual).
        self.assertEqual(
            CHECKER.resolve(list(CHECKER.BASELINE_ROOT_RULES), "podman system df"),
            "allow",
        )

    def test_ordinary_podman_surface_stays_allowed(self) -> None:
        # The migration is not broken: the run/pull/inspect surface the
        # COACH_* workflow uses keeps its unprompted posture.
        merged = list(CHECKER.BASELINE_ROOT_RULES)
        for command in (
            "podman pull ghcr.io/fpittelo/coach:dev",
            "podman run -i --rm -e VAR=1 ghcr.io/fpittelo/coach:dev",
            "podman ps -a",
            "podman logs coach-dev",
        ):
            self.assertEqual(
                CHECKER.resolve(merged, command),
                "allow",
                f"{command!r} must stay allowed (the migration depends on it)",
            )

    def test_env_file_deny_parity_is_filename_scoped(self) -> None:
        # C8 negative test: `podman run --env-file x.env` IS denied — because
        # the filename sits in the command text (the #167 filename glob), not
        # because the mechanism is constrained. The docker form keeps the
        # same verdict, so the documented Docker case has parity.
        merged = list(CHECKER.BASELINE_ROOT_RULES)
        self.assertEqual(
            CHECKER.resolve(
                merged, "podman run -i --rm --env-file x.env ghcr.io/f/p/coach:dev"
            ),
            "deny",
        )
        self.assertEqual(
            CHECKER.resolve(merged, "docker run --env-file x.env image"), "deny"
        )

    def test_podman_only_evasions_are_a_recorded_residual(self) -> None:
        # C8 residual, pinned explicitly (same class as the accepted
        # recursive-read bypass, #362): a secret injected without naming a
        # credential FILENAME is not matched by the command-string deny, and
        # closing that class is an upstream limitation
        # (anomalyco/opencode#56545) — so it is recorded, never silent.
        merged = list(CHECKER.BASELINE_ROOT_RULES)
        for command in (
            "podman run --secret=coach_token,type=env -i --rm x",
            "podman create -e VAR=1 ghcr.io/fpittelo/coach:dev",
            "podman start 7f3a1c9d",
        ):
            self.assertEqual(
                CHECKER.resolve(merged, command),
                "allow",
                f"{command!r} is an accepted residual (MADR-0024 D3/C8) — "
                f"if this changes, update the MADR and arc42 §3 too",
            )

    def test_unshare_is_recorded_as_residual_not_a_deviation(self) -> None:
        # AC3: `podman unshare` (chown to arbitrary UIDs) does not silently
        # widen posture — it is an explicit residual, not a registry entry:
        # the mapping is bounded to the invoking uid + subuid range (no
        # escalation above uid 1000), and it is the documented remediation
        # for subuid-owned bind-mount artifacts (#418, C6).
        self.assertEqual(
            CHECKER.resolve(
                list(CHECKER.BASELINE_ROOT_RULES),
                "podman unshare chown -R 1000:1000 /workspace",
            ),
            "allow",
        )
        self.assertNotIn("podman unshare*", CHECKER.BASELINE_DENY_TAIL)

    def test_compound_command_one_denied_segment_blocks(self) -> None:
        # #419 bypass proof: the documented evaluation splits `&&` / `;` / `|`
        # and judges every segment, so appending an allowed segment cannot
        # launder a denied one.
        merged = list(CHECKER.BASELINE_ROOT_RULES)
        self.assertTrue(CHECKER.COMPOUND_TRUTH_TABLE)
        for command, expected in CHECKER.COMPOUND_TRUTH_TABLE:
            self.assertEqual(
                CHECKER.resolve_command(merged, command),
                expected,
                f"compound {command!r} must resolve to {expected!r}",
            )
        # Whole-line (non-segment) resolution is what the splitter corrects:
        # a single glob cannot see the denied tail of the line.
        self.assertEqual(
            CHECKER.resolve(merged, "podman pull x && podman machine init"),
            "allow",
        )
        self.assertEqual(
            CHECKER.resolve_command(merged, "podman pull x && podman machine init"),
            "deny",
        )

    def test_root_baseline_pin_fails_without_the_podman_denies(self) -> None:
        for pattern in self.PODMAN_DENIES:
            with self.subTest(pattern=pattern):
                drifted = remove_rule(KNOWN_GOOD_RULES, pattern)
                proc = run_checker(build_repo(root_rules=drifted))
                self.assert_gate_fails(proc, "opencode.jsonc", "deny tail")

    def test_no_podman_pattern_registered_in_any_agent_deviation(self) -> None:
        # C3: the scoped-allow lever is explicitly NOT used — neither an
        # allow nor a deny for the runtime family may be registered as an
        # agent deviation.
        for name, patterns in CHECKER.AGENT_DEVIATIONS.items():
            with self.subTest(agent=name):
                self.assertFalse(
                    [pattern for pattern in patterns if "podman" in pattern],
                    f"{name} must register no podman pattern (#419, C3)",
                )

    def test_devops_agent_spec_carries_no_container_runtime_rule(self) -> None:
        # C4 posture-neutral proof: agents/devops.md carries no runtime rule
        # before or after the reconciliation (the registry row was dead).
        agent = REPO_ROOT / "agents" / "devops.md"
        present, rules = CHECKER.agent_bash(REPO_ROOT, agent, [])
        self.assertTrue(present, "agents/devops.md carries the gh carve-out map")
        for pattern, _ in rules:
            self.assertNotIn("docker", pattern)
            self.assertNotIn("podman", pattern)


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

    def test_code_reviewer_old_shape_without_trailing_denies_fails(self) -> None:
        # #358 negative case: the pre-#358 shape (allows, no trailing
        # secret-file denies) is the append-override vulnerability — agent
        # rules append AFTER the root deny tail, so `cat *` re-enabled
        # credential-file reads (e.g. `cat .secrets-home.env`). It must
        # now fail the pin.
        old_shape = (
            ("*", "deny"),
            ("git status *", "allow"),
            ("git diff *", "allow"),
            ("git rev-parse *", "allow"),
            ("git cat-file *", "allow"),
            ("cat *", "allow"),
            ("grep *", "allow"),
            ("ls *", "allow"),
        )
        proc = run_checker(build_repo(agent_bash={"code-reviewer": old_shape}))
        self.assert_gate_fails(proc, "agents/code-reviewer.md", "pinned")

    def test_code_reviewer_trailing_denies_close_append_override(self) -> None:
        # #358 semantic guard: with the pinned (new) shape appended after
        # the root baseline, a credential-file read must resolve to deny
        # under last-match-wins.
        merged = list(CHECKER.BASELINE_ROOT_RULES) + list(CODE_REVIEWER_EXPECTED)
        self.assertEqual(
            CHECKER.resolve(
                merged, "cat /home/frede/.config/opencode/.secrets-home.env"
            ),
            "deny",
        )
        # Zero capability cost: ordinary review reads stay allowed.
        self.assertEqual(CHECKER.resolve(merged, "cat src/main.py"), "allow")
        self.assertEqual(CHECKER.resolve(merged, "git diff main"), "allow")

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
        # #340 + MADR-0022 (#401): architect and cyber-security still omit
        # the bash block (pure root inheritance); devops and developer carry
        # ONLY their registered gh CI-triage deviations (carve-out C6 /
        # legibility allows C7) — the checker verifies they re-state no root
        # pattern and are allow-tier only.
        for name in ("architect", "cyber-security"):
            front_matter = (
                (REPO_ROOT / "agents" / f"{name}.md")
                .read_text(encoding="utf-8")
                .split("---", 2)[1]
            )
            self.assertNotIn(
                "  bash:",
                front_matter,
                f"agents/{name}.md still re-states bash rules — run the "
                f"root-inheritance dedup (#340)",
            )
        for name in ("devops", "developer"):
            front_matter = (
                (REPO_ROOT / "agents" / f"{name}.md")
                .read_text(encoding="utf-8")
                .split("---", 2)[1]
            )
            self.assertIn(
                "  bash:",
                front_matter,
                f"agents/{name}.md must carry the MADR-0022 gh "
                f"CI-triage bash posture (C6/C7)",
            )


if __name__ == "__main__":
    unittest.main()
