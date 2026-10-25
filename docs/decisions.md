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
  - *Amended 2026-10-24.* The first version said the job opens a PR when the live version changes. It pushes a branch instead and a person opens the PR (D-039).
  - *Amended 2026-10-11.* The export runs as a service account with no GCP roles, `gtm-export`, in the admin project. It is added by hand as a read-only user of each container. Workload Identity Federation lets any workflow run on `main` use it, which is accepted because it can only read the containers. The binding matches a run's branch, not a GitHub Environment: if the export job is ever given an Environment, its subject changes and the account needs a new binding in the bootstrap.

### D-011: Automated PR review reuses the app repo's DeepSeek workflow

*Accepted 2026-09-27 · TP-0*

- **Decision:** PRs are reviewed by DeepSeek via OpenRouter, reusing the app repo's `openrouter-review.yml` workflow and its script. The review is advisory and never a required check.
- **Why:** It's already built, tested, and cheap, and its security pattern is right: it checks out the base SHA and fetches the diff through the API, skips forks and Dependabot, and has minimal permissions. Switching to another reviewer later is a small change.
- **Consequences:** The workflow is added in the TP-0 CI PR. It must never have `id-token: write`. The `OPENROUTER_API_KEY` repository secret has to be created in this repo.

### D-012: The bootstrap's state lives in the bucket it creates

*Accepted 2026-09-27 · TP-0*

- **Decision:** The bootstrap stores its state in `huaben-tracking-platform-tfstate` under `bootstrap/`, the same bucket as the environments. The first run applies with local state and then runs `terraform init -migrate-state`.
- **Why:** A state file kept only on a laptop is easy to lose. In the bucket it's versioned, and it's in the same place as everything else.
- **Consequences:** The first run is a documented two-step procedure (`infra/bootstrap/README.md`).

### D-013: CI identities: separate plan and apply accounts, tied to GitHub Environments

*Accepted 2026-09-27 · TP-0*

- **Decision:** Each environment has two service accounts, both in the admin project.
  - **`tf-plan-<env>`** is read-only (Viewer and Security Reviewer). Any workflow run in this repository can use it, so pull requests can run plans.
  - **`tf-apply-<env>`** makes changes. Only jobs running in the matching GitHub Environment can use it; `prod` requires approval.
  - The Workload Identity provider only accepts tokens from this repository, checked by numeric repository ID and owner ID rather than by name.
  - On the state bucket, IAM conditions limit each account to its own `envs/<env>/` prefix: read-only for plan, read-write for apply.
- **Why:**
  - PR plans need credentials, but anything a PR can run shouldn't be able to change infrastructure.
  - Numeric IDs can't be taken over through a repository rename.
- **Consequences:**
  - PR plans run with `-lock=false`, because the plan accounts can't write state locks.
  - **The apply accounts hold only what current deployments need:** Viewer, Service Usage Admin, and Service Account Admin and User. Roles are added as tickets need them.
    - *Amended 2026-09-29 after a security review.* The first version also granted an unconditioned Project IAM Admin, which let an apply account give itself any role in its project, even though nothing needed it. It was removed.
    - When project-level grants are needed, Project IAM Admin comes back only **with an IAM condition** on `iam.googleapis.com/modifiedGrantsByRole`, listing the low-privilege roles it may grant.
    - Service Account Admin and User are project-wide for now, so TP-3 can create runtime service accounts and deploy as them. They're narrowed to specific accounts once those accounts exist.
    - *Amended 2026-10-11.* Service Account Admin and User were replaced by narrower grants. See D-037.
  - **PR plans run the PR's own Terraform code with the plan account's access.** That code can read the environment's state and print it into public logs, and plan-time code (data sources, `external`) can use the plan account's token. Today only the repo owner can open same-repo PRs, and anyone with write access could already merge. So:
    - **secrets never go into Terraform state**: use write-only arguments (e.g. `secret_data_wo`) and ephemeral resources;
    - if anyone else is given write access, PR plans must be gated behind an approval, e.g. a `plan` GitHub Environment with required reviewers.
  - The apply bindings match GitHub's **immutable subject** format, `repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<env>`, which this repo uses (check with `GET /repos/{repo}/actions/oidc/customization/sub`). The first version matched the older `repo:<owner>/<repo>:…` format, so no apply job could authenticate until it was fixed (2026-09-29).

### D-014: Development happens on a persistent `dev` branch

*Superseded by D-015 on 2026-09-29 · TP-0*

- **Decision:** All work is committed to `dev`, and PRs go from `dev` into `main`. `dev` isn't deleted after merging.
- **Why:** It matches the app repo's workflow.
- **Consequences:** `main` only allows squash merges, so after each merge `dev` has to be brought back in line with `main`, or the next PR would show old commits again. See the open decision below.

### D-015: Short-lived branches (GitHub Flow); environments are promoted, not branched

*Accepted 2026-09-29 · TP-0 · supersedes D-014*

- **Decision:**
  - Each change gets a short-lived branch off `main` (for example `tp-0/bootstrap`). It's squash-merged, and the branch is deleted afterwards.
  - There's no long-lived `dev` branch. Branches don't map to environments.
  - A merge to `main` applies to dev automatically. The same commit is then applied to prod after approval in the `prod` GitHub Environment.
  - To try a change in dev before merging, the `dev` GitHub Environment also accepts manually triggered deployments from any branch. `prod` only deploys from `main`.
- **Why:**
  - D-014 was meant to tie a `dev` branch to the dev environment. In this setup environments are separate Terraform roots, and every change goes through both of them from one branch.
  - Branch-per-environment is widely considered an anti-pattern for Terraform: branches drift apart, promotion becomes a merge that can conflict, and it's hard to tell what's actually running in prod.
  - Squash-merging a long-lived branch needs constant re-syncing.
  - Short-lived branches are the most common practice for infrastructure repos, and they fit the squash-only, linear-history ruleset (D-007).
- **Consequences:**
  - The commit that reached prod is exactly the one that ran in dev first.
  - Pre-merge deployments to dev can leave dev ahead of `main` until the change is merged, or reverted by re-applying `main`.

### D-016: CI workflow design

*Accepted 2026-09-29 · TP-0*

