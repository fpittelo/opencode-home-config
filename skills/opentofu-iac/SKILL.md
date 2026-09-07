---
name: opentofu-iac
description: "Infrastructure as Code (IaC) engineering guide using OpenTofu and Terraform for GCP and Azure cloud workloads, remote state management, security hardening, and CI/CD quality gates for @fpittelo projects."
---

# OpenTofu & Terraform Infrastructure as Code (IaC) Guide

This skill is the authoritative guide for engineering Infrastructure as Code (IaC) using **OpenTofu (>= 1.6+)** and **Terraform** for personal cloud workloads across Google Cloud Platform (GCP) and Microsoft Azure under **Frederic Pitteloud (@fpittelo)**.

---

## 1. Core IaC Engineering Principles

1. **Declarative & Idempotent:** Infrastructure state is completely defined in code. Running `tofu apply` multiple times produces identical outcomes.
2. **Strict Remote State Isolation:** State files must never be committed to Git. State is stored in encrypted, versioned remote backends (GCS / Azure Blob) with state locking.
3. **Zero Hardcoded Secrets:** Zero plain-text credentials, API keys, or private keys in code. Use GCP Secret Manager or Azure Key Vault with dynamic data sources.
4. **Swiss Privacy & Data Residency:** Personal workloads handling sensitive data must specify European/Swiss regions (e.g., `europe-west6` Zürich for GCP; `switzerlandnorth` for Azure).
5. **Zero-Warning Quality Gates:** All IaC repositories must pass `tofu fmt -check`, `tofu validate`, `tflint`, and security scanning before any PR merge.

---

## 2. Standard Repository & Module Structure

Every HOME IaC repository (e.g., `iaac-gcp-vm`, `iaac-gcp-data-mgt`) adheres to this standard directory structure:

```
iaac-gcp-<workload>/
├── .github/
│   └── workflows/
│       └── iac-pipeline.yml     # Zero-warning CI/CD pipeline (plan/apply)
├── modules/                     # Reusable local submodules (if complex)
│   └── compute/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── backend.tf                   # Remote backend configuration (GCS / Azure)
├── versions.tf                  # OpenTofu and provider version constraints
├── providers.tf                 # Provider configurations & default tags
├── variables.tf                 # Strongly typed input variables with descriptions
├── main.tf                      # Primary resource orchestrations
├── outputs.tf                   # Output attributes (IDs, endpoints, non-sensitive)
├── terraform.tfvars.example     # Example variable values (NEVER commit terraform.tfvars)
├── .tflint.hcl                  # TFLint configuration
├── .gitignore                   # Ignore .terraform/, *.tfstate, *.tfvars
└── README.md
```

---

## 3. Version Pinning & Provider Configurations (`versions.tf`)

Always pin OpenTofu core and provider versions strictly:

```hcl
# versions.tf
terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6.0"
    }
  }
}
```

---

## 4. Remote State & Locking Configurations (`backend.tf`)

### A. Google Cloud Platform (GCS Backend):
```hcl
# backend.tf (GCP)
terraform {
  backend "gcs" {
    bucket = "fpittelo-tofu-state-europe-west6"
    prefix = "iaac-gcp-vm/state"
  }
}
```
*Prerequisites for GCS State Bucket:*
- Uniform bucket-level access enabled.
- Object versioning enabled (prevents accidental state destruction).
- Region: `europe-west6` (Zürich).

### B. Microsoft Azure (Azure Blob Backend):
```hcl
# backend.tf (Azure)
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-fpittelo-tfstate"
    storage_account_name = "stfpittelotofu"
    container_name       = "tfstate"
    key                  = "iaac-azure-workload.tfstate"
  }
}
```

---

## 5. Security Hardening & Secret Management

1. **Secret Resolution via Secret Managers:**
   ```hcl
   # Read secrets dynamically from GCP Secret Manager
   data "google_secret_manager_secret_version" "db_password" {
     secret  = "database-master-password"
     version = "latest"
   }
   ```
2. **Sensitive Variable Flagging:**
   ```hcl
   variable "admin_password" {
     type        = string
     description = "Admin password retrieved from secure vault"
     sensitive   = true
   }
   ```
3. **Least-Privilege Service Accounts:**
   - Create dedicated IAM service accounts per workload; never bind default Compute Engine service accounts with broad Editor privileges.
   - Restrict roles to exact resource scopes (e.g., `roles/storage.objectViewer`, `roles/logging.logWriter`).

---

## 6. Pre-Flight Quality Gates & Local Verification

Before pushing code or opening a PR to `dev`, execute all local verification steps:

```bash
# 1. Format check
tofu fmt -check -recursive

# 2. Syntax & internal consistency validation
tofu init -backend=false
tofu validate

# 3. Linter checks (TFLint)
tflint --init
tflint --recursive

# 4. Security & Compliance Scan
checkov -d . --framework terraform --quiet --compact
```

---

## 7. CI/CD GitHub Actions Pipeline Blueprint (`.github/workflows/iac-pipeline.yml`)

```yaml
name: IaC Pipeline

on:
  push:
    branches: [dev, qa, main]
  pull_request:
    branches: [dev, qa, main]

permissions:
  contents: read
  pull-requests: write
  id-token: write

jobs:
  validate-and-lint:
    name: Lint, Validate & Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: opentofu/setup-opentofu@v1
        with:
          tofu_version: "1.8.0"

      - name: OpenTofu Format Check
        run: tofu fmt -check -recursive

      - name: OpenTofu Validate
        run: |
          tofu init -backend=false
          tofu validate

      - name: Setup TFLint
        uses: terraform-linters/setup-tflint@v4
      - name: Run TFLint
        run: |
          tflint --init
          tflint --recursive

      - name: Checkov Security Scan
        uses: bridgecrewio/checkov-action@master
        with:
          framework: terraform
          output_format: cli
          soft_fail: false

  speculative-plan:
    name: Speculative Plan (PR Gate)
    needs: validate-and-lint
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: opentofu/setup-opentofu@v1
      - name: Authenticate to Cloud Provider
        # Use OpenID Connect (OIDC) Workload Identity Federation
        run: echo "Authenticating via Workload Identity..."
      - name: Tofu Init & Plan
        run: |
          tofu init
          tofu plan -no-color -out=tfplan
```
