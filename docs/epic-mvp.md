# Epic: Server-side tracking platform (MVP)

This is the overview of the epic: where the app runs, how the environments are split, and what counts as done. The tickets themselves are GitHub issues, listed under [Tickets](#tickets).

Decisions marked **Open** must be resolved and recorded in `docs/decisions.md` before the ticket that depends on them starts.

## Hosting context

The app being tracked is not on GCP:
- **API, durable worker, and Postgres:** Docker Compose on a single small VM.
- **Frontend:** GitHub Pages.
- **DNS:** `huaben.app` is served by Cloudflare.
- **Budget:** $10–25/month for the app's hosting (see the app repo's deployment decisions).

What this means for the platform:
- **Cost.** GCP should stay close to the free tiers: Cloud Run with `min-instances = 0`, domain mapping instead of a load balancer, and BigQuery within its free storage and query allowances. Target under $10/month for both projects together, and set budget alerts to match.
- **Backend credentials.** The VM has no GCP identity. Calling GCP APIs from it (Cloud Tasks, Pub/Sub) would need a service account key, which this project rules out. The backend therefore talks to sGTM only over HTTPS with a shared secret (TP-5).
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

## Tickets

The tickets are GitHub issues, sub-issues of the epic (issue #1), on the "Chinese Story Generator" project board. Each issue holds its ticket's full text and is the only place it's kept (D-030). Their status is on the board.

| Ticket | Issue |
|---|---|
| TP-0: Foundations: GCP, Terraform, CI | [#2](https://github.com/jack93g/huaben-tracking-platform/issues/2) |
| TP-1: Define tracking contract | [#3](https://github.com/jack93g/huaben-tracking-platform/issues/3) |
| TP-2: Set up GTM Web | [#4](https://github.com/jack93g/huaben-tracking-platform/issues/4) |
| TP-3: Set up GTM Server on GCP | [#5](https://github.com/jack93g/huaben-tracking-platform/issues/5) |
| TP-4: Build BigQuery pipeline | [#6](https://github.com/jack93g/huaben-tracking-platform/issues/6) |
| TP-5: Implement backend tracking | [#7](https://github.com/jack93g/huaben-tracking-platform/issues/7) |
| TP-6: dbt modeling | [#8](https://github.com/jack93g/huaben-tracking-platform/issues/8) |
| TP-7: Privacy and data quality | [#9](https://github.com/jack93g/huaben-tracking-platform/issues/9) |
| TP-8: Observability and documentation | [#10](https://github.com/jack93g/huaben-tracking-platform/issues/10) |

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

**Open: are TP-7 and TP-8 part of the MVP?** Recommendation:
- TP-7: yes. Privacy verification can't wait once real users are tracked.
- TP-8: only the failed-insert and freshness alerts are MVP. The fuller documentation can follow.

## After the MVP

- Route GA4 through sGTM, enable the GA4 BigQuery export, and build a reconciliation model.
- Add a sessions and funnels model in dbt.
- Add Meta Pixel with the Conversions API as a hybrid tracking example.
- Move dbt scheduling to Airflow if orchestration needs grow.
- Make ingestion durable with Pub/Sub and a BigQuery subscription between sGTM and BigQuery.
- Move prod sGTM behind a global load balancer.
- Evaluate managing GTM configuration in Terraform once a provider is mature.
- Add a staging environment if dev stops being a safe place to test.