- **Decision:**
  - **`checks.yml`** runs pre-commit and a full-history gitleaks scan.
  - **`terraform.yml`** plans dev and prod on every pull request. A merge to `main` applies dev, then plans prod with the read-only account and shows the plan in the run's summary. Prod is applied only after approval. A manual run applies any branch to dev.
  - **`pr-review.yml`** runs the advisory DeepSeek review (D-011).
  - The required checks are `pre-commit`, `plan (dev)`, and `plan (prod)`, and branches must be up to date before merging.
  - Tools come from `mise.toml` through `jdx/mise-action`, and every action is pinned to a SHA.
- **GitHub Environments:**
  - `dev` accepts any branch, with no reviewers.
  - `prod` accepts only `main` and requires the repo owner's approval. Admins can't bypass it.
- **Why:** The workflows put D-013 and D-015 into practice. The up-to-date rule means the plan you reviewed was made against the latest `main`. The prod plan before the gate means you approve based on prod as it is now, not on a PR plan that may be out of date.
- **Consequences:**
  - Workflow logs are public, so plans must not print secrets.
  - Dependabot and fork PRs can't get an OIDC token, so they aren't planned. Their plan jobs run, skip every step, and report success. Dependabot changes are planned again by the apply jobs after merging, where prod still needs approval.
    - *Amended 2026-10-04.* The first version skipped the whole plan job for these PRs, on the assumption that a skipped job satisfies a required check. That holds for an ordinary job, but a matrix job skipped as a whole never expands its matrix: it reported one check named `plan (${{ matrix.env }})`, so `plan (dev)` and `plan (prod)` never arrived and the first Dependabot PRs couldn't be merged. The condition moved from the job to its steps.
    - A green plan check on a Dependabot or fork PR therefore means "not planned", and the job's notice says so.
    - Whether a PR counts as Dependabot's is now decided by its author, not by who triggered the run, so updating a Dependabot branch by hand doesn't make its code run with the plan account's access.
  - Dependabot doesn't cover `mise.toml`.

### D-017: Event naming, and the MVP's events

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - Event names are snake_case and at most 40 characters.
  - An event that really is a GA4 event uses GA4's name (`page_view`, `login`, `sign_up`). Every other event is a custom event named `object_action` in the past tense (`story_generated`, `quiz_submitted`).
  - Custom events never borrow another event's meaning: `story_generated` isn't sent as a purchase and carries no e-commerce parameters.
  - Each event has exactly one source, the frontend or the backend.
  - The MVP's events are `page_view` (frontend) and `story_generated` (backend, successful generations only).
  - The contract also defines `login` (successful logins only) and `quiz_submitted`, both from the backend. Whether the app sends them in the MVP is TP-5's decision.
  - Failures aren't events, and content isn't sent: no attempted usernames, topic text, or quiz answers.
- **Why:** Strict `object_action` would be more consistent, and GA4's names everywhere would need no mapping, but GA4 has no names for most of the app's events. The hybrid keeps GA4 compatibility for the after-MVP plan and stays honest about what each event is.
- **Consequences:**
  - Custom events don't fill GA4's built-in e-commerce reports. They'd be marked as key events instead.
  - The app has no sign-up and no "add vocabulary" action, which is why `login` and `quiz_submitted` replaced the epic's earlier candidates. The app can gain features such as sign-up later, and their events are added then.

### D-018: The contract is a YAML file, with generated outputs and one version

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - `contract/events.yaml` is the single source. `scripts/generate_contract.py` generates the BigQuery schema, the dbt source tests, and the backend's Pydantic models from it. The generated files are committed.
  - A pre-commit hook runs the generator with `--check`, so the existing `pre-commit` required check fails when the generated files are out of date.
  - The contract has one semantic version, carried by every event as `schema_version`: minor for additive changes, major for breaking ones.
    - *Amended 2026-10-06.* The first version named only minor and major. A change to wording only, which alters no field, now bumps the patch version, so that a description can be corrected without implying a new field. The first use is 1.0.1, which says that `page_location` also loses its fragment. A sender built against an earlier patch version stays valid.
  - The app installs the Pydantic models as a uv git dependency, pinned to a `contract-v<version>` tag of this repository.
- **Why:**
  - YAML with a small generator is easy to read and gives full control of the output. JSON Schema is a standard but verbose, and would still need custom code for BigQuery and dbt. Pydantic as the source would hide the contract inside Python.
  - A pinned git dependency makes a contract upgrade a reviewed version bump in the app. Copying the file in would drift silently.
- **Consequences:**
  - Property definitions use a JSON-Schema-like subset (`type`, `required`, `enum`, `minimum`, `maximum`), so a later move to JSON Schema stays possible.
  - Models are generated only for backend events, so the backend can't send a frontend event.
  - The dbt tests need dbt 1.10.5 or later, for the `arguments` property.

### D-019: Typed common fields plus a JSON `properties` column, partitioned on `server_timestamp`

*Accepted 2026-10-04 · TP-1*

- **Decision:** `analytics.events` has one typed column per common field and a `properties` JSON column for everything event-specific. It's partitioned by day on `server_timestamp`.
- **Why:**
  - Adding an event or a property never touches the table. A typed column per property, or a table per event, would change the schema with every event, and Terraform replaces a table, losing its data, on any change that isn't additive.
  - `server_timestamp` comes from a clock the platform controls. Client clocks drift, and a wrong one could put an event into a partition that has already expired.
- **Consequences:**
  - Property types aren't enforced by BigQuery. They're checked in sGTM (TP-4) and by dbt tests.
  - Common fields can only be added. The table gets `deletion_protection` (TP-4).

### D-020: Identity: identifiers, propagation, and stitching

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - **`user_id`** is the user's ID in the app's database, as a string. Usernames and email addresses are never sent.
  - **`anonymous_id`** is a UUID the frontend generates and keeps in a first-party cookie on `huaben.app`, for 13 months from first set.
  - **`session_id`** is a UUID the frontend generates, ending after 30 minutes without activity.
    - *Amended 2026-10-06.* "Activity" wasn't defined. As built, every `page_view` and every API call renews the session, including a page polling in the background. That's accepted: the app's polling is short, and changing it would mean another change to the app.
  - **Propagation:** the frontend sends `X-Anonymous-Id`, `X-Session-Id`, and `X-Tracking-Consent` headers with every API call. The API treats them as untrusted and drops anything that isn't a UUID. `user_id` always comes from the login session.
  - **Logout** clears `user_id` and nothing else. `anonymous_id` and the session carry on.
    - *Amended 2026-10-06.* The first version replaced `anonymous_id` and started a new session at logout, so that nothing after a logout linked back to the account. A typical shop keeps the browser's ID across logout, and this project follows the common setup. Replacing it also broke the link for someone logging out and back in on their own device. The shared-device case is still covered by the stitching rule, which never applies an earlier `user_id`.
  - **Stitching, applied by dbt:** an event keeps its own `user_id`. An event without one gets the first `user_id` seen after it on the same `anonymous_id`, within 30 days, and never an earlier one.
