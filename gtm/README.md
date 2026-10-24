# GTM exports

One file per GTM container, named by its public ID: the live version, as JSON.

- **Don't edit these by hand.** They are written by the `GTM export` workflow (`.github/workflows/gtm-export.yml`, `scripts/export_gtm.py`) and show what was published in the GTM UI (D-010).
- **How a change gets here.** The workflow runs daily and on demand. When a live version differs from `main`, it pushes a branch `gtm-export/<hash>`, says so in its run summary with a link, and opens an issue that mentions the owner. A person reads the diff and opens the pull request (D-039). Publishing still happens in the GTM UI.
- **What's left out.** The GTM account's numeric ID, resource paths, URLs, and fingerprints are removed, because this repository is public. Unpublished workspace changes aren't exported, only the live version. A version published only to the web container's `dev` Environment (D-028) isn't exported either, until it is promoted to Live.
- **Read the diff before opening the pull request.** Anything saved in a container's tags, variables, or templates ends up in a public repository. The backend's secret is stored only as a hash in the server container (D-024). A real secret in a variable would show up here.
- A container that is deleted in GTM keeps its file here until it is removed by hand.
