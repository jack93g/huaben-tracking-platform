# Folder, projects, organization policies, and group access (D-002, D-003).

resource "google_folder" "huaben" {
  display_name        = "huaben"
  parent              = "organizations/${var.org_id}"
  deletion_protection = true
}

# The three projects were created by hand and moved into the organization
# before the bootstrap existed. They're imported, then moved into the folder.
import {
  for_each = local.all_projects
  to       = google_project.this[each.key]
  id       = each.value
}

resource "google_project" "this" {
  for_each = local.all_projects

  name            = each.value
  project_id      = each.value
  folder_id       = google_folder.huaben.folder_id
  billing_account = var.billing_account_id
  deletion_policy = "PREVENT"

  # Moving a project into the folder needs Project Creator on the folder.
  depends_on = [google_folder_iam_member.org_admins]
}

resource "google_org_policy_policy" "resource_locations" {
  name   = "${google_folder.huaben.name}/policies/gcp.resourceLocations"
  parent = google_folder.huaben.name

  spec {
    rules {
      values {
        allowed_values = ["in:eu-locations"]
      }
    }
  }
}

# Organization roles for the admin group. The first three were granted by
# hand so this bootstrap can run (README.md); declaring them here records them.
# These are additive: bindings not listed here are left alone.
resource "google_organization_iam_member" "org_admins" {
  for_each = toset([
    "roles/resourcemanager.organizationAdmin",
    "roles/resourcemanager.projectMover",
    "roles/resourcemanager.folderAdmin",
    "roles/orgpolicy.policyAdmin",
    "roles/essentialcontacts.admin",
  ])

  org_id = var.org_id
  role   = each.value
  member = local.groups.org_admins
}

resource "google_folder_iam_member" "org_admins" {
  folder = google_folder.huaben.name
  role   = "roles/resourcemanager.projectCreator"
  member = local.groups.org_admins
}

# Owner on the folder is inherited by every project in it.
resource "google_folder_iam_member" "platform_admins" {
  folder = google_folder.huaben.name
  role   = "roles/owner"
  member = local.groups.platform_admins
}

resource "google_billing_account_iam_member" "billing_admins" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.admin"
  member             = local.groups.billing_admins
}

# huaben.app has no mail server; this address is forwarded by Cloudflare
# Email Routing (D-008).
resource "google_essential_contacts_contact" "notifications" {
  parent                              = "organizations/${var.org_id}"
  email                               = "gcp-notifications@${local.domain}"
  language_tag                        = "en-GB"
  notification_category_subscriptions = ["ALL"]
}
