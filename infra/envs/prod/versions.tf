terraform {
  required_version = "~> 1.16.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.4"
    }
  }

  backend "gcs" {
    bucket = "huaben-tracking-platform-tfstate"
    prefix = "envs/prod"
  }
}

provider "google" {
  project = local.project_id
  region  = local.region
}
