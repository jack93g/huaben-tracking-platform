# Decisions

A log of the decisions that shape this platform. Each entry says what was decided, why, and what follows from it. Entries are never deleted: a reversed decision gets a new entry that supersedes the old one.

This repository is public, so entries leave out individual account names, organization and billing account IDs, and anything else that only helps an attacker.

## Accepted

### D-001: Three GCP projects: dev, prod, and admin

*Accepted 2026-09-26 · TP-0*

- **Decision:** `huaben-tracking-platform-dev` and `huaben-tracking-platform-prod` hold the two environments. `huaben-tracking-platform-admin` holds only the bootstrap resources: the Terraform state bucket, the Workload Identity Federation pool, and the CI service accounts.
- **Why:** Access to prod shouldn't include access to the Terraform state or the CI identities. Deleting or rebuilding an environment also can't break the tooling that manages it. A separate staging environment isn't needed yet, because there's no hosted copy of the app to test against: the dev frontend is `localhost`.
- **Consequences:** Project IDs are permanent, and a deleted project's ID can never be reused. Projects are moved, never recreated.

### D-002: Cloud Identity Free on `huaben.app`, with access through groups only

*Accepted 2026-09-26 · TP-0*

- **Decision:** GCP identities are Cloud Identity accounts on `huaben.app`, not personal Gmail accounts. There are two super admins, one for administration and one break-glass account whose credentials are kept offline, plus a separate day-to-day account. IAM is granted only to groups: `gcp-organization-admins@`, `gcp-billing-admins@`, and `gcp-platform-admins@`. 2-step verification is enforced.
- **Why:** Group-based access means adding or removing a person is a membership change, not an IAM change. Keeping a personal account out of the org reduces the number of accounts that can reach infrastructure or billing.
- **Consequences:** The personal Gmail account was removed from the projects and the billing account (2026-09-27). It still owns the Google Payments profile (card and invoices), which grants no GCP access.

### D-003: Projects live in the `huaben.app` organization

*Accepted 2026-09-26 · TP-0*

- **Decision:** The three projects were moved into the `huaben.app` organization. The TP-0 bootstrap creates a `huaben` folder, moves the projects into it, and sets `gcp.resourceLocations = in:eu-locations` on the folder.
- **Why:** The organization enforces Google's secure-by-default policies: no service account key creation or upload, domain-restricted sharing, uniform bucket-level access, and no automatic Editor grants to default service accounts. That makes "no service account keys" something GCP enforces rather than a convention. The location policy keeps data in the EU.
- **Consequences:**
  - Domain-restricted sharing blocks `allUsers`, so public Cloud Run services disable the invoker IAM check instead (TP-3).
  - The organization's Essential Contacts may only be `huaben.app` addresses (see D-008).
  - A project can't be moved back out of an organization without contacting Google support.

### D-004: The bootstrap is applied locally, once, into the admin project

*Accepted 2026-09-26 · TP-0*

- **Decision:** `infra/bootstrap` is applied by a person with their own credentials. It has its own state. Everything after it is applied by CI.
- **Why:** CI can't create the identity it authenticates with.
- **Consequences:** The bootstrap procedure must be documented in the README, because it's rarely run and easy to forget.

### D-005: Budgets are managed by hand, outside Terraform

*Accepted 2026-09-27 · TP-0*

- **Decision:**
  - The budgets are €5/month for dev, €5/month for prod, and €10/month across the whole billing account, with alerts at 50%, 90%, and 100%. The billing account is in EUR.
  - They were created with `gcloud billing budgets create`, and the commands are in the README.
- **Why:** Budgets are set once and rarely change. Keeping them out of Terraform means no Terraform identity needs budget permissions on the billing account.
- **Consequences:** CI service accounts never get billing account permissions. Budgets alert but don't cap spending.

### D-006: Tooling: Terraform, mise, and uv

*Accepted 2026-09-27 · TP-0*

- **Decision:**
  - Terraform, not OpenTofu.
  - `mise.toml` pins every tool version: Terraform, tflint, gitleaks, Python, and uv.
  - uv manages the Python dependencies in `pyproject.toml` and `uv.lock`.
  - CI installs tools with `jdx/mise-action`, which reads the same file.
- **Why:** One file keeps local and CI versions identical. A Terraform version mismatch between local and CI can make one refuse to read state that the other wrote.
- **Consequences:**
  - Upgrading a tool is a one-line change to `mise.toml`, reviewed in a PR.
  - Python is pinned to 3.13 because `dbt-bigquery` doesn't yet support 3.14.

### D-007: Repository security

*Accepted 2026-09-27 · TP-0*

