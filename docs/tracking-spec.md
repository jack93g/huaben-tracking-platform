# Tracking specification

**Contract version 1.0.0**

This document describes what Huaben tracks and how. The machine-readable version is [contract/events.yaml](../contract/events.yaml): where the two disagree, the contract is right and this document needs fixing. The reasons behind each rule are in [decisions.md](decisions.md), D-017 to D-026.

```
Frontend ── page_view ────────┐
                              ▼
Backend ── story_generated ─► sGTM ─► analytics.events ─► dbt ─► fct_events
```

## Events

| Event | Source | When it's sent | Its `event_timestamp` |
|---|---|---|---|
| `page_view` | frontend | A page is shown: on first load and on every client-side route change | When the page was shown, by the browser's clock |
| `story_generated` | backend | The worker finishes generating a story successfully | When the generation completed: the request's `completed_at` in the app |
| `login` | backend | A user logs in successfully | When the login succeeded |
| `quiz_submitted` | backend | A user submits a story's quiz and the attempt is saved | When the attempt was saved |

Each event's properties are listed in the contract.

- Only `page_view` and `story_generated` are needed for the MVP. `login` and `quiz_submitted` are defined so the app can send them when TP-5 decides to.
- **Failures aren't events.** A failed login or a failed generation sends nothing. Failed logins are security data, kept in the app, and the attempted username is never sent.
- **Content isn't sent.** `story_generated` carries no topic text, and `quiz_submitted` carries counts, not answers.
- `login` is the event that first puts a `user_id` and an `anonymous_id` on the same row, which is what stitching relies on.

**Naming (D-017)**
- Names are snake_case and at most 40 characters.
- An event that really is a GA4 event uses GA4's name: `page_view`, `login`, `sign_up`.
- Every other event is a custom event named `object_action` in the past tense: `story_generated`, `quiz_submitted`.
- Custom events never borrow another event's meaning. `story_generated` is not a purchase and carries no e-commerce parameters.

**One source per event.** Each event is sent by the frontend or by the backend, never both. An event is sent by the backend when the backend is the only place that knows it really happened.

## Common fields

Every event has these fields. They're the columns of `analytics.events`.

| Field | Type | Required | Set by | Meaning |
|---|---|---|---|---|
| `event_id` | string (UUID v4) | yes | source | Generated once where the event happens. Retries reuse it, so it's the deduplication key |
| `event_name` | string | yes | source | One of the events above |
| `schema_version` | string | yes | source | The contract version the sender was built against |
| `source` | string | yes | source | `frontend` or `backend` |
| `event_timestamp` | timestamp | yes | source | When the event happened |
| `server_timestamp` | timestamp | yes | sGTM | When sGTM received the event |
| `user_id` | string | no | source | The app's user ID. Null when nobody is logged in |
| `anonymous_id` | string (UUID v4) | no | source | Identifies the browser. Null without analytics consent |
| `session_id` | string (UUID v4) | no | source | Identifies the browser session. Null without analytics consent |
| `consent` | record | yes | source | The Consent Mode v2 signals when the event happened |
| `properties` | JSON | yes | source | The event's own properties. `{}` when it has none |

**Timestamps**
- `event_timestamp` is the business time: the moment the thing the event describes became true. Each event defines which moment that is, in the table above and in the contract's `event_time`.
- It's set once, when the event is created. Retries and delayed delivery never change it.
- For `story_generated` it's the completion time, not the time the story was requested and not the time the event was delivered. Request time would belong to a separate event.
- For a frontend event it comes from the browser's clock, which can be wrong. `source` says which kind of clock produced it.
- `server_timestamp` is set by sGTM when the request arrives, for both sources. A sender never sets it.
- Both are UTC. On the wire they're RFC 3339 strings, e.g. `2026-10-04T09:30:00.123Z`.
- A large gap between the two is normal for backend events that waited in the outbox. That gap is the delivery delay.

**Consent record**
- `analytics_storage` is always present: `granted` or `denied`. Unknown counts as `denied`.
- `ad_storage`, `ad_user_data`, and `ad_personalization` are null until a tag needs them.

## Identity (D-020)

| Identifier | Who creates it | Where it lives | Lifetime |
|---|---|---|---|
| `user_id` | The app | The login session, on the server | The account's |
| `anonymous_id` | The frontend | A first-party cookie on `huaben.app` | 13 months from first set, not extended on later visits |
| `session_id` | The frontend | A first-party cookie on `huaben.app` | Ends after 30 minutes without activity |

- `user_id` is the user's ID in the app's database, sent as a string. A username or email address is never sent.
- The frontend only creates `anonymous_id` and `session_id` when analytics consent is granted.
- **An event with no identifiers at all is valid.** A story generated through the shared API key has no user and no browser, so all three are null. It still counts in totals; it just can't be attributed.
- **Logout** replaces `anonymous_id` and starts a new session, so the next person on a shared device doesn't inherit the previous one's history.

**Reaching the API.** The frontend adds three headers to every API call:

