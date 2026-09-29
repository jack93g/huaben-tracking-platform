# The prod environment. Applied by CI only (D-013, D-015): plans run on every
# pull request, and applies need the `prod` GitHub Environment.
# Resources are added by later tickets (sGTM in TP-3, BigQuery in TP-4, ...).

locals {
  project_id = "huaben-tracking-platform-prod"
  region     = "europe-west1"
}
