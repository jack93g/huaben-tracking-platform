# Only the APIs the bootstrap and CI need to get started. Each environment's
# Terraform enables the APIs for what it deploys (Cloud Run, BigQuery, ...).

locals {
  admin_apis = [
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "essentialcontacts.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "orgpolicy.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]

  env_apis = [
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
  ]

  project_apis = merge(
    { for api in local.admin_apis : "admin/${api}" => { project = local.admin_project_id, api = api } },
    merge([
      for env, project in local.env_projects : {
        for api in local.env_apis : "${env}/${api}" => { project = project, api = api }
      }
    ]...),
  )
}

resource "google_project_service" "this" {
  for_each = local.project_apis

  project            = google_project.this[split("/", each.key)[0]].project_id
  service            = each.value.api
  disable_on_destroy = false
}
