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
    # Least privilege: a role is added only when a ticket deploys something
    # that needs it (Cloud Run, BigQuery, Secret Manager, ...). Never add an
    # unconditioned Project IAM Admin: it would let the account grant itself
    # any role. When project-level grants are needed, add it with an IAM
    # condition on iam.googleapis.com/modifiedGrantsByRole listing only the
    # low-privilege roles it may grant (D-013).
    # Service Account Admin and User are not granted: the custom roles and the
    # per-account Service Account User bindings below replace them (D-037).
    apply = [
      "roles/viewer",
      "roles/serviceusage.serviceUsageAdmin",
      "roles/run.admin",
    ]
  }

  # Custom roles for the apply accounts, created in each environment project.
  # None of them can set IAM policy on service accounts, and none can read or
  # add a secret's version directly. They can still set a secret's IAM policy
  # (to give a runtime account access), so they are not a barrier to reading
  # it: see D-037.
  ci_apply_custom_roles = {
    tfApplyServiceAccounts = {
      title       = "Terraform apply: manage service accounts"
      description = "Create and manage service accounts, without setting their IAM policy."
      permissions = [
        "iam.serviceAccounts.create",
        "iam.serviceAccounts.delete",
        "iam.serviceAccounts.get",
        "iam.serviceAccounts.list",
        "iam.serviceAccounts.update",
      ]
    }
    tfApplySecrets = {
      title       = "Terraform apply: manage secrets"
      description = "Create secrets and set who can access them. Cannot add or read versions directly."
      permissions = [
        "secretmanager.secrets.create",
        "secretmanager.secrets.delete",
        "secretmanager.secrets.get",
        "secretmanager.secrets.getIamPolicy",
        "secretmanager.secrets.list",
        "secretmanager.secrets.setIamPolicy",
        "secretmanager.secrets.update",
      ]
    }
    tfApplyLogExclusions = {
      title       = "Terraform apply: manage log exclusions"
      description = "Manage log exclusions only. Cannot create sinks to other destinations."
      permissions = [
        "logging.exclusions.create",
        "logging.exclusions.delete",
        "logging.exclusions.get",
        "logging.exclusions.list",
        "logging.exclusions.update",
      ]
    }
  }

  ci_apply_custom_role_bindings = merge([
    for env in keys(local.env_projects) : {
      for role in keys(local.ci_apply_custom_roles) : "${env}/${role}" => { env = env, role = role }
    }
  ]...)

  # The runtime accounts the apply accounts may act as, per environment, and
  # no others (D-037). Each is bound by name. The accounts are created by the
  # environment's own apply, and a binding on an account that does not exist
  # yet fails, so an environment is added here only after its accounts exist:
  # prod's after its first apply (the module's deploy_services flag allows
  # that order).
  sgtm_runtime_accounts = {
    dev = ["sgtm-tagging", "sgtm-preview"]
  }

  sgtm_runtime_account_bindings = merge([
    for env, names in local.sgtm_runtime_accounts : {
      for name in names : "${env}/${name}" => { env = env, name = name }
    }
  ]...)

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

resource "google_project_iam_custom_role" "ci_apply" {
  for_each = local.ci_apply_custom_role_bindings

  project     = local.env_projects[each.value.env]
  role_id     = each.value.role
  title       = local.ci_apply_custom_roles[each.value.role].title
  description = local.ci_apply_custom_roles[each.value.role].description
  permissions = local.ci_apply_custom_roles[each.value.role].permissions
}

resource "google_project_iam_member" "ci_apply_custom" {
  for_each = local.ci_apply_custom_role_bindings

  project = local.env_projects[each.value.env]
  role    = google_project_iam_custom_role.ci_apply[each.key].name
  member  = google_service_account.ci["${each.value.env}/apply"].member
}

# Service Account User lets the apply account deploy a Cloud Run service as a
# runtime account. It is bound on each runtime account by name (D-037): a
# condition on the account's name prefix did not match, and the form of the
# name that IAM uses in conditions is not documented.
resource "google_service_account_iam_member" "ci_apply_runtime_user" {
  for_each = local.sgtm_runtime_account_bindings

  service_account_id = "projects/${local.env_projects[each.value.env]}/serviceAccounts/${each.value.name}@${local.env_projects[each.value.env]}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.ci["${each.value.env}/apply"].member
}

# Exports the live GTM container versions into gtm/ (D-010). It has no GCP
# roles. It is added as a read-only user in each GTM container by hand. The
# binding matches runs on main, not one workflow, so any workflow on main can
# use it. That is accepted: it can only read the GTM containers, and getting
# a workflow onto main takes a pull request.
resource "google_service_account" "gtm_export" {
  project      = google_project.this["admin"].project_id
  account_id   = "gtm-export"
  display_name = "GTM container export (read-only)"

  depends_on = [google_project_service.this]
}

resource "google_service_account_iam_member" "gtm_export_wif" {
  service_account_id = google_service_account.gtm_export.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/repo:${local.github.owner}@${local.github.owner_id}/${local.github.repo}@${local.github.repository_id}:ref:refs/heads/main"
}