- **Why:**
  - The app's ID already exists and joins straight to app data. The column is a string, so a random analytics ID could replace it later without a schema change.
  - A cookie is shared between `huaben.app` and `www.huaben.app`; `localStorage` isn't. A cookie set by sGTM would gain nothing, because Safari caps it at 7 days when the tracking domain's IP differs from the site's.
  - Headers are explicit and work the same in every environment. Reading the cookie in the API would depend on the API staying under `huaben.app`.
  - The "never an earlier one" rule stops the next person on a shared device inheriting the previous one's history, whether the previous person logged out or their session just expired.
- **Consequences:**
  - The app must add the three headers to its CORS allowed headers, return the user's ID from `/auth/me`, and store `user_id` and the identity context on each generation request (TP-2, TP-5).
  - Safari limits script-set cookies to 7 days, so a logged-out Safari visitor gets a new `anonymous_id` after a week away. Login re-links them.
  - User IDs are sequential database keys. They must be replaced or hashed before being forwarded to a third party.
  - One `anonymous_id` can belong to several users over time, on a shared device. Events between a logout and the next login are stitched to whoever logs in next.
  - The stitching rules live in dbt, so they can change without losing data.

### D-021: Consent

*Accepted 2026-10-04 · TP-1 · not legally reviewed*

- **Decision:**
  - The signal is Consent Mode v2's `analytics_storage`. Every event records the consent state, and unknown counts as denied.
  - An event produced later by the worker records the consent state from when the request was made.
  - An event with no identifiers at all is valid, e.g. a generation made with the shared API key.
  - **Frontend, consent denied:** no identifiers are created and no events are sent.
  - **Backend, consent denied:** events are still sent, with `user_id` but without `anonymous_id` or `session_id`.
  - Nothing is forwarded to a third party unless the event's consent state is `granted`.
- **Why:**
  - Events without identifiers ("cookieless pings") probably still need consent under the EDPB's 2023 reading of ePrivacy.
  - A backend event records something the user did in the app, which the app's database already holds, like an order in a shop. Keeping it in the platform's own warehouse rests on legitimate interest. Dropping these events would make the counts wrong.
- **Consequences:**
  - The app needs a privacy notice that covers this.
  - Withdrawing consent deletes both cookies and stops the identity headers.
  - This should be checked by someone qualified before the app is opened to the public.

### D-022: Retention

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - Raw `analytics.events`: 14 months, by partition expiration.
  - Event-level dbt models: 14 months, so they can't outlive the raw data.
  - Aggregates with no identifiers: no limit.
  - `events_rejected`: 30 days.
  - Cloud Logging: 30 days.
  - Outbox rows already sent, in the app: 7 days.
- **Why:** 14 months allows a year-over-year comparison of any month and matches GA4's standard maximum. Storage cost is negligible at this volume, so privacy decides it. Rejected events hold raw payloads that could contain anything, so they're kept only long enough to debug.
- **Consequences:** Erasure on request is separate from expiry: a user's rows are deleted by `user_id` from the raw and derived tables. TP-7 documents and tests the procedure.

### D-023: Late-event tolerance: a 3-day lookback, with the outbox giving up after 48 hours

*Accepted 2026-10-04 · TP-1*

- **Decision:** dbt removes duplicates by `event_id`, looking back 3 days on `server_timestamp`. The outbox retries an event for up to 48 hours and then marks it dead. An event is never rejected for being late.
- **Why:** Browser events aren't retried, so duplicates only come from an outbox retry after an attempt that had in fact succeeded. The gap between duplicates is therefore bounded by how long the outbox retries, and the lookback covers that with a day's margin.
- **Consequences:** Resending a dead row by hand after more than 3 days needs a full refresh of `stg_events`.

### D-024: The backend's sGTM client, and its secret

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - A custom sGTM client (D-009) accepts one event per `POST`, in exactly the contract's shape. It answers 401 for a wrong secret and 400 for a body that doesn't match, and it sets `server_timestamp`.
  - The secret is a plain header (`X-Tracking-Secret`) of 32 random bytes, one per environment.
  - **The server container stores only the SHA-256 hash of the secret.** The client hashes the incoming header and compares. The secret itself lives only in the app's runtime secrets.
- **Why:**
  - The GA4 client with Measurement Protocol payloads would tie the payload to GA4's format and limits, and it doesn't check a secret.
  - The server container is exported to this public repository (D-010), so a secret stored in it would leak. A hash of a 32-byte random secret can't be reversed. A hash of a guessable one could be found by brute force, so the secret must come from a cryptographically secure random generator and never be chosen by a person.
  - Reading the secret from Secret Manager at runtime would also keep it out of the container, but needs an IAM grant, an API call on each cold start, and more template code.
  - TLS already protects the header in transit, so signing each request would add complexity without a matching benefit.
- **Consequences:**
  - This replaces the epic's earlier plan to keep the shared secret in Secret Manager. Nothing about it is stored in GCP.
  - Rotating the secret is a GTM publish plus an update on the Droplet. The client accepts two hashes during a rotation, to avoid downtime.

### D-025: dbt Core, not Dataform

*Accepted 2026-10-04 · TP-6*

- **Decision:** The models are built with dbt Core, run by GitHub Actions.
- **Why:** Dataform is free, BigQuery-native, and needs no runner. dbt is the more widely used tool, works with any warehouse, and has the larger ecosystem, and this project is partly a way to learn a standard stack. Its runner is a GitHub Actions cron job on a pattern the repo already has.
- **Consequences:** The contract generates dbt test YAML (D-018).

### D-026: `event_timestamp` is the business time, defined per event

*Accepted 2026-10-04 · TP-1*

- **Decision:**
  - The source's timestamp is called `event_timestamp`, not `client_timestamp` as first planned.
  - It's the moment the thing the event describes became true, and every event in the contract says which moment that is (`event_time`). For `story_generated` it's when the generation completed, the same value as the request's `completed_at` in the app.
  - It's set once, when the event is created. Retries and delayed delivery never change it. The Pydantic models have no default for it, so the caller has to pass it.
  - `server_timestamp` is separate: when sGTM received the event.
