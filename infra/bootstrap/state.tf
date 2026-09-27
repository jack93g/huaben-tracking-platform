# Terraform state for the bootstrap (prefix bootstrap/) and each environment
# (prefix envs/<env>/).

resource "google_storage_bucket" "tfstate" {
  project  = google_project.this["admin"].project_id
  name     = local.state_bucket
  location = "EU"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  # Keep the 20 most recent superseded versions of each state file.
  lifecycle_rule {
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.this]
}

# CI service accounts can only reach their own environment's prefix. Listing
# objects is checked against the bucket itself, so the condition allows the
# bucket resource plus objects under envs/<env>/.
locals {
  state_access = merge([
    for env in keys(local.env_projects) : {
      "${env}/plan"  = { env = env, sa = "plan", role = "roles/storage.objectViewer" }
      "${env}/apply" = { env = env, sa = "apply", role = "roles/storage.objectUser" }
    }
  ]...)
}

resource "google_storage_bucket_iam_member" "ci_state" {
  for_each = local.state_access

  bucket = google_storage_bucket.tfstate.name
  role   = each.value.role
  member = google_service_account.ci[each.key].member

  condition {
    title      = "envs-${each.value.env}-only"
    expression = "resource.type == \"storage.googleapis.com/Bucket\" || resource.name.startsWith(\"projects/_/buckets/${local.state_bucket}/objects/envs/${each.value.env}/\")"
  }
}
