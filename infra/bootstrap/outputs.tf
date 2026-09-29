# Values the CI workflows need. None of them are secrets.

output "workload_identity_provider" {
  description = "Full resource name of the WIF provider, for google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "ci_service_accounts" {
  description = "CI service account emails, keyed by <env>/<plan|apply>."
  value       = { for key, sa in google_service_account.ci : key => sa.email }
}

output "state_bucket" {
  description = "GCS bucket holding all Terraform state."
  value       = google_storage_bucket.tfstate.name
}