- **Why:**
  - "When the event happened at its source" was ambiguous for an event produced by the worker: it could mean request time, completion time, or the time the outbox row was written.
  - `client_timestamp` reads as "the browser's clock", which is wrong for backend events.
  - A default of "now" would silently become delivery time if the model were built when the event is sent.
- **Consequences:**
  - A frontend event's `event_timestamp` comes from the browser's clock and can be wrong. `source` says which kind of clock produced it, and the table is partitioned on `server_timestamp` (D-019).
  - The gap between the two timestamps is the delivery delay.
  - The generator refuses an event without an `event_time`.

### D-027: Browser events reach sGTM through the GA4 tag and client, in basic consent mode

*Accepted 2026-10-04 · TP-2*

- **Decision:**
  - Web GTM sends browser events with the GA4 tag, pointed at the tracking domain. In sGTM the built-in GA4 client claims them.
  - The contract's own fields travel as event parameters: `schema_version`, `event_timestamp`, `anonymous_id`, and `session_id` under the name `app_session_id`. `event_id` and `user_id` use Google's own fields.
    - *Amended 2026-10-07*, after the tag was built and its request inspected. This first listed `event_id` and `session_id` as ordinary event parameters under their own names. `session_id` is now sent as the parameter `app_session_id`. Under its own name, Google's tag took the value as its own session ID, which is expected to be a number, and sent no separate parameter; that would have broken session counting in GA4 once events are forwarded there. The dataLayer key is still `session_id`: only the tag's parameter name differs, and the mapping in sGTM turns it back.
    - Google's tag also treats `event_id` as its own field, a unique ID per event used to remove duplicates. That's what ours means, so it's left as is. It travels under Google's key for it, not as an ordinary parameter.
  - A mapping step in sGTM turns the GA4-shaped event into the contract's row before it's stored. On this path it always sets `source` to `frontend`, and it refuses the names of backend events.
  - *Amended 2026-10-25*, after the tag first ran in the dev container. This said the mapping builds `consent` from the request's Consent Mode state. Server containers have no consent API, so the tag reads the `x-ga-gcs` value the GA4 client puts in the event data (from the request's `gcs` parameter: `G1`, then `ad_storage` and `analytics_storage` as 1 or 0). A missing or malformed value counts as denied, and the browser path rejects an event whose `analytics_storage` isn't granted. Only `analytics_storage` is recorded; the other signals stay null.
  - The custom client (D-024) stays backend-only and keeps requiring its secret.
  - Consent Mode runs in **basic mode**: the tag is blocked until `analytics_storage` is granted, so nothing is sent when consent is denied (D-021).
- **Why:**
  - It's the standard way a browser reaches sGTM, and the contract's browser events already use GA4's names (D-017). Forwarding to GA4 after the MVP needs no second mapping.
  - Google's tag handles batching, sending on page unload, and Consent Mode. GTM Preview shows the event on both sides.
  - Sending the contract's JSON to the custom client would give one shape and one client. But a browser can't hold the secret, so the client would need a second path without one, plus CORS handling, and web GTM would be reduced to a single Custom HTML tag with hand-written transport code.
  - Advanced mode's cookieless pings only pay off as modelling inside GA4 and Google Ads. The MVP forwards nothing to either, the app's traffic is far below GA4's modelling thresholds, and D-021 already rules the pings out.
- **Consequences:**
  - Two shapes arrive in sGTM: GA4's from the browser, and the contract's from the backend. The mapping, and its validation against the contract, is TP-4's work.
  - The tag needs a GA4 measurement ID, so a GA4 property exists even though nothing is forwarded to it in the MVP. A measurement ID isn't a secret.
  - Until the tracking domain exists (TP-3), a live tag would send straight to Google. TP-2 verifies the dataLayer and variables in Preview; the tag goes live only once it points at sGTM.
  - Google's tag sets its own `_ga` cookies once consent is granted. The identity is still D-020's: `client_id` isn't stored.
  - The GA4 client's path takes no secret, like any browser collection endpoint, so anyone can post to it. This is why the mapping fixes `source` and refuses backend event names.
  - That only stops a browser event passing as a backend one. It doesn't stop forged frontend events, made-up identifiers, or bulk spam. How far to guard against those is TP-4's decision.
  - Page views from users who decline are missing from the warehouse. Backend events aren't affected (D-021).
  - Revisit basic mode when GA4 or Google Ads forwarding is added. Changing it is a reversal, so it takes a new entry that supersedes both this one and D-021 and restates what's kept from each.

### D-028: One web GTM container, with GTM Environments

*Accepted 2026-10-04 · TP-2*

- **Decision:**
  - There's one web container. The local dev server loads the snippet of a `dev` GTM Environment, and GitHub Pages loads Live.
  - A version is published to `dev` first, verified, and then the same version is published to Live.
  - Values that differ by environment, such as the sGTM URL and the measurement ID, come from lookup variables on the hostname (`localhost` → dev).
- **Why:**
  - The version that was tested is the version that's promoted. A container per environment would be promoted by export and import, which is manual and can overwrite prod's values if the merge options are wrong.
  - The web container is small, and dev is only ever `localhost`, so full isolation buys little. One container also means one version history and one export in `gtm/`.
  - Using Preview mode alone, without Environments, would leave no step between a draft and Live.