| Header | Value |
|---|---|
| `X-Anonymous-Id` | The `anonymous_id`, only with consent |
| `X-Session-Id` | The `session_id`, only with consent |
| `X-Tracking-Consent` | `granted` or `denied` |

- The API treats the headers as untrusted. A value that isn't a UUID v4 is dropped.
- A missing `X-Tracking-Consent` header means `denied`.
- `user_id` always comes from the login session, never from a header.
- An event produced later by the worker uses the values captured when the request was made. They're stored with the request.

**Stitching.** Raw events are never rewritten. dbt applies these rules when it builds its models:
- An event with its own `user_id` keeps it.
- An event without one gets the first `user_id` seen *after* it on the same `anonymous_id`, if that's within 30 days. It never gets an earlier one.
- One user on several devices: every `anonymous_id` maps to that user.

## Consent (D-021)

This section hasn't been reviewed by a lawyer.

| | Consent granted | Consent denied or not yet given |
|---|---|---|
| Frontend identifiers | Created and stored | Not created |
| Frontend events | Sent | Not sent |
| Backend events | Sent with `user_id`, `anonymous_id`, and `session_id` | Sent with `user_id` only |

- Backend events record something the user did in the app, which the app's own database already holds. They're kept in Huaben's own warehouse under legitimate interest, and the privacy notice must say so.
- Nothing is forwarded to a third party (GA4, Meta) unless the event's consent state is `granted`.
- Withdrawing consent deletes both cookies and stops the identity headers.
- **A worker event uses the consent state from when the request was made.** It's stored with the request, together with the identifiers. Withdrawing or granting consent while a story is being generated doesn't change that story's event.

## Sending frontend events to sGTM (D-027)

- Web GTM sends browser events with the GA4 tag, pointed at the tracking domain. In sGTM the built-in GA4 client claims them.
- The contract's own fields travel as event parameters: `event_id`, `schema_version`, `event_timestamp`, `anonymous_id`, and `session_id`. `user_id` uses GA4's own field.
- sGTM maps the GA4-shaped event to the contract's row before storing it, and builds the `consent` record from the request's Consent Mode state.
- This path takes no secret, so anyone can post to it. The mapping therefore always sets `source` to `frontend` and refuses the names of backend events.
- Consent Mode runs in basic mode: the tag is blocked until `analytics_storage` is granted, so nothing is sent when consent is denied.
- Google's tag sets its own `_ga` cookies once consent is granted. Its `client_id` isn't stored; the identity is the one described above.

## Sending backend events to sGTM (D-024)

```
POST /events
Content-Type: application/json
X-Tracking-Secret: <secret>

{ "event_id": "…", "event_name": "story_generated", … }
```

- One event per request, in exactly the contract's shape, without `server_timestamp`.
- A custom sGTM client claims the request. It answers `401` for a wrong secret and `400` for a body that doesn't match the contract.
- The server container stores only the SHA-256 hash of the secret, because the container is exported to this public repository. The secret itself lives only in the app's runtime secrets.
- The secret must be 32 bytes from a cryptographically secure random generator, e.g. `openssl rand -base64 32`, never a value a person chose. The hash is public, so a guessable secret could be found by brute force.
- Each environment has its own secret.
- sGTM answers `200` once it has accepted the event, whether or not the BigQuery insert later succeeds.

## Storage (D-019)

- `analytics.events` has one typed column per common field, plus `properties` as JSON. Its schema is generated: [contract/generated/bigquery/events.schema.json](../contract/generated/bigquery/events.schema.json).
- The table is partitioned by day on `server_timestamp` and clustered by `event_name`.
- Adding an event or a property doesn't change the table. dbt extracts typed values from `properties`.

## Retention (D-022)

| Data | Kept for |
|---|---|
| Raw `analytics.events` | 14 months |
| Event-level dbt models | 14 months |
| Aggregates with no identifiers | No limit |
| `events_rejected` | 30 days |
| Cloud Logging | 30 days |
| Outbox rows already sent (in the app) | 7 days |

A user's data can also be erased on request, by deleting their rows by `user_id` from the raw and derived tables.

## Late and duplicate events (D-023)

- Delivery from the backend is at-least-once, so the same `event_id` can arrive twice.
- The outbox retries an event for up to 48 hours, then marks it dead.
- dbt removes duplicates by `event_id`, looking back 3 days on `server_timestamp`.
- An event is never rejected for being late.

## Changing the contract (D-018)

1. Edit `contract/events.yaml` and bump `version`:
   - **minor** for an additive change, such as a new event or a new optional property;
   - **major** for a breaking change, such as removing or renaming a property, or making one required.
2. Run `python scripts/generate_contract.py` and commit the generated files with the change. The `pre-commit` check fails if they're out of date.
3. Update this document.
4. After merging, tag the commit `contract-v<version>`. The app pins that tag to install the Pydantic models (see [contract/python/README.md](../contract/python/README.md)).

Common fields can only be added, never removed or retyped: Terraform would replace the table and lose its data.
