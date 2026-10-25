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
   | Accesses BigQuery | Allow `analytics.events` and `analytics.events_rejected` in the environment's project (`huaben-tracking-platform-dev` or `-prod`). The tag names its project, so the permission must list it: it is the one setting to change after importing the template into the other container |
   | Reads event data | Any key |
   | Reads the request: headers | Specific: `origin` and `referer` |
   | Reads the request: query parameters | Off |
   | Reads the request: body, path, remote IP address | Off. The IP address is never needed, and never stored |
   | Logs to console | Always |

3. Create a constant variable `GCP project ID` with the environment's project ID, and `Allowed origins` as below. Then create two tags from the template:

   | Tag | Path | Trigger | Project ID | Allowed origins |
   |---|---|---|---|---|
   | Huaben events: browser | Browser events | Every event (see the note on the trigger below) | `{{GCP project ID}}` | `{{Allowed origins}}`: `http://localhost:3000` in dev, `https://huaben.app,https://www.huaben.app` in prod |
   | Huaben events: backend | Backend events | Every event from the backend's custom client (D-024) | `{{GCP project ID}}` | n/a |

4. The project ID and the allowed origins differ per environment, so keep them in constant variables and don't overwrite them when importing one container into the other.
5. **The trigger:** a Custom trigger needs an event-name condition, so use *Event Name matches RegEx* `.+`. That also fires for the backend's client once TP-5 adds it, where the browser tag would wrongly reject backend events. Limit it to the GA4 client before then (a client-name or request-path condition).
