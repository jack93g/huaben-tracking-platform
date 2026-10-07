# Epic: Server-side tracking platform (MVP)

Decisions marked **Open** must be resolved and recorded in `docs/decisions.md` before the phase that depends on them starts.

## Hosting context

The app being tracked is not on GCP:
- **API, durable worker, and Postgres:** Docker Compose on a single small VM.
- **Frontend:** GitHub Pages.
- **DNS:** `huaben.app` is served by Cloudflare.
- **Budget:** $10–25/month for the app's hosting (see the app repo's deployment decisions).

What this means for the platform:
- **Cost.** GCP should stay close to the free tiers: Cloud Run with `min-instances = 0`, domain mapping instead of a load balancer, and BigQuery within its free storage and query allowances. Target under $10/month for both projects together, and set budget alerts to match.
- **Backend credentials.** The VM has no GCP identity. Calling GCP APIs from it (Cloud Tasks, Pub/Sub) would need a service account key, which this project rules out. The backend therefore talks to sGTM only over HTTPS with a shared secret (Phase 5).
- **No hosted dev frontend.** GitHub Pages serves one site, the prod one. "Dev" for the frontend means the local dev server on `localhost`.

## Environments

Everything is built twice: once for **dev** and once for **prod**. Each environment has its own GCP project. A third project, `huaben-tracking-platform-admin`, holds only the bootstrap resources: the Terraform state bucket, the WIF pool, and the CI service accounts. A separate staging environment isn't needed yet; add one only if dev stops being a safe place to test.

| Component | dev | prod |
|---|---|---|
| GCP project | `huaben-tracking-platform-dev` | `huaben-tracking-platform-prod` |
| Frontend | local dev server (`localhost`) | GitHub Pages |
| API and worker | local Docker Compose | production VM |
| Terraform | `infra/envs/dev` | `infra/envs/prod` (same modules, separate state) |
| Tracking domain | `tracking.dev.huaben.app` | `tracking.huaben.app` |
| sGTM server container | own container | own container |
| BigQuery | `analytics` dataset in the dev project | `analytics` dataset in the prod project |
| dbt | CI and ad-hoc runs | scheduled runs |

The web container is promoted through GTM Environments (D-028): publish a version to the `dev` environment, verify it, then publish the same version to Live. A server container split per environment is promoted by export and import: build and verify in dev, export the container JSON, import it into the prod container (merge), then publish.

**Web GTM: one container with GTM Environments (D-028).** The local dev server loads the `dev` environment's snippet, GitHub Pages loads Live, and lookup variables on the hostname (`localhost` → dev) pick the sGTM URL and the measurement ID.

**Open: how server GTM is split across environments.**
- One server container per environment. This isolates them cleanly, and each container holds its own BigQuery project and dataset.
- One shared container with a hostname lookup to pick the destination.

Recommendation: one container per environment.

---

## 0. Foundations: GCP, Terraform, CI

- Create the platform repo:
  - structure: `infra/modules`, `infra/envs/{dev,prod}`, `contract/`, `gtm/`, `dbt/`, `docs/`
  - `.gitignore`
  - pre-commit with `terraform fmt` and `gitleaks`
  - README skeleton
  - `docs/decisions.md`
  - ~~`CLAUDE.md`~~ Done in the first TP-0 PR: the repo's purpose, commands (mise, uv, pre-commit, Terraform), layout, and working rules. The rules to capture:
    - the repo is public, so no account names, organization or billing IDs, or secrets;
    - every change goes through a PR;
    - actions are pinned to SHAs and must be on the allowlist;
    - no service account keys;
    - the bootstrap is applied locally only;
    - decisions are recorded in `docs/decisions.md`;
    - `TP-n` ticket naming.
- ~~Automated PR review~~ Done in the TP-0 CI PR (`pr-review.yml`), needing the `OPENROUTER_API_KEY` repository secret. It reuses the app repo's DeepSeek/OpenRouter workflow (D-011), reviews each PR, and posts comments. The workflow must:
  - run only on same-repo PRs, and skip forks and Dependabot;
  - check out the **base** SHA, never the PR's code, and fetch the diff through the API, so a PR can't change the workflow to steal its secret;
  - have only `contents: read` and `pull-requests: write` permissions, **never `id-token: write`**, so it can't reach GCP;
  - pin actions to SHAs;
  - keep the LLM API key as a repository secret;
  - be advisory, never a required status check.