- **Decision:**
  - **Ruleset on `main`, with no bypass actors (not even admins):**
    - no deletion and no force pushes;
    - linear history and signed commits. This applies to every commit on a PR branch, not only the squash commit GitHub creates: unsigned branch commits block the merge. Commits are signed locally with an SSH signing key registered on GitHub, and the author email is the GitHub no-reply address;
    - changes only through pull requests, with 0 approvals and squash-merge only.
  - **GitHub Actions:**
    - only GitHub-owned actions, `google-github-actions/*`, `hashicorp/*`, and `jdx/mise-action` may run;
    - every action must be pinned to a full commit SHA;
    - pull requests from fork contributors need approval before workflows run;
    - the workflow token is read-only by default and can't approve PRs.
  - **Security features:** Dependabot alerts and security updates, secret scanning with push protection, and private vulnerability reporting are on.
- **Why:** This repo's CI can change GCP through Workload Identity Federation, so its workflows, and any code they run, are a security boundary. It's based on the app repo's ruleset, plus hardening for that reason.
- **Consequences:**
  - Required status checks and the `dev`/`prod` GitHub Environments are added in TP-0 once the workflows exist.
  - A new third-party action must be added to the allowlist first.

### D-008: Mail for `huaben.app` goes through Cloudflare Email Routing

*Accepted 2026-09-27 · TP-0*

- **Decision:** `huaben.app` has no mail server. Cloudflare Email Routing forwards each individual account and `gcp-notifications@` to a mailbox that's actually read. The catch-all route is disabled. The bootstrap sets the organization's Essential Contacts to `gcp-notifications@huaben.app`.
- **Why:** Budget alerts, billing notices, and Google security notices would otherwise be lost. The organization only allows `huaben.app` addresses as contacts.

### D-009: The app's backend reaches sGTM over HTTPS with a shared secret, never with GCP credentials

*Accepted 2026-09-26 · TP-5*

- **Decision:** The API and worker run on a VM outside GCP. They send events to sGTM over HTTPS, and a custom sGTM client checks a shared-secret header.
- **Why:** The VM has no GCP identity. Using GCP APIs from it (Cloud Tasks, Pub/Sub) would need a service account key, which D-003 forbids.

### D-010: GTM configuration is exported to the repo, not managed by Terraform

*Accepted 2026-09-26 · TP-3*

- **Decision:** A CI job exports each live GTM container version as JSON into `gtm/` through the GTM API. When the live version changes, it opens a PR. Publishing still happens in the GTM UI.
- **Why:** There's no official Terraform support for GTM. The community providers have little adoption and no Google support.
- **Consequences:** GTM changes are reviewed after they're published, not before. Revisit after the MVP.

### D-011: Automated PR review reuses the app repo's DeepSeek workflow

*Accepted 2026-09-27 · TP-0*

- **Decision:** PRs are reviewed by DeepSeek via OpenRouter, reusing the app repo's `openrouter-review.yml` workflow and its script. The review is advisory and never a required check.
- **Why:** It's already built, tested, and cheap, and its security pattern is right: it checks out the base SHA and fetches the diff through the API, skips forks and Dependabot, and has minimal permissions. Switching to another reviewer later is a small change.
- **Consequences:** The workflow is added in the TP-0 CI PR. It must never have `id-token: write`. The `OPENROUTER_API_KEY` repository secret has to be created in this repo.

## Open

These are tracked in their tickets and move to **Accepted** once decided.

| Decision | Ticket | Current recommendation |
|---|---|---|
| Web GTM across environments: one container with GTM Environments, or one per environment | TP-2 | One container with Environments |
| Server GTM across environments | TP-3 | One container per environment |
| Domain mapping or global load balancer for sGTM | TP-3 | Domain mapping for the MVP |
| Minimum Cloud Run instances | TP-3 | 0 in both environments |
| Tracking DNS records | TP-3 | Cloudflare Terraform provider, DNS-only records |
| Consent management platform and Consent Mode v2 | TP-2 | Adopt Consent Mode v2 now |
| Contract format, property storage, partition column, identity lifecycle, consent-denied behaviour, retention, late-event tolerance | TP-1 | See TP-1 |
| sGTM backend client: custom client or the GA4 client | TP-1 | Open |
| Behaviour for malformed events | TP-4 | An `events_rejected` table |
| Backend delivery | TP-5 | Postgres outbox, sent by the existing worker |
| Which backend events are in the MVP | TP-5 | Only `story_generated` is required |
| Cleanup of per-PR dbt datasets | TP-6 | Open |
| Whether TP-7 and TP-8 are in the MVP | Epic | TP-7 yes; TP-8 only the failed-insert and freshness alerts |
