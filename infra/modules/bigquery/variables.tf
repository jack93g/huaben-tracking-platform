variable "project_id" {
  description = "The environment's GCP project."
  type        = string
}

variable "location" {
  description = "Location of the dataset. Must be an EU location (org policy). A dataset's location can't be changed later."
  type        = string
}

variable "writers" {
  description = <<-EOT
    Service accounts that may write to the analytics dataset, keyed by a name that is known
    at plan time, valued by the account's email. They get access to this dataset only, and
    to nothing else in the project.
  EOT
  type        = map(string)
  default     = {}
}

variable "events_retention_days" {
  description = "How long raw events are kept, by partition expiration. 14 months is about 426 days (D-022)."
  type        = number
  default     = 426
}

variable "rejected_retention_days" {
  description = "How long rejected events are kept. They hold raw payloads, so the limit is short (D-022, D-040)."
  type        = number
  default     = 30
}

variable "deletion_protection" {
  description = "Whether Terraform refuses to destroy the tables, and so to replace them, which would lose their data (D-019)."
  type        = bool
  default     = true
}