- **Identity and organization setup** (manual, before the bootstrap):
  - Sign up for Cloud Identity Free on `huaben.app` and verify the domain with a TXT record in Cloudflare.
  - Accounts: two super admins (one for administration only, one break-glass account whose credentials are kept offline) and a separate day-to-day account for GCP work. **Individual account names are deliberately left out of this public repo and its issues.**
  - Groups: `gcp-organization-admins@`, `gcp-billing-admins@`, `gcp-platform-admins@`. IAM is granted to groups, never to individual users.
  - Grant `gcp-billing-admins@huaben.app` Billing Account Administrator on the existing billing account.
  - ~~Move the three projects into the `huaben.app` organization~~ Done 2026-09-26: all three are at the organization root, and the bootstrap moves them into the `huaben` folder. Moving a project that had no organization needed Project IAM Admin on the project and Project Creator on the organization. A deleted project's ID can never be reused, so projects are moved, never recreated.
  - **Required:** set up Cloudflare Email Routing for `huaben.app`, forwarding every individual account plus `gcp-notifications@` to a mailbox you read. `huaben.app` has no mail server, so budget alerts, billing notices, and Google security or policy emails would otherwise be lost. The organization's `essentialcontacts.managed.allowedContactDomains` policy only allows `huaben.app` addresses as contacts, so a Gmail address can't be used directly.
- ~~Create the GCP projects~~ Done: `huaben-tracking-platform-dev`, `huaben-tracking-platform-prod`, and `huaben-tracking-platform-admin`.
- ~~Set budget alerts by hand~~ Done 2026-09-27 with `gcloud billing budgets create`, outside Terraform. The billing account is in EUR: `huaben-tracking-platform-dev` €5/month, `huaben-tracking-platform-prod` €5/month, and `billing-account-total` €10/month across all projects. Alerts at 50%, 90%, and 100% go to billing admins. Document the budgets and the commands in the README. The bootstrap's API list must include `billingbudgets.googleapis.com`, which is already enabled on the admin project.
- Bootstrap Terraform into `huaben-tracking-platform-admin`. This is a **one-time step a person applies locally, not CI**, because CI can't create its own credentials. It manages:
  - the `huaben` folder, with the three projects imported into state
  - a folder-level org policy `gcp.resourceLocations = in:eu-locations`
  - group IAM bindings on the organization, folder, and billing account
  - organization Essential Contacts (all categories) set to `gcp-notifications@huaben.app`
  - the GCS state bucket
  - the Workload Identity Federation (WIF) pool and GitHub provider
  - one CI service account per environment
  - the required APIs in all three projects

  The bootstrap has its own state. Document the procedure in the README.
- Set up GitHub Actions for Terraform:
  - On pull requests: fmt, validate, and plan for **both** environments.
  - On merge to `main`: apply to dev automatically, and apply to prod after approval through a GitHub Environment.
  - Authenticate with WIF, with no service account keys.
- Lock CI down for a **public repo**. Anyone can read Actions logs and plan output.
  - The WIF provider's attribute condition accepts tokens only from this repository, matched on repository ID and owner ID rather than names.
  - Use two CI service accounts per environment: a read-only one for `plan` on pull requests, and one for `apply` that trusts only `main` (dev) or the `prod` GitHub Environment.
  - Mark sensitive Terraform variables and outputs `sensitive`, and never echo secrets in workflow steps.
  - Pull requests from forks get no OIDC token, so they can't plan against GCP. That's intended.
- ~~Protect `main`~~ Done 2026-09-27 (repository ruleset "Protect main"). The follow-up items below were done in the TP-0 CI PR (2026-09-29, D-016). The required checks (`pre-commit`, `plan (dev)`, `plan (prod)`, with branches up to date) were added to the ruleset once the workflows had passed:
  - add the required status checks (pre-commit, plus the dev and prod plans) with "branches must be up to date" once the workflows have run;
  - create the `dev` and `prod` GitHub Environments. `dev` deploys automatically from `main`, and also accepts manually triggered deployments from any branch so a change can be tried before merging (D-015). `prod` deploys only from `main`, requires your approval, and holds the Cloudflare token as a `prod`-only secret;
  - add `.github/dependabot.yml` for GitHub Actions, Terraform providers, and Python (uv), and pin every action to a commit SHA.

