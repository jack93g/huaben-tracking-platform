output "dataset_id" {
  description = "The analytics dataset's ID."
  value       = google_bigquery_dataset.analytics.dataset_id
}

output "events_table_id" {
  description = "The raw events table's ID."
  value       = google_bigquery_table.events.table_id
}

output "events_rejected_table_id" {
  description = "The rejected events table's ID."
  value       = google_bigquery_table.events_rejected.table_id
}
