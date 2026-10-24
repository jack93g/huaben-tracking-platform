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
  description = "Google's sGTM image. The :stable tag moves by design, but Cloud Run resolves it when a revision is created, so an existing revision keeps its image until a new one is deployed. Google advises restarting the servers periodically to pick up updates."
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
    Whether the preview service is public. It has to be: GTM's debugger runs in the
    browser and cannot send an IAM token, so a private service gives Preview mode a 403
    (D-036). Set false only to see that for yourself.
  EOT
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Whether Terraform refuses to destroy the Cloud Run services. Keep true in prod; dev sets false so it can be rebuilt."
  type        = bool
  default     = true
}

variable "tracking_domain" {
  description = <<-EOT
    The domain the tagging service is served on, e.g. tracking.dev.huaben.app, or null
    for none. The mapping is created with the services (D-032). The DNS record it needs
    is added by hand in Cloudflare (D-035), and the apply identity must be a verified
    owner of the domain in Search Console.
  EOT
  type        = string
  default     = null
}
