---
name: release-automation
description: "GitHub platform release automation, semantic version tagging, tag-from-trunk release gates (MADR-0017), and post-release board hygiene orchestration for @fpittelo repositories."
---

# GitHub Platform Release Automation

Use this skill to automate project releases, semantic version tagging, release gates, and post-release board hygiene on GitHub repositories under **Frederic Pitteloud (@fpittelo)**.

---

## 1. Release Lifecycle & Gates (Trunk+Tag — MADR-0017)

```
[feature/*] --(PR: Clean CI + Review)--> [main (trunk)]
                                              |
                    (@fpittelo Release Approval — one per release)
                                              v
                    +-------------------------+-------------------------+
                    |                                                   |
                    v                                                   v
     [Bumped Release Tag vX.Y.Z on main]            [@scrum-master Board Hygiene]
     [GitHub Release with Notes]                    [Close Sprint Marker & Board Audit]
```

### Release Gate Stages:
1. **Sprint Unit Merges (`feature/*` → `main`):**
   - Feature branches merge exclusively into `main` (the trunk) via squash-and-merge (`merge_method: "squash"`).
   - Requires 100% clean CI (0 warnings, 0 failures) and documented `@code-reviewer` approval on GitHub.
   - **No promotion branches or promotion PRs exist** — `dev`/`qa` are retired; MADR-0017 supersedes MADR-0012's promotion merge method.
2. **Staging Validation (pre-tag):**
   - Performed on the release candidate **before** tagging: the PO validates on his own machine (config repos) or the tagged artifact is deployed to a staging environment (repos with real staging).
3. **Release Approval Gate (one per release):**
   - ONE mandatory explicit approval from `@fpittelo` per release, recorded on the sprint marker or release issue (normative: `home-governance` Rule 5 — SSOT).
4. **Automated Release Bumping:**
   - Under the PO approval, a bumped semantic version tag (`vMAJOR.MINOR.PATCH`) is created on `main` and pushed to origin.
   - A formal GitHub Release is created, generating notes from closed issues and merged PRs.
   - **Agent-executable (MADR-0020):** the release object is published by `@devops` with the native `gh` CLI (`gh release create` with the curated notes body; `gh release edit` for follow-up edits) under the single PO approval. The token is injected inline as `GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}"` (the #304 shell-assignment pattern — **not** the `env` command). Standing manual PO action is **not** required in the normal flow (fallback: the PO can still publish in the UI). **Guardrail:** agents MUST NOT use `gh release delete` — the retired MADR-0016 server intentionally had no delete capability; `gh release delete` is recorded as a bash deny candidate if the PO wants machine-enforced parity.
5. **Post-Release Board Hygiene:**
   - Every release automatically triggers a board hygiene cycle executed by `@scrum-master`.
   - `@scrum-master` audits and closes the completed sprint-marker issue (MADR-0013), cleans the board, moves completed items to `status::done`, and appends the lightweight 3-bullet retro section to the marker closeout (standalone retrospective issue only on major incident — #339).

### Rollback & Hotfix:
- **Rollback:** `git revert` the offending squash commit on `main`, or redeploy the previous tag.
- **Hotfix:** branch `fix/<issue-#>-<slug>` from the released tag `vX.Y.Z` → PR into `main` (same gates) → patch tag `vX.Y.Z+1`.

---

## 2. Prerequisites for Release Creation

- Target branch is `main` (the trunk).
- The GitHub Actions CI/CD pipeline on `main` is completely green (0 warnings, 0 failures).
- Mandatory approval from `@fpittelo` is documented on the sprint marker or release issue.
- Semantic tag has been determined (e.g. `v1.1.0`) and created:
  ```bash
  git tag -a v1.1.0 -m "Release v1.1.0"
  git push origin v1.1.0
  ```

---

## 3. Execution Commands (GitHub CLI)

### Via GitHub CLI (`gh`) — primary (MADR-0020):
```bash
GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}" gh release create v1.1.0 \
  --target main \
  --title "Release v1.1.0" \
  --generate-notes \
  --notes "Automated release generated from closed issues and merged PRs."
```

The token is injected inline as `GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}"` (the #304 shell-assignment pattern — **not** the `env` command). Follow-up edits use `gh release edit v1.1.0 ...` under the same injection.

**Guardrail:** agents MUST NOT use `gh release delete` — the retired MADR-0016 server intentionally had no delete capability; `gh release delete` is recorded as a bash deny candidate if the PO wants machine-enforced parity.

### Fallback: GitHub REST API
The REST endpoints (`POST /repos/{owner}/{repo}/releases`, `PATCH /repos/{owner}/{repo}/releases/{id}`) remain the underlying API, but the `curl` transport is **bash-denied** in this posture — use the `gh` CLI above. A plain-REST fallback is only available through a non-`curl` client if one is ever needed.

---

## 4. Agent Authorization Matrix

| Persona | Release Authorization | Responsibilities |
| :--- | :--- | :--- |
| **`@developer`** | ❌ Unauthorized to publish releases or tag | Delivers atomic feature branches into `main` via squash-and-merge. |
| **`@code-reviewer`** | ❌ Unauthorized to publish releases or tag | Inspects PRs targeting `main`; provides formal decisions. |
| **`@cyber-security`** | ❌ Unauthorized to publish releases or tag | Audits secret scanning and dependency vulnerabilities before releases. |
| **`@architect`** | ✅ Release coordination | Prepares release specs and coordinates `@fpittelo` approval requests. |
| **`@devops`** | ✅ Release tagging & publishing | Under the PO approval, tags Git releases on `main`, triggers Docker builds, and **publishes the GitHub Release object via the native `gh` CLI (`gh release create`; MADR-0020 — sole release-write authority)**. |
| **`@scrum-master`** | ✅ Board hygiene & sprint-marker closing | Audits GitHub issue board, closes the sprint-marker issue (MADR-0013), archives cards, and appends the 3-bullet retro to the marker closeout upon release (#339). |
