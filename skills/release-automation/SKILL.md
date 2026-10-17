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
   - **Agent-executable since MADR-0016 (#323):** the release object is published by `@devops` via the `GITHUB_RELEASES` MCP server (`create_release` with the curated notes body; `update_release` for follow-up edits). The official pinned `github-mcp-server` remains read-only for releases — only these two home-grown tools write. Standing manual PO action is **not** required in the normal flow (fallback: the PO can still publish in the UI, or edit/revert via `gh`, if `GITHUB_RELEASES` is unavailable; the tool intentionally has no `delete_release` — MADR-0016 YAGNI — so an erroneous publish is PO-disposal material).
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

## 3. Execution Commands (GitHub CLI / API)

### Via GitHub CLI (`gh`):
```bash
gh release create v1.1.0 \
  --target main \
  --title "Release v1.1.0" \
  --generate-notes \
  --notes "Automated release generated from milestone history, closed issues, and merged PRs."
```

### Via GitHub REST API using `$GITHUB_PERSONAL_ACCESS_TOKEN`:
```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_PERSONAL_ACCESS_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/:owner/:repo/releases \
  -d '{
    "tag_name": "v1.1.0",
    "target_commitish": "main",
    "name": "Release v1.1.0",
    "body": "Automated release generated from milestone history and closed issues.",
    "draft": false,
    "prerelease": false,
    "generate_release_notes": true
  }'
```

---

## 4. Agent Authorization Matrix

| Persona | Release Authorization | Responsibilities |
| :--- | :--- | :--- |
| **`@developer`** | ❌ Unauthorized to publish releases or tag | Delivers atomic feature branches into `main` via squash-and-merge. |
| **`@code-reviewer`** | ❌ Unauthorized to publish releases or tag | Inspects PRs targeting `main`; provides formal decisions. |
| **`@cyber-security`** | ❌ Unauthorized to publish releases or tag | Audits secret scanning and dependency vulnerabilities before releases. |
| **`@architect`** | ✅ Release coordination | Prepares release specs and coordinates `@fpittelo` approval requests. |
| **`@devops`** | ✅ Release tagging & publishing | Under the PO approval, tags Git releases on `main`, triggers Docker builds, and **publishes the GitHub Release object via `GITHUB_RELEASES` MCP (MADR-0016 — sole release-write authority)**. |
| **`@scrum-master`** | ✅ Board hygiene & sprint-marker closing | Audits GitHub issue board, closes the sprint-marker issue (MADR-0013), archives cards, and appends the 3-bullet retro to the marker closeout upon release (#339). |