**Decided:**
- Automated PR review: reuse the app repo's DeepSeek/OpenRouter workflow, added in the CI PR (D-011).
- Repository security (applied 2026-09-27), based on the app repo's ruleset plus hardening for a repo whose CI can change GCP:
  - Ruleset on `main` with no bypass actors, not even admins: no deletion, no force push, linear history, signed commits, and pull requests required (0 approvals, squash only). Signed commits cover every commit on a PR branch, so commits are signed locally with an SSH signing key (set up 2026-09-27).
  - Squash merges only, branches deleted after merge, auto-merge off.
  - Actions: only GitHub-owned actions plus `google-github-actions/*`, `hashicorp/*`, and `jdx/mise-action`. Every action must be pinned to a full commit SHA. Fork PRs from any outside contributor need approval before workflows run. The workflow token is read-only by default and can't approve PRs.
  - Dependabot alerts and security updates, secret scanning with push protection, and private vulnerability reporting are all on.
- Budgets are created by hand, not in Terraform. They're set once and rarely change, and keeping them out of Terraform means no Terraform identity needs budget permissions on the billing account. CI service accounts never get billing account permissions.
- Tooling: Terraform (not OpenTofu). **mise** pins every tool version (Terraform, Python, gitleaks, tflint) in `mise.toml`, and CI reads the same file through `jdx/mise-action`. **uv** manages the Python dependencies (dbt, scripts) with `pyproject.toml` and `uv.lock` in a project `.venv`.
- Access after migration: `gcp-platform-admins@` has Owner on the three projects for now, until the bootstrap moves this to the `huaben` folder. No individual users hold project roles. Project Creator on the organization was removed after the move.
- Identity: Cloud Identity Free on `huaben.app`, with GCP access granted through groups. The personal Gmail is not an admin. The old auto-created `jack93g-org` is left unused.
- Organization: the projects live in the `huaben.app` organization, under a `huaben` folder. New organizations enforce Google's secure-by-default policies, including no service account keys and domain-restricted sharing.
- Three projects: dev, prod, and admin. The bootstrap lives in the admin project, so access to prod doesn't include the Terraform state or the CI identities, and deleting or rebuilding an environment can't break the tooling that manages it.


**Deliverable:** Two empty GCP projects, fully managed by Terraform and changed only through reviewed pull requests. Every PR shows a plan for both environments.

---

## 1. Define tracking contract

- Define the event taxonomy and naming conventions.
- Write a **machine-readable contract** (for example `contract/events.yaml` or JSON Schema) as the single source of truth. Generate these from it:
  - the BigQuery schema JSON used by Terraform
  - the dbt `accepted_values` and not-null tests
  - the Pydantic models for the backend

  Add a CI check that fails if the generated files are out of date.
- Define the common fields: `event_name`, `event_id`, `schema_version`, `event_timestamp`, `server_timestamp`, `user_id`, `anonymous_id`, `session_id`, `source` (frontend or backend), and consent state.
- Define what the timestamps mean (D-026). `event_timestamp` is the business time, when the thing the event describes happened, and each event defines which moment that is. For `story_generated` it's when the generation completed. `server_timestamp` is set by sGTM when it receives the event, for both sources.
- Define event-specific properties.
- Single source per event: each event comes from either the frontend or the backend, never both.
- Identity propagation: decide how `anonymous_id` and `session_id` reach the API (for example a request header set by the frontend) and who generates `session_id`.
- Define the BigQuery event schema, kept in the repo (generated from the contract).

