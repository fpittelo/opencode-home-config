---
name: release-automation
description: "GitHub platform release automation, semantic version tagging, promotional gates (dev -> qa -> main), and post-release board hygiene orchestration for @fpittelo repositories."
---

# GitHub Platform Release Automation

Use this skill to automate project releases, promotion gates, semantic version tagging, and post-release board hygiene on GitHub repositories under **Frederic Pitteloud (@fpittelo)**.

---

## 1. Release Promotion Lifecycle & Gates

```
[feature/*] --(PR: Clean CI + Review)--> [dev]
                                          |
                        (@fpittelo Approval + Clean CI)
                                          v
                                         [qa]
                                          |
                        (@fpittelo Approval + Clean CI)
                                          v
                                       [main]
                                          |
                   +-----------------------+-----------------------+
                   |                                               |
                   v                                               v
     [Bumped Release Tag vX.Y.Z]                    [@scrum-master Board Hygiene]
     [GitHub Release with Notes]                    [Close Milestone & Board Audit]
```

### Promotion Gate Stages:
1. **Sprint Unit Merges (`feature/*` → `dev`):**
   - Feature branches merge exclusively into `dev` via squash-and-merge (`merge_method: "squash"`).
   - Requires 100% clean CI (0 warnings, 0 failures) and documented `@code-reviewer` approval on GitHub.
2. **Staging Promotion Gate (`dev` → `qa`):**
   - Requires 100% clean GitHub Actions pipeline on `dev`.
   - Requires **mandatory explicit approval from @fpittelo**.
   - Merged into `qa` via promotion PR.
3. **Production Promotion Gate (`qa` → `main`):**
   - Requires 100% clean GitHub Actions pipeline and validation tests on `qa`.
   - Requires **mandatory explicit approval from @fpittelo**.
   - Merged into `main` via promotion PR.
4. **Automated Release Bumping:**
   - A bumped semantic version tag (`vMAJOR.MINOR.PATCH`) is created on `main` and pushed to origin.
   - A formal GitHub Release is created, generating notes from milestone history, closed issues, and merged PRs.
5. **Post-Release Board Hygiene:**
   - Merge to `main` automatically triggers a board hygiene cycle executed by `@scrum-master`.
   - `@scrum-master` audits and closes the completed Sprint Milestone, cleans the board, moves completed items to `status::done`, and generates the Sprint Retrospective issue.

---

## 2. Prerequisites for Release Creation

- Target branch is `main`.
- The GitHub Actions CI/CD pipeline on `main` is completely green (0 warnings, 0 failures).
- Mandatory approval from `@fpittelo` is documented on the promotion PR.
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

| Persona | Release & Promotion Authorization | Responsibilities |
| :--- | :--- | :--- |
| **`@developer`** | ❌ Unauthorized to publish releases or promote branches | Delivers atomic feature branches into `dev` via squash-and-merge. |
| **`@code-reviewer`** | ❌ Unauthorized to publish releases or promote branches | Inspects PRs targeting `dev`, `qa`, and `main`; provides formal decisions. |
| **`@cyber-security`** | ❌ Unauthorized to publish releases or promote branches | Audits secret scanning and dependency vulnerabilities before promotions. |
| **`@architect`** | ✅ Promotion coordination | Prepares promotion specs and coordinates `@fpittelo` approval requests. |
| **`@devops`** | ✅ Release publishing & promotion | Executes branch merges (`dev` → `qa` → `main`) post-approval, tags Git releases, and triggers Docker builds. |
| **`@scrum-master`** | ✅ Board hygiene & milestone closing | Audits GitHub issue board, closes milestone, archives cards, and creates Sprint Retrospective upon release to `main`. |