- **Consequences:**
  - Dev and prod share a container, so a version can be published to Live by mistake. The export job (D-010) turns every Live change into a PR diff.
  - The frontend build chooses the snippet: the environment's snippet carries `gtm_auth` and `gtm_preview` parameters.
    - *Amended 2026-10-06.* This first said neither parameter is a secret. `gtm_preview` isn't, but `gtm_auth` lets anyone load the `dev` environment's unpublished tags, and it only ever appears on `localhost`. It stays out of both repositories, in the frontend's local environment file. If it leaks, GTM's "Reset Link" on the environment replaces it.
  - Web and server GTM are promoted differently if the server containers are split per environment (TP-3's decision).

### D-029: Cookiebot is the consent management platform, loaded through GTM

*Accepted 2026-10-04 · TP-2*

- **Decision:**
  - The consent banner is Cookiebot, on its free plan.
  - It's loaded by Cookiebot's tag template in the web container, on the Consent Initialization trigger, so it runs before every other tag.
  - The template sets the Consent Mode v2 defaults and updates (D-021). Every other tag is gated by its consent settings in GTM.
  - The frontend reads the consent state from Cookiebot, behind one small module. That module decides whether the identity cookies exist and what `X-Tracking-Consent` says (D-020).
  - The module follows Cookiebot's events, not a single read at startup. Until Cookiebot has reported, consent is unknown and counts as denied. When it reports or changes to granted, the module creates the identifiers, starts the headers, and sends the `page_view` for the page being shown. When it changes to denied, it deletes the cookies and stops the headers.
    - *Amended 2026-10-06*, after the frontend was built. Three details this didn't state:
      - Granted means Cookiebot's Statistics category alone, the one its tag maps to `analytics_storage`.
      - The module tells "denied" from "not known yet". Both read as denied to the rest of the code, but the cookies are deleted only once Cookiebot has reported a refusal. Every page load starts as unknown, so deleting on unknown would remove a returning visitor's `anonymous_id`.
      - It listens for Cookiebot's `CookiebotOnConsentReady` event, and also reads the state once when first used, because the event can fire before the listener is attached.
  - `localhost` and `localhost:3000` are added as domain aliases, so the banner runs on the local dev server.
- **Why:**
  - Cookiebot through its GTM template is the setup most likely to be met in an e-commerce shop, which is what this project is practice for. Consent is configured in one place, GTM, and a change to it is a publish, promoted through the same Environments as the tags (D-028).
  - Cookiebot sets Consent Mode by itself and keeps a log of consents.
  - The self-hosted vanilla-cookieconsent is the better technical fit for this app: its code could import it directly, nothing would leave `huaben.app`, and it has no limits. It was passed over because it's less common in that work and keeps no consent log. CookieYes offers much the same as Cookiebot with less presence.
  - Loading the script in the frontend's root layout, as Cookiebot's guide for Next.js describes, would move the consent setup out of GTM and into the app's code.
- **Consequences:**
  - Cookiebot's guide for Next.js says the banner can flash and disappear when its script loads after the page hydrates, which a script loaded by GTM does. TP-2 tests for this. If it happens, the script moves to the root layout, recorded as an amendment here.
    - *Tested 2026-10-06.* In the app on `localhost`, the banner appears and stays. Cookiebot stays in GTM.
  - The template comes from GTM's Community Template Gallery, so its permissions are reviewed before it's added.
  - A third party's script loads on every page, and Cookiebot sets its own cookie. The privacy notice must name it.
  - If the script is blocked, e.g. by an ad blocker, there's no banner and consent stays unknown, which counts as denied (D-021).
  - The free plan covers one domain and 50 subpages. Its cookie scanner only sees the login page, so the cookie declaration needs checking by hand.
  - TP-2 confirms that the free plan allows the `localhost` alias. If it doesn't, the fallback is vanilla-cookieconsent, and only the consent module and the way the banner loads would change.
    - *Confirmed 2026-10-06.* The free plan accepts `localhost` and `localhost:3000` as aliases.

### D-030: Ticket text lives in the GitHub issues, not in the repository

*Accepted 2026-10-08 · Epic*

- **Decision:**
  - Each ticket's text is kept in its GitHub issue and nowhere else. The issue is edited directly.
  - A ticket's progress is recorded the same way, by editing the issue's text: what was decided, what's done, and what's left. It isn't kept in comments, so the issue always reads as the ticket's current state.
  - The epic's issue holds no overview of its own. It points to `docs/epic-mvp.md` and lists its tickets as sub-issues.
  - `docs/epic-mvp.md` keeps only what isn't a ticket: the hosting context, the environments, the MVP boundary, and a list of the tickets with links.
  - Decisions stay in this file, and the tracking specification stays in `docs/tracking-spec.md`. A ticket refers to them; it doesn't repeat them.
- **Why:**
  - Until now the epic document held every ticket's text and each issue was kept matching it, so every ticket edit was made twice: once through a pull request, once on the issue. During TP-2 the two drifted several times, and the board, which is where the work is followed, ran ahead of `main`.
  - Keeping the text in the repository gave ticket edits a review and one file to read. Neither was worth the double work for a one-person project.
- **Consequences:**
  - Ticket edits aren't reviewed in a pull request. GitHub keeps each issue's edit history.
  - This repository is public and so are its issues, so the rules for what may be written apply to issue text as before.
  - Anything that has to outlive a ticket goes in a decision or in the specification, not only in the issue. A closed issue is history.
  - The ticket sections removed from `docs/epic-mvp.md` matched their issues when they were removed, so no text was lost.

### D-031: One server GTM container per environment

*Accepted 2026-10-09 · TP-3*

- **Decision:** Dev and prod each have their own server container, with their own tagging and preview services on Cloud Run. Each service is deployed with its container's config string. A version is promoted by exporting the dev container's JSON, importing it into the prod container with the merge option, and publishing.
- **Why:**
  - A tagging server is deployed with one container's config, so separate containers are the usual way to keep environments apart.
  - Each container sends to its own BigQuery project. With one shared container, a hostname lookup would pick the destination, and a wrong lookup would write dev events into prod's table.
  - The server container is empty today, so splitting now costs nothing. Splitting later would mean rebuilding the clients, the mapping, and the BigQuery tag (TP-4, TP-5).
- **Consequences:**
  - Promotion is manual, and a wrong merge option can overwrite prod's values. The export job (D-010) turns every live change into a PR diff, so it's visible after the fact.
  - The web container stays single (D-028). Its lookup variable on the hostname picks the sGTM URL: `localhost` → `tracking.dev.huaben.app`, GitHub Pages → `tracking.huaben.app`.
  - The export job covers three containers: the web container and both server containers.
  - Whether a server container can use GTM Environments the way the web container does (D-028) wasn't established. It doesn't change this decision.

### D-032: Cloud Run domain mapping for the tracking domains, in both environments

*Accepted 2026-10-09 · TP-3*

- **Decision:** `tracking.dev.huaben.app` and `tracking.huaben.app` are Cloud Run domain mappings, with DNS-only records in Cloudflare. Prod moves to a global external Application Load Balancer when real traffic arrives, or if monitoring shows latency.
- **Why:**
  - A load balancer costs about $18 per month per environment, a large share of the under-$10 target for both projects together (epic).
  - Domain mappings are free and available in europe-west1.
  - Tracking requests are sent in the background and don't block the UI.
- **Consequences:**
  - Domain mappings are in preview. Google calls them "not production-ready" because of latency. They can't disable TLS 1.0/1.1, can't use custom certificates, and have no Cloud Armor or CDN. A certificate can take up to 24 hours.
  - **The identity that creates a mapping must be a verified owner of `huaben.app` in Search Console.** That's the CI apply account for each environment. Verifying the domain (a TXT record in Cloudflare) and adding both `tf-apply-*` accounts as owners is a one-time manual step, done by a person.
    - Ownership covers the whole domain, which is broader than creating one mapping. It is the grant Cloud Run's domain mapping requires, so only the two apply accounts get it, and no plan account or other identity does.
  - Records pointing at Google must not be proxied by Cloudflare, or Google can't issue the certificate. If CAA records are ever added, they must allow `pki.goog` and `letsencrypt.org`.

### D-033: Tagging service: minimum 0 instances, CPU only during requests

*Accepted 2026-10-09 · TP-3*

- **Decision:** In both environments, the tagging service has `min-instances = 0` and Cloud Run's default CPU allocation, which is throttled between requests. The preview service is limited to one instance, as Google requires.
- **Why:** Google's own setup uses at least 2 instances with CPU always allocated, about $45 per month per server. That is more than the app's whole hosting budget (epic).
- **Consequences:**
  - Cold starts can delay or lose browser events, which aren't retried. Backend events are retried by the outbox for up to 48 hours (D-023).
  - **A risk to test in dev before prod:** the spec has sGTM answer `200` before the BigQuery insert finishes. With throttled CPU, work after the response may stall. If backend events don't reach BigQuery reliably, switch to CPU always allocated, keeping `min-instances = 0`, and amend this entry.
  - Revisit with real traffic.

### D-034: The container config is a secret whose value is added by hand

*Accepted 2026-10-09 · TP-3*

- **Decision:** Terraform creates each environment's Secret Manager secret and the runtime service account's access to it, but no secret version. A person adds the container config string with `gcloud secrets versions add`. Cloud Run reads it from the secret.
- **Why:**
  - The config string holds an auth key, and plans run in public logs on the PR's own code (D-013).
  - A write-only argument keeps the value out of state, but the value would then pass through a GitHub Environment secret and CI. Adding it by hand keeps it out of both.
- **Consequences:**
  - A fresh environment doesn't start until someone adds the value. The first deploy of the service therefore comes after that step.
    - *Amended 2026-10-24.* The sGTM module has a `deploy_services` flag, off in a fresh environment. The first apply then creates the secret, the runtime accounts, and the log exclusion, but no Cloud Run service, because a service can't start without a secret version. After a person adds the value, a pull request turns the flag on. The steps are in `infra/modules/sgtm/README.md`.
  - Instances read the secret when they start, so rotating it needs a new revision.
  - This is the one secret Terraform doesn't fully manage. TP-3 documents the step in the README.

### D-035: Tracking DNS records are added by hand in Cloudflare

*Accepted 2026-10-11 · TP-3*

- **Decision:**
  - The records for `tracking.dev.huaben.app` and `tracking.huaben.app` are added by a person in Cloudflare, once each. They are the records Cloud Run shows for the domain mapping (D-032), read with `gcloud beta run domain-mappings describe`, and they are DNS-only, never proxied.
  - The Search Console verification record (D-032) is also added by hand.
  - Terraform creates the domain mappings and nothing in Cloudflare. No Cloudflare provider and no Cloudflare token are used.
- **Why:**
  - A Cloudflare API token is scoped to a zone, not to a record name. A CI token able to edit `huaben.app` could also edit the API, the mail routing (D-008), and the GitHub Pages records, so a leak would break the whole app, not just tracking.
  - The records are two static CNAMEs that don't change after the first setup, so code would add little.
  - Managing them in Terraform would add the project's first third-party provider, up to three tokens, and a way for PR plans to read Cloudflare without a secret that a PR could print.
  - Managing a whole zone in code is the common setup for a team. A single person with a handful of static records often uses the console.
- **Consequences:**
  - The records aren't in code or reviewed in a PR, and drift isn't detected.
    - TP-3 puts the exact records and how to read them in the README.
    - TP-3's verification checks them with `dig`.
    - A wrong or proxied record shows up as a certificate that never issues.
  - After the mapping is created the certificate waits for the record, then takes about 15 minutes, or up to 24 hours.
  - If a team or a second person starts changing the zone, revisit: a provider with a token limited to the tracking records, if Cloudflare supports that by then.

### D-036: The tagging service is public through `invoker_iam_disabled`; the preview service is private if Preview mode allows it

*Accepted 2026-10-11 · TP-3*

- **Decision:**
  - The tagging service sets `invoker_iam_disabled = true` on `google_cloud_run_v2_service`. The organization policy stays as it is (D-003).
  - The preview service stays private, with the invoker check on, if GTM's Preview mode works that way. Otherwise it also disables the check. Which one is settled by testing in dev, and this entry is amended with the result.
    - *Amended 2026-10-24.* Tested in dev: opening Preview on the server container failed with `403 Forbidden` on `/gtm/debug`, Cloud Run's refusal of an anonymous call to a private service. GTM's debugger runs in the browser and can't send an IAM token, so the preview service is public in dev and prod, where it was meant to stay private (`preview_invoker_iam_disabled = true`, now the module's default). The debugger is meant to need a Preview session's token, which GTM generates for the container, but that hasn't been tested for what an anonymous caller can see. Anyone with the service's address can also call it, which costs money: the cost is bounded by its single instance. To check after the apply: call the service without a token and record what it returns.
    - *Checked 2026-10-24.* Called without a token, the preview service answers `/healthy` with `200` and everything else, including `/gtm/debug`, with `404`, in dev and prod. Preview mode on the dev server container then worked: a `page_view` from `localhost` showed in the debugger. That the debugger needs a session token is still the expectation and not something these requests prove.
