# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Server-side tracking for [Huaben](https://huaben.app), a Chinese story generator. The app itself lives in a separate repo, `jack93g/project-chinese-story-generator`:
- a FastAPI API, a worker, and Postgres in Docker Compose on a DigitalOcean Droplet;
- a static frontend on GitHub Pages.

This repo holds the tracking infrastructure: web GTM, a server-side GTM (sGTM) container on Cloud Run, BigQuery, and dbt.

```
Frontend ── page_view ────────┐
                              ▼
Backend ── story_generated ─► sGTM ─► analytics.events ─► dbt ─► fct_events
```

- **Plan:** [docs/epic-mvp.md](docs/epic-mvp.md) is the source of truth. Tickets `TP-0` to `TP-8` are sub-issues of the epic (issue #1), on the "Chinese Story Generator" project board.
- **Reasoning:** [docs/decisions.md](docs/decisions.md) records the decisions and why they were made.

## Commands

Tools are pinned in `mise.toml`. With mise activated in the shell, `cd` into the repo puts the pinned Terraform, tflint, gitleaks, Python, and uv on `PATH`, and activates `.venv`.

```bash
mise install                 # install the pinned tools
uv sync                      # install Python dependencies into .venv
pre-commit install           # enable the git hooks (once per clone)
pre-commit run --all-files   # run every hook: formatting, terraform fmt/validate, gitleaks
```

GCP access uses a `huaben.app` Cloud Identity account, never a personal account:

```bash
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project huaben-tracking-platform-admin
```

mise's shell hook only runs in interactive shells. In scripts and non-interactive commands, use `mise exec -- <command>` (for example `mise exec -- terraform plan`) to get the pinned versions.

Sessions expire. If `gcloud` or Terraform fails with a re-authentication error, the user has to log in again interactively; you can't do it for them.

## Layout

| Path | Contents |
|---|---|
| `infra/bootstrap/` | One-time setup applied **locally** by a person: state bucket, Workload Identity Federation, CI service accounts, `huaben` folder, org policies, Essential Contacts |
| `infra/modules/` | Terraform modules shared by the environments |
| `infra/envs/{dev,prod}/` | One Terraform root per environment, each with its own state; applied by CI |
| `contract/` | The machine-readable tracking contract, the single source for the BigQuery schema, dbt tests, and Pydantic models |
| `gtm/` | Exported GTM container versions (JSON), written by a CI job, not by hand |
| `dbt/` | The dbt project |
| `.github/workflows/` | `checks.yml` (pre-commit and a gitleaks history scan), `terraform.yml` (plans on PRs; applies dev then prod), `pr-review.yml` (advisory DeepSeek review) |
| `scripts/` | Helper scripts, e.g. `openrouter_pr_review.py` (the PR reviewer, adapted from the app repo) |

## GCP

- **Projects:** `huaben-tracking-platform-dev`, `huaben-tracking-platform-prod`, and `huaben-tracking-platform-admin` (bootstrap resources only), all in the `huaben.app` organization.
- **Region and location:** europe-west1 for regional resources. Everything stays in EU locations; a folder policy enforces this once the bootstrap runs.
- **Access:** IAM is granted to groups only (`gcp-organization-admins@`, `gcp-billing-admins@`, `gcp-platform-admins@`), never to individual users.
- **Organization policies in force:**
  - **No service account keys.** CI authenticates through Workload Identity Federation.
  - **Domain-restricted sharing.** `allUsers` can't be granted, so public Cloud Run services use `invoker_iam_disabled = true` instead.
- **Budgets:** managed by hand, outside Terraform (see the README). CI identities never get billing permissions.
- **The app's backend has no GCP identity.** It reaches sGTM over HTTPS with a shared secret. Never design anything that needs GCP credentials on the Droplet.

## Rules

**This repo is public.**
- Never commit, or write into issues or PRs:
  - individual account names (especially super admins);
  - organization, billing account, or customer IDs;
  - secrets or tokens.
- Use placeholders such as `$BILLING_ACCOUNT_ID`.
- Before publishing text anywhere public, check it for these. GitHub keeps edit history, so a leak can't be fixed just by editing it out.

**Changes go through pull requests.**
- `main` is protected by a ruleset with no bypass: PRs only, squash merge, linear history, signed commits.
- **Every commit on a PR branch must be signed**, not just the squash commit. GitHub checks the branch's commits too, and one unsigned commit blocks the merge.
  - Commits are signed automatically with the user's SSH signing key (global git config: `gpg.format ssh`, `commit.gpgsign true`, and the author email is the GitHub no-reply address).
  - Never pass `--no-gpg-sign` or override `user.email`.
  - If signing fails, the key probably isn't loaded in the agent. Ask the user to run `ssh-add --apple-use-keychain ~/.ssh/id_ed25519_signing`.
- Work on a short-lived branch off `main`, named after the ticket (e.g. `tp-0/bootstrap`). It's squash-merged and then deleted (D-015). There is no persistent `dev` branch: environments are Terraform roots, not branches.
- Don't push, open PRs, or merge without the user's go-ahead.

**GitHub Actions is a security boundary**, because this repo's CI can change GCP.
- Pin every action to a full commit SHA, with the version in a comment.
- Only GitHub-owned actions, `google-github-actions/*`, `hashicorp/*`, and `jdx/mise-action` are allowed. Adding another means changing the repo's allowlist first, which the user decides.
- Give each workflow the minimum `permissions`.
- Only the Terraform workflows get `id-token: write`. The PR review workflow must never have it.
- Workflows that handle secrets check out the base SHA, not the PR's code, and skip forks and Dependabot.

**Terraform:**
- The bootstrap is only ever applied locally, by a person.
- Environments are applied by CI: dev on merge to `main`, prod after approval in the `prod` GitHub Environment. A branch can also be deployed to dev manually, before merging, to try it out.
- Commit `.terraform.lock.hcl`, and pin provider versions.
- `*.tfvars` files are gitignored.
- **No secrets in Terraform state.** PR plans run the PR's own code with read access to state and print to public logs (D-013). Pass secrets with write-only arguments (e.g. `secret_data_wo`) or ephemeral resources, never as regular attributes or outputs.
- **CI apply accounts get the least privilege a deployment needs.** Add a role in `infra/bootstrap/ci.tf` only when a ticket needs it. Never grant an unconditioned Project IAM Admin, Owner, Editor, or Service Account Token Creator. Project-level grants go through Project IAM Admin with a `modifiedGrantsByRole` condition listing the allowed roles.
- Don't add `external` data sources, `local-exec` provisioners, or other code that runs during `plan`, without flagging it to the user: it runs with CI credentials on every PR.

**IAM changes that grant or remove access are made by the user, not by you.** Give them the exact command or console steps, then verify the result afterwards.

## Decisions and tickets

- Record decisions in `docs/decisions.md`: add an entry with an ID and move it from **Open** to **Accepted**. Entries are superseded, never deleted.
- `docs/epic-mvp.md` holds the full text of every ticket. When it changes, update the matching GitHub issue body to match.
- The user treats this project as a way to learn. For decisions, lay out the options and trade-offs, give a recommendation, and let them choose. Don't pick silently, and don't treat an open decision as settled.