**Decided (2026-10-04).** The specification is [tracking-spec.md](tracking-spec.md), and the contract is `contract/events.yaml`.
- **Naming and events** (D-017): GA4's name when the event really is that GA4 event, otherwise a custom `object_action` event. The MVP's events are `page_view` and `story_generated`. `login` and `quiz_submitted` are also in the contract.
- **Contract format** (D-018): a YAML file with a Python generator, one semantic version, and the Pydantic models installed by the app from a git tag.
- **Property storage and partition column** (D-019): typed common fields plus a `properties` JSON column, partitioned on `server_timestamp`.
- **Identity** (D-020):
  - `user_id` is the app's user ID as a string.
  - The frontend generates `anonymous_id` and `session_id`, keeps them in first-party cookies, and sends them to the API in request headers.
  - Logout clears `user_id` and keeps `anonymous_id` (amended 2026-10-06; it first replaced it).
  - dbt backfills `user_id` onto earlier anonymous events on the same `anonymous_id`, within 30 days.
- **Consent** (D-021, not legally reviewed): with consent denied the frontend sends nothing and sets no identifiers. Backend events are still sent, with `user_id` but no device identifiers.
- **Retention** (D-022): 14 months for raw events and event-level models, 30 days for rejected events and logs, 7 days for sent outbox rows.
- **Timestamps** (D-026): `event_timestamp` is the business time, defined per event and never changed by retries. `server_timestamp` is when sGTM received it.
- **Late-event tolerance** (D-023): a 3-day dbt lookback, with the outbox giving up after 48 hours.
- **Backend → sGTM** (D-024): a custom client, one event per request, with a shared-secret header. The server container stores only the secret's SHA-256 hash, because the container is exported to this public repo.

**Deliverable:** A versioned tracking specification in `docs/`, the contract file, and the generated schema, with every decision above recorded in `docs/decisions.md`.

---

## 2. Set up GTM Web

**Decided (2026-10-04).**
- **Transport** (D-027): browser events are sent with the GA4 tag to the GA4 client in sGTM, in basic consent mode. The contract's own fields travel as event parameters.
- **Environments** (D-028): one web container with a `dev` GTM Environment. The local dev server loads the `dev` snippet, GitHub Pages loads Live.
- **Consent platform** (D-029): Cookiebot's free plan, loaded through its GTM template.

**Where the work happens.** Most of it is in the app repo (`jack93g/project-chinese-story-generator`): the API and the frontend. The GTM container, the GA4 property, and the Cookiebot account are set up by hand in their own UIs.

**1. Accounts and containers (by hand)**
- Create the web GTM container, with a `dev` Environment.
- Create a GA4 property, only to get a measurement ID. Nothing is forwarded to it in the MVP.
- Create the Cookiebot account for `huaben.app`.
  - Add `localhost` and `localhost:3000` as domain aliases, and first confirm that the free plan allows them. If it doesn't, fall back to vanilla-cookieconsent.

**2. API (app repo), deployed before the frontend changes**
- `/auth/me` returns only the username today. Make it return the user's ID too, so the frontend can set `user_id`.
- Add `X-Anonymous-Id`, `X-Session-Id`, and `X-Tracking-Consent` to the CORS allowed headers. They're only `Content-Type` and `X-API-Key` today, so a request carrying the new headers fails its preflight.
- The API ignores the headers until TP-5, which reads and stores them.

**3. Frontend: load GTM**
- Add the container's `<head>` snippet to the frontend's root layout. Leave out the `<noscript>` iframe: the app doesn't work without JavaScript, and the iframe would load regardless of consent.
- The build chooses which snippet: the `dev` environment's on the local dev server, Live on GitHub Pages.
- The frontend is a static export, so the container ID and the environment's snippet parameters are `NEXT_PUBLIC_…` build variables, set in the frontend's local environment file.
- Don't add the container ID to the app's `deploy-frontend.yml` in this ticket. That makes the real site load the Live container, so it's the go-live switch: a change of its own, made once the Live version in GTM is checked, the GA4 tag is absent or paused, and the privacy notice exists.

**4. Consent**
- In GTM, load Cookiebot with its tag template, on the Consent Initialization trigger. Review the template's permissions before adding it.
- In the frontend, read the consent state in one small module. The identity cookies and the `X-Tracking-Consent` header depend on it.
- The module follows Cookiebot's events. Cookiebot's script loads after the app starts, so a single read at startup would see no consent yet.
- Until Cookiebot has reported, consent is unknown and counts as denied (D-021).

