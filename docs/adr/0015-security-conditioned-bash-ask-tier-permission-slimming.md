# MADR-0015: Security-conditioned bash ask-tier permission slimming

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @architect (spec), @cyber-security (MADR-0008 security approval with conditions), @fpittelo (PO mandate, grooming approval 2026-10-17)

## Context

The HOME agent fleet runs under a three-tier bash permission model introduced by MADR-0004 (`allow` / `ask` / `deny`; last-match-wins pattern engine). The `ask` tier, while safety-valuable, is the primary friction source in the autonomous loop: every `rm`, `chmod`, or `pip install` invocation halts an in-flight agent task awaiting PO confirmation (recorded as issue #308 "Deliverable C: ask-tier permission slimming").

Trimming this tier is a Tier-1 security change (MADR-0008 Security Impact Routing): it directly modifies what agents may perform *without human confirmation*. Two hard constraints apply:

1. The `deny` tier — network fetchers (`curl*`, `wget*`), interpreters (`bash -c *`, `sh *`, `python* -c*`), process-environment readers (`printenv*`, `env`), and secret-file globs (`*.env*`, `*.pem*`, `*.key*`) — is the load-bearing wall of fleet isolation and must not be weakened.
2. The pattern engine matches **command text, not resolved paths or expanded globs** — so any allow rule must be argued against the *text* an attacker could submit, and the ask/deny tiers are duplicated verbatim in the four allow-default agent specs (`agents/architect.md`, `agents/developer.md`, `agents/devops.md`, `agents/cyber-security.md`), making single-file edits a fragmentation hazard.

A blocking @cyber-security review (2026-10-17, embedded in issue #320) produced per-pattern verdicts and a six-condition approval.

## Decision Drivers

- Loop autonomy: PO-confirmation prompts on low-blast-radius operations stall the WIP-1 autonomous cycle (issue #308 PO friction report).
- Irreversibility: `rm` is unrecoverable outside git; workspaces contain `.env` secret siblings.
- Secrets adjacency: file permission changes can widen read exposure on non-denied credential paths (`~/.aws/credentials`, `~/.netrc`, `~/.docker/config.json` carry no deny-glob suffix).
- Supply chain: package-install commands execute third-party build/install hooks; the pattern engine cannot express "pinned requirements only".
- Drift control: tiers are mirrored across five files; editing one without the others silently changes the fleet's effective policy.
- Continuous verification: the config-validation harness (15 gates) is the established regression mechanism; KIS/YAGNI mandates the smallest diff that satisfies the acceptance criteria.

## Considered Options

### Option 1: Blanket trims — allow `rm ./*`, `chmod +x *`, demote `pip install*` to allow

- Pros: Maximum friction reduction; near-zero diff.
- Cons: Rejected outright by the security review. `rm ./*` deletes a sibling `.env` without matching `*.env*` (irrecoverable Tampering); `chmod +x *` is an execution primitive on untrusted files (Elevation); allowing package installs hands agents arbitrary supply-chain code execution with no mitigating checkpoint. Violates drivers 1–4.

### Option 2: Security-conditioned narrow delta (chosen)

- Pros: Trims friction exactly where blast radius is provably bounded (a sanctioned scratch directory; restrictive-only permission changes), closes a real pre-existing ask-tier bypass discovered during the review (`pip3 install*`, `uv pip install*`, `*-m pip install*` all fell through to `allow`), keeps the deny tail untouched, and adds a drift-guard + truth-table regression test so the mirrored five-file structure is CI-enforced.
- Cons: Friction reduction is modest — most `rm`/`pip` remain ask. Accepted: the PO's pain was auto-loop interruption, not the existence of prompts.
- Risks embedded in the delta by design: at most consulted risk lines are string-based (`/tmp/opencode/*` does not resolve `..`), documented in Consequences.

### Option 3: Do nothing; rely on ask-confirmations

- Pros: Zero security change; zero diff.
- Cons: Does not address the recorded PO friction (#308 Deliverable C remains unsatisfied); leaves the discovered pip bypass open. Rejected as non-responsive to the issue.

## Decision Outcome

Chosen option: **"Security-conditioned narrow delta"**, because it is the only option that simultaneously satisfies the PO friction driver, survives the MADR-0008 review, and closes the discovered bypass. Every moved line traces to a security verdict; every rejected line traces to a STRIDE rationale, so future re-litigation starts from a documented baseline.

The approved delta (the complete and only permitted change set):

New `allow` lines (inserted after the corresponding `ask` rule, before the deny tail):

- `"rm /tmp/opencode/*": "allow"` — sanctioned agent scratch path
- `"rm -r /tmp/opencode/*": "allow"`
- `"chmod 600 *": "allow"` — restrictive-only; cannot widen exposure
- `"chmod 700 *": "allow"`

New `ask` lines (supply-chain parity, closing the pre-existing bypass):

- `"pip3 install*": "ask"`
- `"uv pip install*": "ask"`
- `"*-m pip install*": "ask"`

Explicitly rejected by security: `"rm ./*"` (evades `*.env*` by string matching), `"chmod 755 *"` (grants read on non-denied secret paths).

Delivered as one PR: mirrored identical insertions in `opencode.jsonc` and the four allow-default agent specs, plus `harness/config-validation/check_bash_permission_tiers.py` + its unittest (drift guard across the five locations, deny-tail-identical-to-baseline assertion, last-match-wins truth table), registered as gate 16/16 in `harness/run-config-gate.sh` and the CI port.

## Consequences

- **Positive:** Autonomous loop no longer interrupts for workspace-scoped scratch cleanup or restrictive-only permission fixes; parity holes in the package-install ask surface are closed; five-file tier mirroring becomes CI-enforced rather than convention-only.
- **Negative:** Friction reduction is narrow (most `rm *`, `chmod *`, `pip install*` invocations still require PO confirmation). `rm /tmp/opencode/*` does not resolve path traversal — a `..`-suffixed argument can reach outside the sanctioned directory. `chmod 600/700 <absolute path>` remains theoretically abusable against system files. `*: allow` stays a command-text filter, not a sandbox.
- **Mitigations:** `-rf` forms remain deny-tier (`rm -rf /*` head of the deny tail) — truth-table asserted; traversal gap accepted under the MADR-0004 threat model (tier checkpoints stop accidents, not determined agents) and recorded here; the drift-guard test turns any future unmirrored edit into a red gate; the deny tail is asserted byte-identical to this document's baseline in every CI run.

Security impact review: @cyber-security, 2026-10-17 — APPROVED with conditions 1–6 (deny tail intact; delta limited to the seven lines; rejected patterns excluded; five-file mirroring + drift guard in same PR; checker + green 16-gate run; this MADR indexed before the config change). Conditions 1–5 execute in issue #320 Slice B; condition 6 is satisfied by this document.