- **Why:**
  - Browser tracking requests carry no Google credentials, so a service that receives them has to accept anonymous requests. Domain-restricted sharing forbids `allUsers`, and weakening the policy would open it for every service in the organization.
  - A private tagging service behind a load balancer and IAP would cost about $18 per environment per month (D-032), and browsers still couldn't send the IAM token.
  - The tagging service's protection is therefore at the application level, and what is settled is two things: the mapping that fixes `source` and refuses backend event names (accepted in D-027), and the secret the backend client requires (D-024). Guarding the browser path further, against forged frontend events and spam, is not settled. It is TP-4's open decision.
  - The preview service is only used by GTM's debug interface and the tagging server. Google's own setup deploys it unauthenticated, but whether it can be private wasn't verified. An IAM check would block the browser's calls to it, since they can't carry a token.
- **Consequences:**
  - Anyone can post to the tagging service. Forged frontend events and spam are TP-4's open decision (D-027).
  - If the preview service has to be public, it's reachable by anyone who knows its URL. The URL isn't published, but it isn't a secret either.
  - Terraform grants no `allUsers` and no invoker role for either service.

### D-037: The apply accounts create service accounts and act as the sGTM runtime accounts only

*Accepted 2026-10-11 · TP-3 · amends D-013*

- **Decision:**
  - The apply accounts no longer hold Service Account Admin or User.
  - A custom role lets them create, update, delete, get, and list service accounts. It has no `setIamPolicy`, so an apply account can't let itself act as another service account.
  - Service Account User is bound on each sGTM runtime account by name, and not project-wide.
    - *Amended 2026-10-24.* This first said an IAM condition limited it to accounts whose name starts with `sgtm-`. The first local apply rejected that condition, because IAM conditions have `startsWith` and `endsWith` but no `contains`. It was rewritten with `startsWith` over two forms of the account's resource name (`projects/-/…` and `projects/<project id>/…`), because Google's documentation doesn't say which form conditions use, and that was applied. The first dev deploy as a runtime account was then denied `iam.serviceAccounts.actAs`, so neither form matched. The form isn't known. A numeric unique ID is a likely candidate, which no prefix could match. This is the first fallback this entry named: a binding per account, listed in the bootstrap and applied locally.
  - For the rest of TP-3 they also hold Cloud Run Admin, a custom role for secrets (no direct `versions.access` or `versions.add`), and a custom role for log exclusions only.
