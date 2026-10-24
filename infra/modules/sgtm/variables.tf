variable "project_id" {
  description = "The environment's GCP project."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and the secret's only replica. Must be an EU location (org policy)."
  type        = string
}

variable "deploy_services" {
  description = <<-EOT
    Whether to create the Cloud Run services. Keep false in a fresh environment: the
    services need a version of the container config secret, which a person adds by
    hand after the first apply (D-034). Set to true afterwards, in a pull request.
  EOT
  type        = bool
  default     = false
}

variable "image" {
  description = "Google's sGTM image. The :stable tag is moving by design; instances pick up a new image when they start."
  type        = string
  default     = "gcr.io/cloud-tagging-10302018/gtm-cloud-image:stable"
}

variable "tagging_max_instances" {
  description = "Upper limit of the tagging service. It bounds the worst-case cost (D-033)."
  type        = number
  default     = 3
}

variable "preview_invoker_iam_disabled" {
  description = <<-EOT
    Whether the preview service is public. False keeps it private, as D-036 prefers.
    GTM's Preview mode may not work then, because the browser cannot send an IAM
    token. If it does not, set this to true and amend D-036.
  EOT
  type        = bool
  default     = false
}
