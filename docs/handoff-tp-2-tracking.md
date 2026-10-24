# Handoff: TP-2 results from the app repo

For a session working in `jack93g/huaben-tracking-platform`. Written 2026-10-06 from the app repo's session, as the reply to `docs/handoff-tp-2-app.md`.

**What this is for:** the app side of TP-2 is built. This lists what was built, where it differs from or adds to the spec, and what the docs in this repo need to say as a result. Nothing in this repo was edited from the app session.

## State on 2026-10-06

- **API:** merged and deployed (app PR #85). `/auth/me` and `/auth/login` return `{"id", "username"}` with `id` as a string. Production's CORS preflight accepts `X-Anonymous-Id`, `X-Session-Id` and `X-Tracking-Consent`; checked against `api.huaben.app`.
- **Frontend:** all five pieces are on the app's `dev` branch and in app PR #86, which is **open, not merged**. Last commit `1b5c771`.
- **Production:** unchanged by #86 except that every API call will carry `X-Tracking-Consent: denied`. No container ID is in `deploy-frontend.yml`, so GTM, Cookiebot, the cookies and `page_view` stay dormant.
- **Local:** verified on `localhost:3000` against container `GTM-KF33X5LB`, Environment `env-3`.

## Where the code is, in the app repo

| Piece | File |
|---|---|
| GTM snippet | `frontend/lib/gtm.ts`, `frontend/app/components/google-tag-manager.tsx` |
| Consent | `frontend/lib/tracking/consent.ts` |
| Identity cookies | `frontend/lib/tracking/identity.ts` |
| API headers | `frontend/lib/tracking/headers.ts`, used by `apiFetch` in `frontend/lib/api.ts` |
| `page_view` and the dataLayer | `frontend/lib/tracking/page-view.ts` |
| What runs it | `frontend/app/components/tracking.tsx`, mounted in `frontend/app/layout.tsx` |

## Changes to make in this repo

### 1. `docs/tracking-spec.md`, "The frontend's dataLayer": two pushes that aren't events

The spec says the frontend pushes one flat object per event. The app now also makes two pushes with no `event` key. Both exist because GTM keeps a value until a later push replaces it, and neither a logout nor a withdrawal changes the page, so no `page_view` follows to do that.

| When | Push |
|---|---|
| Nobody is logged in any more (logout, or the session expires) | `{ user_id: undefined }` |
| Consent is withdrawn | `{ user_id: undefined, anonymous_id: undefined, session_id: undefined }` |

- Each is pushed only if a `page_view` put those values in the dataLayer during this page load, and only once.
- The first is pushed whatever the consent state, since it carries no data.
- Confirmed in the browser that GTM's data model returns `undefined` for the keys afterwards.

### 2. `docs/tracking-spec.md`: details of `page_view` the spec doesn't state

- **Fragments are dropped** from `page_location` and `page_referrer`, as well as non-allowlisted query parameters. The contract only mentions the query string.
- **Another site's referrer loses its whole query string.** The allowlist only applies to the app's own origin.
- **`page_title` can be `undefined`.** On a route change Next.js removes the `<title>` and re-adds it about a millisecond later. The push waits for it, for up to one second, then goes without. The contract already has `page_title` as optional. In practice every page has the same title, "话本 Huaben".
- **`event_id` and `event_timestamp` are fixed when the page is shown.** The identifiers and the title are read when the push is made, which can be a moment later.
- **A waiting `page_view` is sent first, without a title, if the visitor navigates.** It is dropped if consent is withdrawn while it waits.
- **Logging in or out on the same URL sends no `page_view`.** The login form replaces the page content without a route change. The next one comes with the next navigation.
- **One `page_view` per page shown,** where a page is its tracked URL. `/story?id=12&fresh=1` becoming `/story?id=12` is the same page. The exception is the next point.
- **Consent withdrawn and granted again on the same page sends a second `page_view`** for it, with the new identifiers. This follows D-029 ("changes to granted ... sends the `page_view` for the page being shown").

### 3. `docs/decisions.md`, D-029 or a new entry: what "granted" means

- **Granted means Cookiebot's Statistics category**, alone. It is the category Cookiebot's tag maps to `analytics_storage` (D-021). Marketing and Preferences are ignored.
- **The module tells "denied" from "not known yet".** Both read as `denied` to callers, but the identity cookies are only deleted once Cookiebot has reported a refusal. Otherwise every page load, which starts as unknown, would delete a returning visitor's `anonymous_id`.
- **How it follows Cookiebot:** it listens for `CookiebotOnConsentReady`, which fires for a new choice, a withdrawal and a returning visitor. It also reads `Cookiebot.consent.statistics` once when first used, because that event can fire before the app's listener is attached. It doesn't use `Cookiebot.hasResponse`, which goes back to `false` while the banner is reopened.

### 4. `docs/tracking-spec.md`, "Identity": two things for TP-5

- **The first API call of each page load says `denied`.** The session check (`/auth/me`) runs before Cookiebot reports, so it carries `X-Tracking-Consent: denied` and no identifiers, even for a visitor who accepted earlier. Later calls carry the real state. This matters if TP-5 ever records something from that call.
- **Every API call and every `page_view` counts as session activity** and renews the 30-minute cookie. A page polling for a story's generation status keeps the session alive while it polls.

### 5. Documents that now disagree

- **`docs/handoff-tp-2-app.md`, "State":** it says the API change is not on `main` and that only the snippet exists in the frontend. Both are out of date; see the state above.
- **`docs/epic-mvp.md`, section 2, step 3** says to add the GTM build variables to `deploy-frontend.yml`. The handoff says not to in TP-2, because the container ID is the go-live switch. The app followed the handoff, so the ticket should say the same.
- **`docs/decisions.md`, D-028** says `gtm_auth` and `gtm_preview` "aren't secrets". The handoff says `gtm_auth` stays out of both repos because it loads the `dev` Environment's unpublished tags. The app's `.env.example` follows the handoff. One of the two should change.

### 6. Outside the docs

- **Cookiebot's cookie declaration:** `huaben_anonymous_id` and `huaben_session_id` belong under Statistics, to match what the code treats as consent.
- **Privacy notice:** still needed before go-live (D-021, D-029). It must cover Cookiebot's own cookie and the two above.

## Verified, and not

**Verified in the browser on localhost:**
- GTM loads once; the Cookiebot banner appears and stays; Consent Mode defaults to denied.
- A returning visitor who accepted gets identifiers and a `page_view` on first load. A new visitor gets them on accepting, without a reload.
- `page_view` on load and on each route change, with all 11 keys and the right referrer; `fresh` and other parameters dropped; fragment dropped.
- Denied or not given: no identity cookies, no `page_view`.
- Withdrawing deletes both cookies and clears the three keys in GTM's data model, without a reload.
- The preflight for the three headers passes locally and in production.

**Verified by the user in GTM Preview, logged in:**
- The first `page_view` carries `user_id`.
- After logout, the next `page_view` has no `user_id`.

**Covered by unit tests only:**
- The values of the three headers on API calls.
- `anonymous_id` and `session_id` staying the same across a logout.
- The `{ user_id: undefined }` push at logout.
- The second `page_view` when consent is granted again on the same page.

## Still to do for TP-2, in GTM

From the ticket's steps 7 and 8; none of it is app work:

- dataLayer variables for the contract's fields, and the hostname lookup variables.
- The GA4 tag for `page_view`, with its consent settings, the automatic page view turned off, and "page changes based on browser history events" turned off. It stays unpublished until TP-3.
- A trigger on the `page_view` custom event. The pushes without an `event` key can't fire it.

## The go-live switch

Unchanged from the first handoff: adding `NEXT_PUBLIC_GTM_ID` to the app's `deploy-frontend.yml` is a change of its own, made last, once the Live version in GTM is checked, the GA4 tag is absent or paused, and the privacy notice exists.