**5. Identity (D-020)**
- Generate `anonymous_id` and `session_id` in the frontend's own code, not in a GTM tag, and push them to the dataLayer. The API calls need them too, outside GTM.
- Keep them in the cookies `huaben_anonymous_id` and `huaben_session_id`: `Path=/`, `SameSite=Lax`, and in prod `Secure` with `Domain=huaben.app`. On `localhost` they're host-only.
- Only create them when consent is granted.
- Send the `X-Anonymous-Id`, `X-Session-Id`, and `X-Tracking-Consent` headers with every API call, once the API change in step 2 is deployed.
- On logout, leave both cookies alone. Only `user_id` is cleared (D-020, as amended).
- When consent is withdrawn, delete both cookies and stop sending the identity headers (D-021).

**6. The dataLayer and `page_view`**
- Implement the dataLayer interface as the tracking spec defines it: one flat object per event, with every key on every push and `undefined` for a value that's absent, so a stale `user_id` can't survive a logout.
- `schema_version` is a constant in the frontend's tracking code, set to the contract version it was built against and changed by hand when that changes.
- The frontend is a Next.js single-page app, so push `page_view` on every client-side route change, not only on page load.
- The first `page_view` after a load waits for two things: Cookiebot reporting the consent state, and the session check (`/auth/me`). Without the first it would be dropped as denied, even for a returning visitor who accepted. The second makes it carry `user_id` when someone is logged in; on the login screen it's sent without one.
- Strip query strings from `page_location` and `page_referrer`, keeping only allowlisted parameters, so emails and tokens in URLs aren't sent on. The allowlist is `id` on `/story` (story pages are `/story?id=…`, and without it they'd all look the same). Everything else, such as `fresh`, is dropped.

**7. GTM: variables and the GA4 tag**
- Add dataLayer variables for the contract's fields, and lookup variables on the hostname for the sGTM URL and the measurement ID (`localhost` → dev).
- Build the GA4 tag for `page_view`, with the contract's own fields as event parameters.
- Turn off the Google tag's automatic page view, and GA4's "page changes based on browser history events". The app pushes `page_view` itself, so either would count every page twice.
- Set each tag's consent settings, so the GA4 tag is blocked until `analytics_storage` is granted.
- The GA4 tag doesn't go live in this ticket. Until the tracking domain exists it would send straight to Google, so it's connected to sGTM and published in TP-3.

**8. Verify, in GTM Preview on `localhost`**
- `page_view` appears on first load and on every route change, with the fields in the deliverable.
- A returning visitor who already accepted gets identifiers and a `page_view` on first load. A new visitor gets them as soon as they accept, without a reload.
- With consent denied or not yet given: no identity cookies, no `page_view`, and `X-Tracking-Consent: denied` on API calls.
- The banner doesn't flash and disappear on first load. Cookiebot's guide for Next.js warns of this when its script loads after the page hydrates. If it does, load the script in the frontend's root layout instead and amend D-029.
- After a logout, `anonymous_id` and `session_id` are unchanged and the next `page_view` has no `user_id`. Check the second in Preview's Data Layer tab: it confirms that pushing `undefined` clears a key.

**Note:** GitHub Pages only serves prod, so the first time the setup runs on the real site is in prod. Keep the prod GTM publish separate from the frontend deploy, so either can be rolled back on its own.

**Deliverable:** In dev, `page_view` appears in GTM Preview with every key of the dataLayer push the tracking spec defines, ready for the GA4 tag. `source`, `consent`, and `server_timestamp` aren't among them: sGTM and Consent Mode supply those. With consent denied, no identifiers are created and no event is sent (D-021).

---

## 3. Set up GTM Server on GCP

- Create the server containers for dev and prod.
- **Narrow the CI apply accounts** (D-013). They currently hold Service Account Admin and User project-wide. Service Account Admin includes `iam.serviceAccounts.setIamPolicy`, so an apply account could let itself act as any service account in its project. Once the sGTM runtime service accounts exist:
  - grant Service Account User only on those specific accounts;
  - replace Service Account Admin with narrower permissions, e.g. a custom role that can create service accounts but not set IAM on existing ones;
  - add the Cloud Run, Secret Manager, and other roles this ticket needs, and no more.
