# Set in terraform.tfvars, which is gitignored. The repo is public, so these
# IDs stay out of it (see terraform.tfvars.example).

variable "org_id" {
  description = "Numeric ID of the huaben.app organization."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the projects are linked to (XXXXXX-XXXXXX-XXXXXX)."
  type        = string
}