- **Why:**
  - Service Account Admin includes `iam.serviceAccounts.setIamPolicy`, which would let an apply account act as any service account in its project (D-013).
  - Binding by name doesn't depend on how IAM writes a service account's name in a condition, which isn't documented and turned out not to match a prefix. The list of accounts is explicit, so a new runtime identity is a reviewed change to the bootstrap.
  - Cloud Run Admin. Its `setIamPolicy` permissions cover Cloud Run services, jobs, instances, and worker pools, and nothing else.
    - *Amended 2026-10-24.* This first chose Cloud Run Developer, on the reasoning that a service with `invoker_iam_disabled` (D-036) doesn't need `run.services.setIamPolicy`. That was wrong: the API refuses to set `invoker_iam_disabled` without it, and the first dev deploy of the tagging service failed with `Changes to invoker_iam_disabled require run.services.setIamPolicy permissions`. The permission can't be left out while D-036 holds. A custom role with only the service permissions would be narrower than Admin, but any permission missing from it is found by a failed CI apply, so Admin was chosen.
  - The secrets role has no `versions.access` or `versions.add`, so Terraform never handles the container config's value (D-034).
  - `logging.configWriter` also lets an account create log sinks to other destinations, which an exclusion doesn't need.
- **Consequences:**
  - **Checked 2026-10-11:** none of the roles the apply accounts keep includes `iam.serviceAccounts.actAs`: not Viewer, Service Usage Admin, Cloud Run Admin (checked again 2026-10-24 when it replaced Developer), and not the custom roles, which list their permissions. The per-account bindings are therefore the only way they can act as a service account. To repeat the check: `gcloud iam roles describe <role> --format='value(includedPermissions)' | tr ';' '\n' | grep -c 'iam.serviceAccounts.actAs'` prints 0 for each of the three predefined roles. For Cloud Run Admin it printed 0 on 2026-10-24, before it was granted.
  - Binding by name has a cost: the environment's apply creates the runtime accounts, and the bootstrap can only bind an account that exists. For a new environment the order is the environment's first apply with `deploy_services = false`, then a bootstrap change that adds its accounts to `sgtm_runtime_accounts` (applied locally), then the pull request that turns the services on. A new or renamed runtime account needs the same bootstrap change before a service can run as it.
  - **The secrets role doesn't stop an apply account reading the container config.** It can set a secret's IAM policy, which is how the runtime account gets access, so it could grant itself access. It can also deploy a service as an `sgtm-*` account with the secret mounted. D-034 keeps the value out of Terraform, state, and logs. It doesn't make it unreachable from CI. As far as we know the string only lets a tagging server fetch the container's configuration from GTM, and D-010 publishes that configuration in this repository.
  - **Domain mappings:** neither Cloud Run Developer nor Admin lists a domain-mapping permission (Admin is the role held), so it's unknown which role covers `google_cloud_run_domain_mapping` (D-032). The first dev apply that creates a mapping is the test, and this entry is amended with the result.
    - *Amended 2026-10-24.* The dev mapping was created by the apply account with Cloud Run Admin and no other role. Cloud Run's IAM has no domain-mapping permission at all (`run.routes` has only get, invoke, and list). What it checks is that the caller is a verified owner of the domain in Search Console, which the apply accounts are. No change to the roles was needed.
  - Roles for the runtime accounts themselves, such as BigQuery access, come in TP-4. Project IAM Admin with a `modifiedGrantsByRole` condition (D-013) is added then if it's needed.

### D-038: Cloud Run request logs are excluded

*Accepted 2026-10-11 · TP-3*

- **Decision:** A log exclusion drops Cloud Run's request logs (`run.googleapis.com/requests`) for the sGTM services, in both environments. Application logs are kept, for 30 days (D-022).
- **Why:** The request log records the client IP, the user agent, and the full URL, which is personal data the platform doesn't need. An exclusion means they are never stored. A dedicated bucket with short retention would still hold them for its retention period, and would need a bucket, a sink, and an exclusion.
- **Consequences:**
  - Request counts, response codes, and latency come from Cloud Run's built-in metrics, which don't depend on the logs.
  - Failed inserts are logged by the application, which TP-8's alert uses.
  - Debugging an individual request is harder. Lifting the exclusion for a while is a change through a pull request.

### D-039: The GTM export pushes a branch, and a person opens the pull request

*Accepted 2026-10-24 · TP-3 · amends D-010*

