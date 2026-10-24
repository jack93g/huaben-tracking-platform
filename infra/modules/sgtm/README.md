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
5. **Domain and DNS.** The domain mapping and the DNS records are added in a later change (D-032, D-035), and this section will list the exact records.

## Changing things later

- **Rotating the config.** Add a new secret version. Instances read the secret when they start, so a running instance keeps the old value until it is replaced. To apply it at once, deploy a new revision.
- **Updating Google's image.** The `:stable` tag moves, but Cloud Run resolves it when a revision is created. A running revision keeps its image until a new revision is deployed. Google advises restarting the servers from time to time to pick up updates.
- **The preview service is private by default** (`preview_invoker_iam_disabled = false`, D-036). GTM's Preview mode may need it public: set the variable to `true` and amend D-036 with the result.
- **Destroying.** `deletion_protection` defaults to true. The dev environment sets it to false so it can be rebuilt.
