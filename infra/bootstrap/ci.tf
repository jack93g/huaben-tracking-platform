# GitHub Actions identities: Workload Identity Federation, no service account
# keys (D-003). Each environment has two service accounts:
#   plan  - read-only; used by any workflow run in this repository, e.g. PR plans.
#   apply - makes changes; only usable by jobs running in the matching GitHub
#           Environment (dev, or prod with its required approval).

locals {
  ci_accounts = merge([
    for env in keys(local.env_projects) : {
      "${env}/plan"  = { env = env, sa = "plan" }
      "${env}/apply" = { env = env, sa = "apply" }
    }
  ]...)

  ci_project_roles = {
    plan = [
      "roles/viewer",
      "roles/iam.securityReviewer",
    ]
    # Extended as later tickets add resources (Cloud Run, BigQuery, Secret
    # Manager, ...). Project IAM Admin lets this account grant itself further
    # roles in its own project, so it's effectively admin of that project only.
    apply = [
      "roles/viewer",
      "roles/serviceusage.serviceUsageAdmin",
      "roles/resourcemanager.projectIamAdmin",
      "roles/iam.serviceAccountAdmin",
      "roles/iam.serviceAccountUser",
    ]
  }

  ci_project_bindings = merge([
    for key, account in local.ci_accounts : {
      for role in local.ci_project_roles[account.sa] : "${key}/${role}" => {
        account = key
        project = local.env_projects[account.env]
        role    = role
      }
    }
  ]...)

  # GitHub's OIDC subject for a job that uses a GitHub Environment. This repo
  # uses GitHub's immutable subject format, which embeds the owner and
  # repository IDs: repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<env>
  # (see GET /repos/{repo}/actions/oidc/customization/sub).
  environment_subject = "repo:${local.github.owner}@${local.github.owner_id}/${local.github.repo}@${local.github.repository_id}:environment"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = google_project.this["admin"].project_id
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = google_project.this["admin"].project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "huaben-tracking-platform"
  display_name                       = "huaben-tracking-platform"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
  }

  # Only tokens from this repository are accepted at all.
  attribute_condition = "assertion.repository_id == '${local.github.repository_id}' && assertion.repository_owner_id == '${local.github.owner_id}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "ci" {
  for_each = local.ci_accounts

  project      = google_project.this["admin"].project_id
  account_id   = "tf-${each.value.sa}-${each.value.env}"
  display_name = "Terraform ${each.value.sa} (${each.value.env})"

  depends_on = [google_project_service.this]
}

resource "google_service_account_iam_member" "ci_wif" {
  for_each = local.ci_accounts

  service_account_id = google_service_account.ci[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member = (
    each.value.sa == "plan"
    ? "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${local.github.repository_id}"
    : "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/${local.environment_subject}:${each.value.env}"
  )
}

resource "google_project_iam_member" "ci" {
  for_each = local.ci_project_bindings

  project = google_project.this[split("/", each.value.account)[0]].project_id
  role    = each.value.role
  member  = google_service_account.ci[each.value.account].member
}