- **Decision:**
  - The `GTM export` workflow runs daily and on demand, only on `main`. It logs in as `gtm-export` through Workload Identity Federation, with the read-only Tag Manager scope.
  - `scripts/export_gtm.py` writes the live version of every container the account can see to `gtm/<public ID>.json`. It removes the account's numeric ID, resource paths, URLs, and fingerprints.
  - When the files differ from `main`, the workflow pushes a branch `gtm-export/<hash of the content>`, with its commits made through the GitHub API, and links to the pull request form in the run summary. A person opens the pull request.
  - `id-token: write` may now be held by the Terraform workflows and this one. CLAUDE.md says so, and also that it is never given to a workflow that runs code from a pull request or handles other secrets.
- **Why:**
  - A pull request opened with the workflow's own token doesn't start other workflows, so the required checks (`pre-commit`, `plan (dev)`, `plan (prod)`) would never run and the pull request could never merge. Fixing that takes a GitHub App or a personal token, and a new action in the allowlist. Neither was worth it for a daily diff that one person reads.
  - Commits made with `git` in the workflow would be unsigned, and the ruleset requires every commit of a pull request to be signed (D-007). Commits made through the API are signed by GitHub.
  - Naming the branch by content makes a repeat run a no-op, and it never deletes or resets a branch that has a pull request open.
  - The account ID is left out because this repository is public.
- **Consequences:**
  - A person has to open the pull request.
    - *Amended 2026-10-24.* At first only the run's summary and a notice told them. The workflow now also opens one issue per pushed branch, mentioning the owner, with the diff and pull request links, so GitHub notifies them. The issues carry a `gtm-export` label and are found by label and title, and only open ones count, so a change seen before (a rollback in GTM, say) gets a new issue. Closing the issue without merging the pull request brings a new one the next day. The job gains `issues: write` for that. A failed run still shows red in Actions.
  - Merged or abandoned `gtm-export/*` branches pile up until someone deletes them.
  - Unpublished workspace changes aren't exported, only the live version. A deleted container keeps its file until it is removed by hand.
  - The identity binding only trusts runs on `main` (D-037), so the workflow can't be tried from a branch. The first real run is a manual run on `main` after the merge.
  - A GitHub App could automate the pull request later. That is a new decision, and it needs the app's action added to the allowlist first.

### D-040: Malformed events are written to an `events_rejected` table

*Accepted 2026-10-24 · TP-4*

- **Decision:** sGTM validates each event against the contract before inserting it. An event that fails is written to `analytics.events_rejected` with its raw payload and the reason, instead of to `analytics.events`. The table is partitioned by day and expires after 30 days (D-022).
- **Why:** One bad row can fail a whole insert. Dropping it, or inserting with `skipInvalidRows`, would lose events without a trace. A rejects table keeps them for debugging and shows how often a sender gets the contract wrong.
- **Consequences:**
  - The raw payload can hold anything a sender posts, so the table is kept for 30 days only, and the payload is truncated.
  - On the browser path the payload keeps only the contract's own keys. Google's tag also sends the IP address, client ID, user agent, region and more, none of which is stored anywhere.
  - A failed insert into either table is logged with the `event_id` and the error, which TP-8's alert uses.

### D-041: The browser path is guarded by validation, size limits, and an `Origin` check

*Accepted 2026-10-24 · TP-4 · follows D-027*

- **Decision:** On the GA4 client's path, which takes no secret, sGTM:
  - validates each event against the contract: a known event name, UUID identifiers, and property types;
  - limits string lengths and request size;
  - checks the request's `Origin` against the site's hostnames.

  Rate limiting is not added for the MVP.
- **Why:** Validation and size limits keep malformed and oversized events out of the warehouse. The `Origin` check stops casual misuse, though it is trivially forged outside a browser. Rate limiting on Cloud Run needs Cloud Armor and so the load balancer (D-032), which the MVP doesn't have.
- **Consequences:**
  - Forged but well-formed `page_view` events, made-up identifiers, and bulk spam from outside a browser are not stopped.
  - Bulk spam is bounded by the tagging service's instance limit (D-033) and shows up in the budget alerts.
  - A request with an `Origin` outside the site's hostnames is logged and not stored. That keeps casual misuse, such as another site's page posting events, out of `events_rejected` (D-040). It does not stop a request made outside a browser, which can send an allowed `Origin`.
  - A browser event whose `analytics_storage` isn't `granted` is rejected with the reason `consent_not_granted`. The spec says page views from visitors who decline are absent, not stored as denied.
  - Revisit if the load balancer is added after the MVP.

### D-042: BigQuery access: dataset-level `dataEditor` for sGTM, and a custom role for the apply accounts

*Accepted 2026-10-25 · TP-4 · follows D-013 and D-037*

- **Decision:**
  - The tagging service account gets `roles/bigquery.dataEditor` on the `analytics` dataset, and nothing on the project. The preview account gets nothing.
  - The apply accounts get a custom role, `tfApplyBigQuery`, that manages datasets and tables and sets IAM on datasets. It has no permission to run jobs or queries.
- **Why:**
  - Writing rows with the streaming API needs `bigquery.tables.updateData`, which `dataEditor` includes. A narrower custom role for the runtime account would have to be created in the bootstrap, for one dataset, so it wasn't thought worth it.
  - Dataset-level grants need no Project IAM Admin, so the apply accounts stay without it (D-013).
- **Consequences:**
  - `dataEditor` also carries `bigquery.tables.update` and `delete`. A compromised sGTM container could alter or drop `analytics.events`. Table deletion protection stops Terraform from doing it, but not that account. Revisit with a custom role if the container's exposure grows.
  - `bigquery.datasets.setIamPolicy` applies to every dataset in the project, not only the ones the module manages. An apply account could give itself read access to any dataset there, such as the dbt datasets TP-6 adds, without being able to run a job. This is accepted for the same reason as in D-037: the account that creates a resource can already reach it, and the projects hold only this platform's data.

## Open

These are tracked in their tickets and move to **Accepted** once decided.

| Decision | Ticket | Current recommendation |
|---|---|---|
| Backend delivery | TP-5 | Postgres outbox, sent by the existing worker |
| Which backend events are in the MVP | TP-5 | Only `story_generated` is required; `login` and `quiz_submitted` are already in the contract (D-017) |
| Cleanup of per-PR dbt datasets | TP-6 | Open |
| Whether TP-7 and TP-8 are in the MVP | Epic | TP-7 yes; TP-8 only the failed-insert and freshness alerts |
