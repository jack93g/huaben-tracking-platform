# Handoff: TP-2 changes in the app repo

For a session working in `jack93g/project-chinese-story-generator`. Written 2026-10-04, updated 2026-10-06.

**Goal:** the frontend loads web GTM, asks for consent, creates the tracking identifiers, and pushes `page_view` to the dataLayer. The API tells the frontend the user's ID and accepts three new request headers.

**Read first, in `jack93g/huaben-tracking-platform`:**
- `docs/epic-mvp.md`, section 2 (the ticket, also issue #4)
- `docs/tracking-spec.md` and `contract/events.yaml` (the fields and their meaning)
- `docs/decisions.md`, D-020, D-021, D-027, D-028, D-029

## State on 2026-10-06

- **GTM:** container `GTM-KF33X5LB`, with a `dev` Environment that has a published version.
- **Cookiebot:** loaded by its tag in GTM, on Consent Initialization. The `localhost` aliases work, and the banner shows on `localhost:3000` with a TEST watermark.
- **API:** the user's ID on `/auth/me` and `/auth/login`, and the three CORS headers, are committed and pushed on the app's `dev` branch. **Not yet on `main`, so not deployed.**
- **Frontend:** the GTM snippet is in the working tree on `dev`, uncommitted, and `frontend/.env.local` has the three GTM values. It was written from the tracking repo's session and hasn't been reviewed in the app repo.
- **Nothing else of the frontend work exists yet.**

## Merge order and constraints

The work doesn't have to merge all at once. The GitHub Pages build has no container ID, so GTM doesn't load in prod. Without GTM there's no Cookiebot, consent is never reported, and it counts as denied: no identity cookies, no `page_view`. Everything below can reach prod and stay dormant, with one exception.

**Constraint 1: deploy the API change before any frontend that sends the headers.**
- `X-Tracking-Consent` goes on every API call, whatever the consent state. It's the one piece that isn't dormant.
- If the API change and that frontend change reach `main` in the same merge, both deploys start together. The frontend can finish first, and every API call then fails its CORS preflight until the backend catches up.
- So merge the API change to `main` and let it deploy first, in a merge of its own.

**Constraint 2: the container ID in `deploy-frontend.yml` is the go-live switch.**
- Adding `NEXT_PUBLIC_GTM_ID` there makes the real site load the Live container, and so the Cookiebot banner.
- It isn't part of TP-2, whose deliverable is in dev only. It's a change of its own, made last, and only when:
  - the version on Live in GTM has been checked and is the one wanted;
  - the GA4 tag isn't in that version, or is paused, because it mustn't send until TP-3 (D-027);
  - the privacy notice covers Cookiebot and the two cookies.

**Order.** Each piece depends on the one before. They can merge one at a time or grouped, in this order:

| | Piece | Depends on |
|---|---|---|
| 1 | GTM snippet | Nothing |
| 2 | Consent module | 1, to have Cookiebot on the page |
| 3 | Identity module | 2 |
| 4 | API headers | 3, and the API change deployed (constraint 1) |
| 5 | `page_view` | 2 and 3, and the user's ID in the session state |

## Frontend, in merge order

**1. GTM snippet** (already in the working tree; review it, don't rewrite it)
- Files: `frontend/lib/gtm.ts`, `frontend/lib/gtm.test.ts`, `frontend/app/components/google-tag-manager.tsx`, two lines in `frontend/app/layout.tsx`, and a block in `frontend/.env.example`.
- Google's `<head>` snippet, written by hand as an inline `next/script` in a small component, loaded in `frontend/app/layout.tsx`. No `@next/third-parties` dependency.
- Leave out the `<noscript>` iframe. The app doesn't work without JavaScript, and the iframe would load regardless of consent.
- Build variables:

  | Variable | Value | Set where |
  |---|---|---|
  | `NEXT_PUBLIC_GTM_ID` | `GTM-KF33X5LB` | `frontend/.env.local`, and the app repo's Actions variables |
  | `NEXT_PUBLIC_GTM_AUTH` | The `dev` Environment's `gtm_auth` | `frontend/.env.local` only |
  | `NEXT_PUBLIC_GTM_PREVIEW` | `env-3` | `frontend/.env.local` only |

- With the two environment values set, the snippet's URL ends `&gtm_auth=…&gtm_preview=…&gtm_cookies_win=x`. With them unset, it loads Live. With no container ID, it loads nothing, so tests and forks run without GTM.
- The `gtm_auth` value stays out of both repos. It lets anyone load the `dev` environment's unpublished tags.
- The three names are documented in `frontend/.env.example`.
- **Don't add `NEXT_PUBLIC_GTM_ID` to `.github/workflows/deploy-frontend.yml` in this work.** That's the go-live switch; see "Merge order and constraints".
- `frontend/AGENTS.md` says this Next.js version differs from older ones. Read the bundled docs before using `next/script` or a router hook.

**2. Consent module** (new, e.g. `frontend/lib/tracking/consent.ts`)
- Follows Cookiebot's events on `window`; it doesn't read once at startup. Cookiebot's script is loaded by GTM, after the app starts.
- Exposes `granted` or `denied`, and lets other code subscribe. Until Cookiebot reports, the answer is `denied`.
- Keep Cookiebot behind this one module, so the platform can be swapped.

**3. Identity module** (new, e.g. `frontend/lib/tracking/identity.ts`)
- `anonymous_id`: UUID v4, in the cookie `huaben_anonymous_id`, 13 months from first set, not extended on later visits.
- `session_id`: UUID v4, in the cookie `huaben_session_id`, which ends after 30 minutes without activity.
- Cookie attributes: `Path=/`, `SameSite=Lax`, and in prod `Secure` with `Domain=huaben.app`, so `www.huaben.app` shares them. Host-only on `localhost`.
- Created only when consent is granted. Deleted when it's withdrawn.
- Logout leaves both cookies alone; only `user_id` is cleared, through the session state. No change to `frontend/app/components/logout-button.tsx` is needed for identity. (Changed 2026-10-06: D-020 first replaced `anonymous_id` at logout.)

**4. API headers** (needs the API change deployed first)
- `apiFetch` in `frontend/lib/api.ts` is the one place every call goes through. Add the headers there:
  - `X-Tracking-Consent`: always, `granted` or `denied`;
  - `X-Anonymous-Id` and `X-Session-Id`: only with consent.

**5. `page_view`**
- First, `CurrentUser` and the `signed-in` state carry the user's ID: `frontend/lib/api.ts`, `frontend/lib/session.ts`, `frontend/app/components/login-gate.tsx`.
- The push's shape, also in the tracking spec:

  ```js
  window.dataLayer.push({
    event: "page_view",
    event_id: "<uuid v4>",
    schema_version: "1.0.0",
    event_timestamp: "2026-10-04T09:30:00.123Z",
    user_id: "42",              // undefined when nobody is logged in
    anonymous_id: "<uuid v4>",
    session_id: "<uuid v4>",
    page_location: "https://huaben.app/story?id=12",
    page_path: "/story",
    page_title: "…",
    page_referrer: "https://huaben.app/stories",   // undefined when there is none
  });
  ```

- Every push carries every key, with `undefined` for a value that's absent. GTM merges pushes, so a key left out would keep its old value, e.g. `user_id` after a logout.
- `source` and `consent` aren't pushed: sGTM sets `source`, and consent comes from Consent Mode (D-027).
- `page_referrer` is `document.referrer` on first load and the previous page's URL on a route change.
- Pushed on first load and on every client-side route change.
- Only with consent granted. When consent changes to granted, push one for the page being shown.
- The first one after a load waits for two things: Cookiebot reporting the consent state, and the session check. Without the first it would be dropped as denied, even for a returning visitor. The second makes it carry `user_id` when someone is logged in; on the login screen it has none.
- `page_location` and `page_referrer` keep only allowlisted query parameters: `id` on `/story`. Everything else, such as `fresh`, is dropped.
- `schema_version` is a constant in the tracking code, currently `1.0.0`.

## Done when

- GTM Preview on `localhost` shows `page_view` on load and on each route change, with the fields above.
- A returning visitor who accepted gets identifiers and a `page_view` on first load. A new visitor gets them on accepting, without a reload.
- With consent denied or not given: no identity cookies, no `page_view`, and `X-Tracking-Consent: denied` on API calls.
- After a logout, `anonymous_id` and `session_id` are unchanged, and the next `page_view` has no `user_id`.
- The Cookiebot banner doesn't flash and disappear on first load. If it does, the fallback is in D-029.

## Not in scope

- The GA4 tag going live and the connection to sGTM (TP-3).
- The API reading or storing the headers, and `user_id` on generation requests (TP-5).
- A privacy notice. D-021 and D-029 need one before the app is opened to the public.
