---
name: gcp-docs
description: "Google Cloud Platform documentation grounding guide: consult and cite official GCP docs (docs.cloud.google.com) via webfetch/websearch before GCP-specific claims; curated docs map for HOME portfolio services; Swiss data-residency regions for @fpittelo projects."
---

# Google Cloud Platform Documentation Grounding Guide

This skill is the authoritative guide for grounding Google Cloud Platform (GCP) work on the **official Google Cloud documentation** for personal projects under **Frederic Pitteloud (@fpittelo)**. It does not teach GCP APIs; it mandates where to verify them and how to cite them.

---

## 1. Grounding Discipline (the mandate)

1. **Consult before asserting.** Before any GCP-specific claim — API and resource names, quotas and limits, region/zone availability, provider or client-library versions, IAM role and permission semantics, or pricing — fetch or search the official documentation and read the relevant page.
2. **Cite the exact URL.** Every architectural spec, ADR, issue, or PR that makes a GCP-specific claim carries the official documentation URL it is grounded on (a deep link, not a product landing page). An uncited GCP-specific claim is a defect.
3. **Official docs over training-data recall.** Recall is not evidence for anything version-, quota-, or price-specific. `docs.cloud.google.com` is the source of truth; `cloud.google.com/docs` serves the same corpus. The canonical documentation home is https://docs.cloud.google.com/docs.
4. **Read-only and credential-free.** Grounding uses the existing `webfetch` / `websearch` tools against public documentation only — no MCP server, no GCP authentication, no token, no scope.
5. **Quote the constraint, not the vibe.** When a quota, limit, or regional constraint drives a design, cite the value and the page it came from; never paraphrase it from memory.

Minimum loop: identify the claim → search/fetch the official docs → verify on the live page → cite URL and value in the deliverable.

---

## 2. Curated Docs Map — HOME-relevant services

| Service / concern | Authoritative entry point | Use it for |
| :--- | :--- | :--- |
| Compute Engine | https://docs.cloud.google.com/compute/docs | VM instances, disks, machine types, maintenance semantics |
| Cloud Storage (GCS) | https://docs.cloud.google.com/storage/docs | Buckets, locations, storage classes, object IAM |
| GCS remote state for OpenTofu | https://opentofu.org/docs/language/settings/backends/gcs/ | Backend configuration, authentication, state locking and object-versioning prerequisites (OpenTofu-owned page; bucket prerequisites: https://docs.cloud.google.com/storage/docs/creating-buckets) |
| Identity and Access Management | https://docs.cloud.google.com/iam/docs | Roles, permissions, service accounts, least privilege |
| Cloud Run | https://docs.cloud.google.com/run/docs | Container services and jobs, regional deployment, IAM |
| BigQuery | https://docs.cloud.google.com/bigquery/docs | Datasets, tables, locations, quotas, pricing |
| VPC networking | https://docs.cloud.google.com/vpc/docs | Networks, subnets, routes, Private Service Connect |
| Regions and zones | https://docs.cloud.google.com/compute/docs/regions-zones | Region/zone availability; data locality via https://docs.cloud.google.com/docs/geography-and-regions |
| MCP servers overview | https://docs.cloud.google.com/mcp/overview | Google Cloud remote MCP servers (future-spike material — see §5) |

---

## 3. Swiss Privacy & Data Residency Anchor

- **Default region:** `europe-west6` (Zürich, Switzerland) for personal GCP workloads that handle personal or sensitive data, per [home-governance](../home-governance/SKILL.md) §2 and mirroring [opentofu-iac](../opentofu-iac/SKILL.md) §1.4.
- **Record the region explicitly** in every spec: VM zone, bucket location, dataset location, Cloud Run region — and cite the page proving the service is offered there. Availability is per service, not per region name.
- **Deviating from `europe-west6`** requires a stated justification in the spec or ADR.

---

## 4. Complement, Not Overlap — `opentofu-iac`

- [opentofu-iac](../opentofu-iac/SKILL.md) owns the **IaC mechanics**: module layout, remote-state wiring, provider pinning, validation gates.
- `gcp-docs` owns **documentation grounding only**: what the GCP fact is, and where it is documented.
- When both apply: verify the GCP fact here, express it in HCL there. This skill never duplicates IaC patterns.

---

## 5. Routing Note — Developer Knowledge MCP (deferred) and `google/skills`

- **Evaluated for #471 (2026-11-21):** Google's Developer Knowledge MCP server (`developerknowledge.googleapis.com/mcp`, tools `search_documents`, `answer_query`, `get_documents`) would automate docs retrieval.
- **Deliberately deferred to a future `type::spike`:** it is a technology introduction requiring a MADR, a **@cyber-security** review (MADR-0008), and GCP authentication. No MCP server, namespace, credential, or scope is wired in this repository (KIS & YAGNI — home-governance §9).
- The official **`google/skills` catalog** is complementary, product-specific reference material (e.g. `gcloud` CLI guidance). It neither replaces this grounding discipline nor is it vendored here.