- Deploy the tagging and preview servers to Cloud Run (europe-west1) for each environment via Terraform, with the container config stored in Secret Manager.
- Map the tracking domains and set up DNS and TLS. DNS records are managed with the official Cloudflare Terraform provider, using an API token scoped to DNS edits on the `huaben.app` zone and stored as a GitHub Environment secret. Records pointing at Google must be **DNS-only (not proxied)**, or Google can't issue the certificate.
- Connect web GTM to the server container.
- **GTM export to the repo.** A script uses GTM API v2 to export the live version of each container (web and server) as JSON into `gtm/`.
  - It runs in CI on a schedule and on demand, using a read-only service account that has been added as a GTM user.
  - When the live version changes, it opens a PR, so every publish becomes a diff you can review.
  - Publishing still happens in the GTM UI.
- Stop Cloud Run request logs from storing PII. By default they record the client IP, user agent, and full URL. Add a log exclusion, or set a short retention on a dedicated log bucket.
- Verify that events are received server-side.

**Open:**
- **Domain mapping or load balancer.**

  | | Cloud Run domain mapping | Global external Application Load Balancer |
  |---|---|---|
  | Cost | Free | About $18/month per environment (forwarding rule at $0.025/h) plus $0.008/GB processed |
  | Status | Preview. Google calls it "not production-ready" because of latency. Available in europe-west1. | GA |
  | Limits | TLS 1.0/1.1 can't be disabled, no custom certificates, no Cloud Armor or CDN, certificate can take up to 24h | None relevant |
  | Terraform | `google_cloud_run_domain_mapping` | LB, serverless NEG, managed certificate |

  Recommendation: domain mapping in both environments for the MVP, since tracking requests don't block the UI. Move prod to a load balancer when real traffic arrives, or if latency shows up in monitoring.
- **Minimum instances.** Google recommends at least 3 for production. With 1, it costs roughly $40–50/month per service, more than the app's whole hosting budget. Recommendation: 0 in both environments and accept cold starts. Browser events are sent in the background, and backend events are retried by the outbox (Phase 5).
- **Public access under domain-restricted sharing.** The `huaben.app` organization only allows IAM grants to its own identities, so Cloud Run can't be opened with `allUsers`. Recommendation: disable the invoker IAM check on the sGTM tagging service (`invoker_iam_disabled = true` on `google_cloud_run_v2_service`) rather than weakening the org policy. The preview server should stay private if possible.
- **GTM in Terraform.** Only community providers exist (for example `mirefly/google-tag-manager`). None has much adoption or Google support. Use export-and-diff for the MVP and reconsider afterwards.

**Deliverable:** `tracking.huaben.app` and the dev domain serve sGTM end to end. The infrastructure is in Terraform, and both containers' JSON is in the repo.

---

## 4. Build BigQuery pipeline

- Create the `analytics` dataset and `events` table in each environment via Terraform, using the generated schema.
- Partition daily on the column chosen in Phase 1, cluster by `event_name`, and set partition expiration per the retention policy.
- Give the sGTM service account write access to the `analytics` dataset only.
- Build the sGTM → BigQuery tag. sGTM has no built-in BigQuery tag, so this is a custom template using the `BigQuery.insert` sandbox API. Map events to the schema.
- Map browser events to the contract's row first (D-027). They arrive through the GA4 client in GA4's shape, while backend events arrive already in the contract's shape. On the browser path, always set `source` to `frontend` and refuse the names of backend events, because that path takes no secret.
- On insert failure, the tag calls `logToConsole` with the `event_id` and the error, so that Phase 8 alerts have something to fire on.
- Don't write the IP address or other unnecessary PII.
- Validate the schema and data types, and test malformed events against the defined behaviour.

**Decisions:**
- **Behaviour for malformed events.** One bad row can fail an insert. Options:
  - drop it
  - use `skipInvalidRows`
  - validate in sGTM and write rejects, with their raw payload and the reason, to an `events_rejected` table

  Recommendation: the rejects table, so nothing is lost silently.
