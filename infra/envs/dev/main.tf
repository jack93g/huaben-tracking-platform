# The dev environment. Applied by CI only (D-013, D-015): plans run on every
# pull request, and applies need the `dev` GitHub Environment.
# Resources are added by later tickets (BigQuery in TP-4, ...).

locals {
  project_id = "huaben-tracking-platform-dev"
  region     = "europe-west1"
}

# Server-side GTM (D-031). The services need a version of the container config
# secret, which a person added by hand (D-034).
module "sgtm" {
  source = "../../modules/sgtm"

  project_id          = local.project_id
  region              = local.region
  deploy_services     = true
  deletion_protection = false
}
