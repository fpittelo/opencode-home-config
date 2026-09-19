# 6. Runtime View

*Status: seeded (Sprint 03, STORY-02 #59).*

## 6.1 Scenario: Autonomous Issue-by-Issue Delivery Loop

**Trigger:** a sprint milestone is active with at least one `status::todo` issue, and @fpittelo has authorized the loop.

```mermaid
sequenceDiagram
    participant SM as @scrum-master
    participant DEV as @developer
    participant CR as @code-reviewer (@devfpittelo)
    participant GH as GitHub (board + CI)

    SM->>GH: Pick next status::todo issue (DoR check, WIP limit 1)
    SM->>GH: label → status::in-progress + kickoff comment
    DEV->>GH: branch feature/<issue#>-<slug> off dev
    DEV->>DEV: implement (TDD where applicable) + local pre-flight (0 warnings)
    DEV->>GH: open PR → dev (Resolves #N)
    SM->>GH: label → status::review
    CR->>GH: inspect diff, verify ACs, formal APPROVE (as @devfpittelo)
    DEV->>GH: squash-merge PR into dev
    SM->>GH: verify 5-point DoD, close issue (status::done)
    SM->>SM: trigger next Ready story (WIP limit 1)
```

**Postconditions:** issue closed with full traceability (squash SHA, PR, CI run, review links); `dev` advanced by exactly one squash commit.

**Failure modes:** pre-flight or CI failure → developer self-remediation (max 3 attempts, then `blocker::active` escalation to @architect per the circuit breaker).

## 6.2 Scenario: Promotion & Release (human-gated)

**Trigger:** all sprint deliverables merged into `dev`.

1. @fpittelo explicitly approves → @devops merges `dev` → `qa` (CI must be green).
2. @fpittelo explicitly approves → @devops merges `qa` → `main`.
3. Release tag `vX.Y.Z` + GitHub Release; @scrum-master runs board hygiene (audit, label cleanup, milestone close, retrospective, next-sprint initialization).

## 6.3 Scenario: Architecture Change → Documentation Update

**Trigger:** any change to agents, skills, MCP servers, or policies.

1. @architect identifies affected arc42 sections via the update-trigger table (`arc42-documentation` skill §4).
2. The arc42 update travels **in the same feature branch and PR** as the change.
3. @code-reviewer verifies documentation parity alongside the code/config change.