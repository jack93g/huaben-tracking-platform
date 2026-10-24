"""Export the live version of every GTM container the caller can see, as JSON.

Used by the GTM export workflow (D-010, D-039). It writes one file per
container, named by the container's public ID, e.g. gtm/GTM-XXXXXXX.json.

    GTM_ACCESS_TOKEN=... python scripts/export_gtm.py gtm

The token needs the tagmanager.readonly scope. The containers it exports are
those the account was added to as a user, so no account or container IDs are
kept in this repository.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://tagmanager.googleapis.com/tagmanager/v2"
PUBLIC_ID = re.compile(r"^GTM-[A-Z0-9]+$")

# Dropped from the export. The first three embed the GTM account's numeric ID,
# which this public repository doesn't publish. The fingerprint changes with
# every save and says nothing the content doesn't.
DROPPED_KEYS = {"accountId", "path", "tagManagerUrl", "fingerprint"}


def get(token, path, params=None):
    """GET one resource from the Tag Manager API and return its JSON."""
    url = f"{API}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def list_all(fetch, token, path, key):
    """Return every item of a paged list resource."""
    items = []
    page_token = None
    while True:
        params = {"pageToken": page_token} if page_token else None
        page = fetch(token, path, params)
        items.extend(page.get(key, []))
        page_token = page.get("nextPageToken")
        if not page_token:
            return items


def redact(text):
    """Make an API error body fit for a public log: a long number may be an ID."""
    return re.sub(r"\d{6,}", "<id>", text)[:300]


def scrub(value):
    """Return value without the dropped keys, at every depth."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in DROPPED_KEYS}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def live_versions(fetch, token):
    """Yield (container, live version) for every container with a live version."""
    for account in list_all(fetch, token, "accounts", "account"):
        containers = list_all(fetch, token, f"{account['path']}/containers", "container")
        for container in containers:
            try:
                version = fetch(token, f"{container['path']}/versions:live")
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    print(f"{container.get('publicId', '?')}: no live version, skipped")
                    continue
                raise
            yield container, version


def export(token, out_dir, fetch=None):
    """Write each live version to out_dir and return the file names written."""
    fetch = fetch or get
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for container, version in live_versions(fetch, token):
        public_id = container.get("publicId", "")
        if not PUBLIC_ID.match(public_id):
            raise ValueError(f"Unexpected container public ID: {public_id!r}")
        text = json.dumps(scrub(version), indent=2, sort_keys=True, ensure_ascii=False)
        (out_dir / f"{public_id}.json").write_text(text + "\n", encoding="utf-8")
        written.append(f"{public_id}.json")
        print(f"{public_id}: live version {version.get('containerVersionId', '?')}")
    return sorted(written)


def main(argv):
    if len(argv) != 2:
        print("usage: export_gtm.py <output directory>", file=sys.stderr)
        return 2
    token = os.environ.get("GTM_ACCESS_TOKEN")
    if not token:
        print("GTM_ACCESS_TOKEN is not set", file=sys.stderr)
        return 2
    try:
        written = export(token, argv[1])
    except urllib.error.HTTPError as error:
        # The body says which API or permission is the problem. It holds no token,
        # but it can name an account or project by number, and the log is public.
        body = redact(error.read().decode(errors="replace"))
        print(f"Tag Manager API error {error.code}: {body}", file=sys.stderr)
        return 1
    if not written:
        print(
            "No containers were exported. Either the export account is not a user of any "
            "container, or no container has a published live version.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
