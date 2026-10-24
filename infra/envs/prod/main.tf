# The prod environment. Applied by CI only (D-013, D-015): plans run on every
# pull request, and applies need the `prod` GitHub Environment.
# Resources are added by later tickets (BigQuery in TP-4, ...).

locals {
  project_id = "huaben-tracking-platform-prod"
  region     = "europe-west1"
}

# Server-side GTM (D-031). The bootstrap lists this environment's runtime
# accounts (sgtm_runtime_accounts in infra/bootstrap/ci.tf, D-037) and a person
# has added the container config's value to the secret (D-034). Deletion
# protection stays on.
module "sgtm" {
  source = "../../modules/sgtm"

  project_id      = local.project_id
  region          = local.region
  deploy_services = true
  tracking_domain = "tracking.huaben.app"
}

output "sgtm_dns_records" {
  description = "The records to add in Cloudflare for the tracking domain (DNS-only)."
  value       = module.sgtm.dns_records
}
