output "tagging_url" {
  description = "The tagging service's run.app URL. Empty until the services are deployed."
  value       = one(google_cloud_run_v2_service.tagging[*].uri)
}

output "preview_url" {
  description = "The preview service's run.app URL. Empty until the services are deployed."
  value       = one(google_cloud_run_v2_service.preview[*].uri)
}

output "secret_id" {
  description = "The secret that holds the container config. A person adds its value."
  value       = google_secret_manager_secret.container_config.secret_id
}

output "runtime_service_accounts" {
  description = "The runtime service accounts' emails, keyed by service."
  value       = { for key, sa in google_service_account.runtime : key => sa.email }
}
