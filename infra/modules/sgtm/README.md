# sGTM module

Server-side GTM on Cloud Run for one environment (D-031): a tagging service that receives events, and a preview service for GTM's debug interface. Both run Google's image and read the container's config from Secret Manager.

## What it creates

- The Cloud Run and Secret Manager APIs.
- Two runtime service accounts, `sgtm-tagging` and `sgtm-preview`. The CI apply accounts can only act as the accounts listed in the bootstrap (`sgtm_runtime_accounts` in `infra/bootstrap/ci.tf`, D-037), so a new or renamed account needs a change and a local apply there first.
- The secret `sgtm-container-config`, **without a value**, replicated only in the environment's region. Both runtime accounts can read it.
- A log exclusion for the services' Cloud Run request logs, which hold the client IP, user agent, and URL (D-038).
- The two Cloud Run services, only when `deploy_services` is true.

## Bringing up a new environment

1. **First apply, with `deploy_services = false`.** It creates everything except the services, which can't start without a secret version.
2. **Create the environment's server container in GTM** (target "Server", "Manually provision tagging server") and copy its **Container Config** string. It holds an auth key: keep it in a password manager, never in this repository, an issue, or a chat.
3. **Add the value to the secret.** Copy the string from your password manager and run the line below. It reads the clipboard, so the string stays out of your shell history, and `tr` removes a trailing newline, which could break the config. Then clear the clipboard with `pbcopy < /dev/null`:

   ```bash
   pbpaste | tr -d '\n' | gcloud secrets versions add sgtm-container-config --project=<project id> --data-file=-
   ```

4. **Turn the services on** in a pull request that sets `deploy_services = true` in the environment's module call. The tagging service reads the preview service's URL from it.
5. **Domain and DNS** (D-032, D-035). The domain mapping is created with the services when `tracking_domain` is set. The certificate only issues once the DNS record exists, and the record is added by hand:
   1. Read the records from the apply's output (`sgtm_dns_records`, in the job log or `terraform output`), or from `gcloud beta run domain-mappings describe --domain <domain> --region <region> --project <project id>`, under `resourceRecords`.
   2. Add them in Cloudflare as **DNS-only** records, never proxied, or Google can't issue the certificate. If CAA records are ever added, they must allow `pki.goog` and `letsencrypt.org`.
   3. Wait. The certificate usually takes about 15 minutes and can take up to 24 hours.
   4. Check it, with the domain's own name:

      ```bash
      dig +short <domain>
      curl -s https://<domain>/healthy
      ```

      The second should print `ok`. A TLS error means the certificate isn't ready yet.

   The identity that creates the mapping must be a verified owner of the domain in Search Console. For CI that is the environment's apply account.

## Changing things later

- **Rotating the config.** Add a new secret version. Instances read the secret when they start, so a running instance keeps the old value until it is replaced. To apply it at once, deploy a new revision.
- **Updating Google's image.** The `:stable` tag moves, but Cloud Run resolves it when a revision is created. A running revision keeps its image until a new revision is deployed. Google advises restarting the servers from time to time to pick up updates.
- **The preview service has to be public** (`preview_invoker_iam_disabled = true`, D-036). GTM's debugger runs in the browser and can't send an IAM token, so a private service gives a 403 and Preview mode doesn't work. It is the module's default.
- **Destroying.** `deletion_protection` defaults to true. The dev environment sets it to false so it can be rebuilt.
