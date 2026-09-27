locals {
  region = "europe-west1"
  domain = "huaben.app"

  admin_project_id = "huaben-tracking-platform-admin"
  env_projects = {
    dev  = "huaben-tracking-platform-dev"
    prod = "huaben-tracking-platform-prod"
  }
  all_projects = merge(local.env_projects, { admin = local.admin_project_id })

  groups = {
    org_admins      = "group:gcp-organization-admins@${local.domain}"
    billing_admins  = "group:gcp-billing-admins@${local.domain}"
    platform_admins = "group:gcp-platform-admins@${local.domain}"
  }

  # GitHub identifiers are matched by numeric ID, which can't be reused after a
  # rename or deletion, unlike owner/repo names.
  github = {
    repository    = "jack93g/huaben-tracking-platform"
    repository_id = "1388971082"
    owner_id      = "76908040"
  }

  state_bucket = "huaben-tracking-platform-tfstate"
}
