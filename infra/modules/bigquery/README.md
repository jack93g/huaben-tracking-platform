# BigQuery module

The `analytics` dataset for one environment: the raw events sGTM writes, and the events it rejects.

## What it creates

- The BigQuery API.
- The `analytics` dataset, in the location the environment passes (an EU location; it can't be changed later).
- `analytics.events`:
  - The schema is generated from the contract (`contract/generated/bigquery/events.schema.json`). It may only grow: any other change replaces the table and loses its data (D-019).
  - Partitioned by day on `server_timestamp`, clustered by `event_name`, and expiring after 14 months (D-022).
  - `deletion_protection` is on by default.
- `analytics.events_rejected` (D-040): events that failed validation, with their raw payload (cut to a fixed length) and the reason. Partitioned by day on `received_at`, expiring after 30 days. Its schema is written by hand in `events_rejected.schema.json`, because it is not part of the contract.
- `roles/bigquery.dataEditor` on the dataset, for each service account in `writers`. Nothing is granted on the project. The role is wider than inserting rows needs (it can also change and delete tables); a narrower custom role would have to be created in the bootstrap, which wasn't thought worth it for one dataset.

The CI apply accounts manage all of this with the `tfApplyBigQuery` role from the bootstrap.