- **Guarding the browser path (D-027).** The GA4 client's path takes no secret, so anyone can post forged `page_view` events, made-up identifiers, or bulk spam. Options:
  - validate each event against the contract (known event name, UUID identifiers, property types) and limit string lengths and request size
  - also check the request's `Origin` against the site's hostnames, which stops casual misuse but is trivially forged outside a browser
  - rate limit, which Cloud Run can't do by itself: it needs Cloud Armor, and so the load balancer (TP-3)

  Recommendation: validation and size limits, with the `Origin` check, and accept the rest for the MVP. Bulk spam is bounded by the Cloud Run instance limit and shows up in the budget alerts.

**Note:** Writes from sGTM to BigQuery are best-effort. A failed insert is logged but not retried. The durable upgrade is Pub/Sub with a BigQuery subscription (after the MVP).

**Deliverable:** In dev, a test `page_view` lands in `analytics.events` within a minute. A malformed test event is handled as defined, and a forced insert failure produces a log entry.

---

## 5. Implement backend tracking

- **sGTM side:** implement the custom client (D-024). It checks the shared-secret header against the SHA-256 hash stored in the container.
- Define a small tracking module in FastAPI, using the Pydantic models generated from the contract.
- Read `anonymous_id`, `session_id`, and consent state from the `X-Anonymous-Id`, `X-Session-Id`, and `X-Tracking-Consent` request headers (D-020). Drop values that aren't UUIDs. The frontend already sends the headers, and CORS already allows them (TP-2). The first API call of each page load, the session check, always says `denied`, because it runs before the consent state is known; record nothing from it.
- **App change:** `story_generation_requests` has no `user_id` today. Add it, and record the requesting user when a generation is created.
- Generate authoritative business events: `story_generated` for the MVP, then `login` and `quiz_submitted`, which the contract already defines. The app has no sign-up or "add vocabulary" action today; `sign_up` is added if the app gains one (D-017).
- Add `event_id` and `event_timestamp` once, when the outbox row is written. For `story_generated`, `event_timestamp` is the request's `completed_at` (D-026). Retries never change either. `server_timestamp` is set by sGTM.
- Send events without blocking the user's request. Retries reuse the same `event_id` so they stay idempotent.

**Delivery design (Open; document the result):**
- **Problem.**
  - In-process background tasks lose events when the process restarts.
  - The VM has no GCP identity, so Cloud Tasks and Pub/Sub would need a service account key, which is ruled out.
  - Retries only cover the hop to sGTM, because sGTM returns 200 whether or not the BigQuery insert succeeds.
- **Options.**
  1. **In-process async queue.** Retry with backoff and flush on shutdown via FastAPI's lifespan handler. Cheap, at-most-once, and loses events on a crash or redeploy.
  2. **Transactional outbox in Postgres, sent by the existing worker.**
     - In the same database transaction as the business write, insert a row into a `tracking_outbox` table: `event_id` (primary key), payload, `created_at`, `attempts`, `next_attempt_at`, `sent_at`, `last_error`.
     - The existing durable worker claims unsent rows (`FOR UPDATE SKIP LOCKED`), POSTs them to sGTM with the shared-secret header, and marks them sent. Failures back off and retry with the same `event_id`. After 48 hours of retries, a row is marked dead (D-023).
     - Events survive crashes and redeploys, and are never recorded for a business write that rolled back.
     - Delivery is at-least-once, and dbt dedup removes the duplicates.
     - It reuses Postgres and the worker, with no new infrastructure or GCP credentials. The user's request only pays for a local insert.
  3. **Cloud Tasks or Pub/Sub.** Durable, but rejected because they need a service account key on the VM.
- **Recommendation:** the outbox.
- **Identity context.** `story_generated` is produced by the worker, which has no HTTP request to read headers from. Capture `user_id`, `anonymous_id`, `session_id`, and consent when the generation request is created, store them with it, and copy them into the outbox payload.
- **Housekeeping.** Delete sent rows after 7 days (D-022).
- **Secret.** The sGTM shared secret reaches the VM the same way as the app's other runtime secrets (the M5 deploy process), never through the repo. It's stored nowhere else: sGTM holds only its hash (D-024).

**Open:**
- Are `login` and `quiz_submitted` part of the MVP? Only `story_generated` is needed for the MVP boundary.

**Deliverable:** A `story_generated` sent from the dev API lands in dev `analytics.events` with the same `anonymous_id` as the `page_view` from the same browser. With sGTM made unreachable, events wait in the outbox and are delivered, without duplicates in `fct_events`, once it's back.

