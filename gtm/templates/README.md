# Server container templates

Custom templates for the server containers, kept here so they can be reviewed before they are imported. The live container is still what runs (D-010): what is imported and published shows up in `gtm/GTM-*.json` through the export workflow.

## `huaben-bigquery-events.tpl` (TP-4)

The tag that writes events to BigQuery. It maps an event to the contract's row, validates it, and inserts it into `analytics.events`. An event that fails validation goes to `analytics.events_rejected` instead, with the reason (D-040). A browser event from an `Origin` that isn't allowed is logged and not stored (D-041).

- **Don't edit the contract block** between `BEGIN GENERATED CONTRACT` and `END GENERATED CONTRACT`. `python scripts/generate_contract.py` writes it from `contract/events.yaml`, and the `pre-commit` check fails when it is stale.
- **Tests:** `node --test tests/gtm/` runs the template's code against mocked sGTM APIs, in a `pre-commit` hook and so in CI. Node is pinned in `mise.toml`. GTM's own template tests only run in its UI.
- **Reasons** an event is rejected are short codes, e.g. `unknown_event_name`, `invalid_event_id`, `missing_property:<name>`, `consent_not_granted`. They are listed in the template.

### Importing it

1. In the server container, open **Templates**, then **New** under Tag Templates, and import the file from the menu.
2. Open the template's **Permissions** tab and set these (the editor shows which APIs the code uses):

   | Permission | Setting |
   |---|---|
   | Accesses BigQuery | Tables `analytics.events` and `analytics.events_rejected`. If the project ID field accepts `any`, use it, so the dev and prod containers stay identical; otherwise enter the environment's project ID, and set it again after importing into prod |
   | Reads event data | Any key |
   | Reads HTTP request | Headers `origin` and `referer` only |
   | Logs to console | Always |

3. Create two tags from the template:

   | Tag | Path | Trigger | Allowed origins |
   |---|---|---|---|
   | Huaben events: browser | Browser events | Every event, only when the client is `GA4` | A constant variable, e.g. `https://huaben.app,https://www.huaben.app` in prod, plus `http://localhost:3000` in dev |
   | Huaben events: backend | Backend events | Every event, only when the client is the backend's custom client (D-024) | n/a |

4. The allowed origins differ per environment, so keep them in a constant variable and don't overwrite it when importing one container into the other.
