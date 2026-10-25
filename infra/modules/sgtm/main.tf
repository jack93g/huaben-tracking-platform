# Server-side GTM on Cloud Run for one environment (D-031): a tagging service
# that receives events, and a preview service for GTM's debug interface. Both
# run Google's image and read the container's config from Secret Manager.

locals {
  secret_id = "sgtm-container-config"

  # The services that log requests we do not want to keep (D-038).
  service_names = ["sgtm-tagging", "sgtm-preview"]

  # The apply accounts may only act as the accounts listed in the bootstrap
  # (sgtm_runtime_accounts, D-037): a new or renamed account needs a change
  # and a local apply there before a service can run as it.
  runtime_accounts = {
    tagging = "sgtm-tagging"
    preview = "sgtm-preview"
  }
}

resource "google_project_service" "this" {
  for_each = toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_service_account" "runtime" {
  for_each = local.runtime_accounts

  project      = var.project_id
  account_id   = each.value
  display_name = "sGTM ${each.key} service"
}

# The container config holds an auth key, so Terraform makes the secret and
# who can read it, and never its value: a person adds that (D-034).
# Replication is pinned to one EU location. The automatic kind would store the
# secret outside the locations the organization allows.
resource "google_secret_manager_secret" "container_config" {
  project   = var.project_id
  secret_id = local.secret_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.this]
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each = google_service_account.runtime

  project   = var.project_id
  secret_id = google_secret_manager_secret.container_config.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

# Cloud Run's request log records the client IP, user agent, and full URL.
# The platform has no use for them, so they are never stored (D-038).
# Application logs are kept.
resource "google_logging_project_exclusion" "request_logs" {
  project     = var.project_id
  name        = "sgtm-request-logs"
  description = "Cloud Run request logs of the sGTM services hold the client IP, user agent, and URL (D-038)."
  filter = join(" AND ", [
    "resource.type=\"cloud_run_revision\"",
    "log_id(\"run.googleapis.com/requests\")",
    "resource.labels.service_name=(${join(" OR ", [for name in local.service_names : "\"${name}\""])})",
  ])
}

# Exactly one instance at most: Google says the preview server must not scale
# beyond one. It scales to zero when nobody is previewing (D-033).
resource "google_cloud_run_v2_service" "preview" {
  count = var.deploy_services ? 1 : 0

  project  = var.project_id
  name     = "sgtm-preview"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  invoker_iam_disabled = var.preview_invoker_iam_disabled
  deletion_protection  = var.deletion_protection

  template {
    service_account = google_service_account.runtime["preview"].email
    timeout         = "60s"

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.image

      env {
        name  = "RUN_AS_PREVIEW_SERVER"
        value = "true"
      }
      env {
        name = "CONTAINER_CONFIG"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.container_config.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # CPU only while handling a request (D-033).
        cpu_idle = true
      }

      startup_probe {
        http_get {
          path = "/healthy"
        }
      }
    }
  }

  depends_on = [
    google_project_service.this,
    google_secret_manager_secret_iam_member.runtime_access,
  ]
}

resource "google_cloud_run_v2_service" "tagging" {
  count = var.deploy_services ? 1 : 0

  project  = var.project_id
  name     = "sgtm-tagging"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # Browsers send no Google credentials, and the organization policy forbids
  # allUsers, so the invoker check is off (D-036). The protection is in the
  # container: the mapping and the backend client's secret.
  invoker_iam_disabled = true
  deletion_protection  = var.deletion_protection

  template {
    service_account = google_service_account.runtime["tagging"].email
    timeout         = "60s"

    # Zero minimum: cold starts are accepted (D-033).
    scaling {
      min_instance_count = 0
      max_instance_count = var.tagging_max_instances
    }

    containers {
      image = var.image

      env {
        name = "CONTAINER_CONFIG"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.container_config.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "PREVIEW_SERVER_URL"
        value = google_cloud_run_v2_service.preview[0].uri
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # CPU only while handling a request (D-033). Tested in TP-4: inserts still complete.
        cpu_idle = true
      }

      startup_probe {
        http_get {
          path = "/healthy"
        }
      }
    }
  }

  depends_on = [
    google_project_service.this,
    google_secret_manager_secret_iam_member.runtime_access,
  ]
}

# The tracking domain for the tagging service (D-032). Cloud Run issues the
# certificate once the DNS record exists. The record is added by hand in
# Cloudflare, DNS-only, never proxied (D-035): see the dns_records output.
resource "google_cloud_run_domain_mapping" "tagging" {
  count = var.deploy_services && var.tracking_domain != null ? 1 : 0

  name     = var.tracking_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.tagging[0].name
  }
}
