# The analytics dataset for one environment: the raw events sGTM writes
# (D-019), and the events it rejects (D-040).

locals {
  day_ms = 24 * 60 * 60 * 1000
}

resource "google_project_service" "this" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "analytics" {
  project       = var.project_id
  dataset_id    = "analytics"
  friendly_name = "Analytics"
  description   = "Raw events written by sGTM, and the events it rejected."
  location      = var.location

  depends_on = [google_project_service.this]
}

# Raw events. The schema is generated from the contract, and may only grow:
# any other change replaces the table and loses its data (D-019).
resource "google_bigquery_table" "events" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "events"

  description         = "One row per received event. Delivery is at-least-once, so event_id is not unique here."
  schema              = file("${path.module}/../../../contract/generated/bigquery/events.schema.json")
  deletion_protection = var.deletion_protection

  # Partitioned on the platform's own clock, not the sender's (D-019).
  time_partitioning {
    type          = "DAY"
    field         = "server_timestamp"
    expiration_ms = var.events_retention_days * local.day_ms
  }

  clustering = ["event_name"]
}

resource "google_bigquery_table" "events_rejected" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "events_rejected"

  description         = "Events that failed validation, with their raw payload and the reason (D-040)."
  schema              = file("${path.module}/events_rejected.schema.json")
  deletion_protection = var.deletion_protection

  time_partitioning {
    type          = "DAY"
    field         = "received_at"
    expiration_ms = var.rejected_retention_days * local.day_ms
  }
}

# Write access on this dataset only, never on the project. sGTM inserts rows
# with the streaming API, which needs no permission to run jobs.
resource "google_bigquery_dataset_iam_member" "writer" {
  for_each = var.writers

  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${each.value}"
}
