terraform {
  required_version = "~> 1.16.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.4"
    }
  }
}

provider "google" {
  region = local.region

  # Bill API calls for organization-level resources (org policies, Essential
  # Contacts) to the admin project, where those APIs are enabled.
  billing_project       = local.admin_project_id
  user_project_override = true
}