---

## 6. dbt modeling

- Set up a dbt Core project against BigQuery (D-025), with `dev` and `prod` targets. The source definition and its tests are generated from the contract into `dbt/models/staging/_contract__sources.yml`. Pin dbt-core to 1.10.5 or later: the generated tests use the `arguments` property (D-018).
- Build `stg_events`: incremental, typed, cleaned, and deduplicated on `event_id`, with a 3-day lookback window (D-023).
- Build an identity-map model (`anonymous_id` → `user_id`) that implements the identity rules in D-020.
- Build `fct_events`: frontend and backend events joined on identity, with `user_id` backfilled per the identity map.
- Add tests, generated from the contract where possible:
  - unique and not-null `event_id`
  - accepted values for `event_name` and `source`
  - not-null required fields
- Apply the retention policy to derived tables.
- CI: run `dbt build` on pull requests into a per-PR dataset in the **dev project**, reading dev `analytics.events`. Prod data never reaches CI.
- Schedule prod runs with a GitHub Actions cron job. No orchestrator is needed yet.
- Give each environment its own dbt service account, authenticated through WIF, with dataset-level permissions.

**Open:**
- How to clean up per-PR datasets: drop them when the PR closes, or set a default table expiration on them.

**Deliverable:** `dbt build` passes in CI against dev data. A scheduled prod run produces `fct_events` with `page_view` and `story_generated` stitched by `anonymous_id`.

---

## 7. Privacy and data quality

The decisions were made in Phase 1. This phase **verifies** them.

- Verify consent handling for frontend and backend events, including the consent-denied path.
- Confirm no unnecessary PII reaches BigQuery **or Cloud Logging**.
- Verify the identity rules across login, logout, several devices, and a shared device.
- Test duplicate, missing, and late events, including backend retries producing duplicates that dbt removes.
- Document data ownership and who can access the prod dataset. Confirm the retention policy is applied everywhere: raw, derived, and logs.

**Deliverable:** Every privacy and identity decision from Phase 1 has a test or check showing it holds.

---

## 8. Observability and documentation

- Add log-based alerts for:
  - sGTM errors
  - failed BigQuery inserts (from the tag's `logToConsole` entries)
  - outbox backlog: unsent rows older than N minutes, or rows marked dead. The VM isn't in Cloud Monitoring, so this goes through the app's existing observability (app ticket M5-6).
- Add a dbt source freshness check to catch stalled ingestion.
- Document the event taxonomy, architecture, environments and GTM promotion flow, how to add a new event, and key decisions.

**Open:**
- Freshness thresholds. A low-traffic app will raise false alarms overnight. Set thresholds from observed traffic, or check volume over a longer window.
- Where alerts go: email, or a chat channel.

**Deliverable:** A deliberately failed BigQuery insert in dev triggers an alert. Someone new can add an event by following the docs alone.

---

## MVP boundary

```
Frontend ── page_view ────────┐
                              ▼
Backend ── story_generated ─► sGTM ─► analytics.events ─► dbt ─► fct_events
```

The epic is complete when, in prod:
- a test `page_view` and a test `story_generated` from the same browser appear in `fct_events` as one stitched journey, deduplicated and with dbt tests passing;
- all infrastructure is in Terraform and deployed via CI;
- GTM container versions are in the repo.

**Open: are Phases 7 and 8 part of the MVP?** Recommendation:
- Phase 7: yes. Privacy verification can't wait once real users are tracked.
- Phase 8: only the failed-insert and freshness alerts are MVP. The fuller documentation can follow.

## After the MVP

- Route GA4 through sGTM, enable the GA4 BigQuery export, and build a reconciliation model.
- Add a sessions and funnels model in dbt.
- Add Meta Pixel with the Conversions API as a hybrid tracking example.
- Move dbt scheduling to Airflow if orchestration needs grow.
- Make ingestion durable with Pub/Sub and a BigQuery subscription between sGTM and BigQuery.
- Move prod sGTM behind a global load balancer.
- Evaluate managing GTM configuration in Terraform once a provider is mature.
- Add a staging environment if dev stops being a safe place to test.
