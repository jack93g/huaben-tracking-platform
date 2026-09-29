# The bootstrap's own state lives in the bucket it creates (state.tf).
# First run only: rename this file to backend.tf.off, apply with local state,
# rename it back, then `terraform init -migrate-state`. See README.md.
terraform {
  backend "gcs" {
    bucket = "huaben-tracking-platform-tfstate"
    prefix = "bootstrap"
  }
}
