# huaben-tracking-platform

Server-side tracking for [Huaben](https://huaben.app).

Browser events go through Google Tag Manager, and business events come from the app's backend. Both arrive at a server-side GTM container on Cloud Run, land in BigQuery, and are modelled with dbt.

```
Frontend ── page_view ────────┐
                              ▼
Backend ── story_generated ─► sGTM ─► analytics.events ─► dbt ─► fct_events
```

The plan is in [docs/epic-mvp.md](docs/epic-mvp.md), and the reasoning behind it is in [docs/decisions.md](docs/decisions.md). What's tracked, and how, is in [docs/tracking-spec.md](docs/tracking-spec.md).

## Repository layout

| Path | Contents |
|---|---|
| `infra/bootstrap/` | One-time setup, applied locally: state bucket, Workload Identity Federation, CI service accounts, folder, and org policies |
| `infra/modules/` | Terraform modules shared by the environments |
| `infra/envs/{dev,prod}/` | One Terraform root per environment, each with its own state |
| `contract/` | The machine-readable tracking contract, and what's generated from it |
| `gtm/` | Exported GTM container versions (JSON) |
| `dbt/` | The dbt project |
| `docs/` | The epic, decisions, and the tracking specification |

## Environments

| | dev | prod |
|---|---|---|
| GCP project | `huaben-tracking-platform-dev` | `huaben-tracking-platform-prod` |
| Frontend | local dev server (`localhost`) | GitHub Pages |
| Tracking domain | `tracking.dev.huaben.app` | `tracking.huaben.app` |

Bootstrap resources live in `huaben-tracking-platform-admin`.

## Getting started

You need [mise](https://mise.jdx.dev) activated in your shell. It installs every other tool at the version pinned in `mise.toml`.

```bash
mise install
```

```bash
uv sync
```

```bash
pre-commit install
```

- `mise install` installs Terraform, tflint, gitleaks, Python, and uv.
- `uv sync` installs the Python dependencies into `.venv`, which mise activates when you `cd` into the repo.
- `pre-commit install` enables the git hooks: formatting, Terraform checks, and gitleaks.

GCP access uses your `huaben.app` account:

```bash
gcloud auth login
```

```bash
gcloud auth application-default login
```

```bash
gcloud auth application-default set-quota-project huaben-tracking-platform-admin
```

## CI

| Workflow | Runs on | What it does |
|---|---|---|
| `checks.yml` | every PR, and pushes to `main` | pre-commit hooks (formatting, `terraform validate`, tflint, gitleaks), plus a gitleaks scan of the whole history |
| `terraform.yml` | PRs | `plan (dev)` and `plan (prod)` with the read-only plan accounts |
| | merge to `main` | apply to dev, plan prod (shown in the run's summary), then apply to prod once you approve in the `prod` GitHub Environment |
| | manual run on any branch | apply that branch to dev, to try it before merging |
| `pr-review.yml` | PRs | advisory DeepSeek review via OpenRouter (needs the `OPENROUTER_API_KEY` repository secret) |

- The required checks on `main` are `pre-commit`, `plan (dev)`, and `plan (prod)`.
- **Workflow logs are public**, so Terraform code must never print secrets. Mark sensitive values `sensitive`.
- Dependabot updates GitHub Actions, Terraform providers, and Python dependencies weekly. Tool versions in `mise.toml` are bumped by hand.

## Budgets

Budgets are managed by hand, outside Terraform ([D-005](docs/decisions.md#d-005-budgets-are-managed-by-hand-outside-terraform)). The billing account is in EUR, and every budget alerts billing admins at 50%, 90%, and 100%.

| Budget | Amount | Scope |
|---|---|---|
| `huaben-tracking-platform-dev` | €5/month | dev project |
| `huaben-tracking-platform-prod` | €5/month | prod project |
| `billing-account-total` | €10/month | all projects |

To recreate one, for example dev, run this as a member of `gcp-billing-admins@`. It needs `billingbudgets.googleapis.com` enabled on the quota project.

```bash
gcloud billing budgets create --billing-account="$BILLING_ACCOUNT_ID" --display-name="huaben-tracking-platform-dev" --budget-amount=5EUR --filter-projects=projects/huaben-tracking-platform-dev --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

For `billing-account-total`, leave out `--filter-projects`.
