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
  - The contract's own fields (`event_id`, `schema_version`, `event_timestamp`, `anonymous_id`, `session_id`) travel as event parameters. `user_id` uses GA4's own field.
    - *Amended 2026-10-07*, after the tag was built and its request inspected. `session_id` is sent as the parameter `app_session_id`. Under its own name, Google's tag took the value as its own session ID, which is expected to be a number, and sent no separate parameter; that would have broken session counting in GA4 once events are forwarded there. The dataLayer key is still `session_id`: only the tag's parameter name differs, and the mapping in sGTM turns it back.
    - Google's tag also treats `event_id` as its own field, a unique ID per event used to remove duplicates. That's what ours means, so it's left as is. It travels under Google's key for it, not as an ordinary parameter.
  - A mapping step in sGTM turns the GA4-shaped event into the contract's row before it's stored. On this path it always sets `source` to `frontend`, and it refuses the names of backend events.
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

## Open

These are tracked in their tickets and move to **Accepted** once decided.

| Decision | Ticket | Current recommendation |
|---|---|---|
| Server GTM across environments | TP-3 | One container per environment |
| Domain mapping or global load balancer for sGTM | TP-3 | Domain mapping for the MVP |
| Minimum Cloud Run instances | TP-3 | 0 in both environments |
| Tracking DNS records | TP-3 | Cloudflare Terraform provider, DNS-only records |
| Behaviour for malformed events | TP-4 | An `events_rejected` table |
| Guarding the browser path against forged events and spam (D-027) | TP-4 | Validate against the contract and limit sizes; accept the rest for the MVP |
| Backend delivery | TP-5 | Postgres outbox, sent by the existing worker |
| Which backend events are in the MVP | TP-5 | Only `story_generated` is required; `login` and `quiz_submitted` are already in the contract (D-017) |
| Cleanup of per-PR dbt datasets | TP-6 | Open |
| Whether TP-7 and TP-8 are in the MVP | Epic | TP-7 yes; TP-8 only the failed-insert and freshness alerts |
