# The dev environment. Applied by CI only (D-013, D-015): plans run on every
# pull request, and applies need the `dev` GitHub Environment.
# Resources are added by later tickets.

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
  tracking_domain     = "tracking.dev.huaben.app"
  deletion_protection = false
}

# The analytics dataset (D-019, D-040). Only the tagging service writes to it.
module "bigquery" {
  source = "../../modules/bigquery"

  project_id = local.project_id
  location   = local.region
  writers = {
    sgtm_tagging = module.sgtm.runtime_service_accounts["tagging"]
  }
}

output "sgtm_dns_records" {
  description = "The records to add in Cloudflare for the tracking domain (DNS-only)."
  value       = module.sgtm.dns_records
}
