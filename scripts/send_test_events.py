"""Send test events to an sGTM tagging service and check what BigQuery stored (TP-4).

    python scripts/send_test_events.py                 # dev: the cases, then the check
    python scripts/send_test_events.py --burst 30      # also send 30 valid events at once
    python scripts/send_test_events.py --no-check      # send only; skip the BigQuery check

It posts GA4-shaped requests to the browser path, the way Google's tag does (D-027), and
then queries BigQuery with the `bq` CLI for the rows each case should have produced. Every
event's page path starts with /tp4-test/<run id>/, which is how its rows are found. Test
rows stay in dev's tables until their partitions expire.

The backend path can't be tested here: it needs the custom client (TP-5).
Needs `gcloud auth login` for the check. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

DEV_URL = "https://tracking.dev.huaben.app"
DEV_PROJECT = "huaben-tracking-platform-dev"
DEV_ORIGIN = "http://localhost:3000"

# Not real identifiers: the check looks for them in the stored rows, because none of Google's
# own details may be stored.
FAKE_IP = "203.0.113.9"
FAKE_CLIENT_ID = "tp4-test-client-id"

# GA4's consent state: G1, then ad_storage and analytics_storage as 1 (granted) or 0 (denied).
CONSENT_GRANTED = "G101"
CONSENT_DENIED = "G100"


@dataclass
class Case:
    name: str
    why: str
    # "stored", "rejected:<reason>", or "absent" (nothing is stored for it).
    expect: str
    event_name: str = "page_view"
    origin: str | None = DEV_ORIGIN
    consent: str = CONSENT_GRANTED
    # Overrides of the request's parameters. A value of None removes the parameter.
    params: dict[str, str | None] = field(default_factory=dict)


def uuid4() -> str:
    return str(uuid.uuid4())


CASES = [
    Case("valid", "a page_view as the browser sends it", "stored"),
    Case(
        "valid-anonymous",
        "no identifiers at all is still a valid event",
        "stored",
        params={"uid": None, "ep.anonymous_id": None, "ep.app_session_id": None},
    ),
    Case(
        "foreign-origin",
        "an Origin outside the site is logged and not stored (D-041)",
        "absent",
        origin="https://evil.example",
    ),
    Case(
        "backend-event-name",
        "a backend event name on the browser path",
        "rejected:event_not_allowed_on_frontend_path",
        event_name="story_generated",
    ),
    Case("unknown-event", "a name that is not in the contract", "rejected:unknown_event_name", event_name="purchase"),
    Case("bad-event-id", "an event_id that is not a UUID v4", "rejected:invalid_event_id", params={"evnid": "12345"}),
    Case(
        "bad-anonymous-id",
        "an anonymous_id that is not a UUID v4",
        "rejected:invalid_anonymous_id",
        params={"ep.anonymous_id": "abc"},
    ),
    Case(
        "bad-timestamp",
        "an event_timestamp that is not RFC 3339",
        "rejected:invalid_event_timestamp",
        params={"ep.event_timestamp": "yesterday"},
    ),
    Case(
        "bad-version",
        "a schema_version from another major version",
        "rejected:invalid_schema_version",
        params={"ep.schema_version": "2.0.0"},
    ),
    Case(
        "long-title",
        "a string far past the length limit",
        "rejected:invalid_property:page_title",
        params={"dt": "t" * 3000},
    ),
    Case(
        "impossible-date",
        "passes validation but BigQuery refuses it: nothing is stored, and the insert failure is logged",
        "absent",
        params={"ep.event_timestamp": "2026-02-31T08:30:31.000Z"},
    ),
    Case(
        "consent-denied",
        "the browser path stores nothing without analytics consent",
        "rejected:consent_not_granted",
        consent=CONSENT_DENIED,
    ),
]


def build_url(case: Case, run_id: str, *, base_url: str, measurement_id: str, burst_index: int | None = None) -> str:
    name = f"burst-{burst_index}" if burst_index is not None else case.name
    params: dict[str, str | None] = {
        "v": "2",
        "tid": measurement_id,
        "en": case.event_name,
        "gcs": case.consent,
        # Google's own details. None of them may reach BigQuery.
        "cid": FAKE_CLIENT_ID,
        "uip": FAKE_IP,
        "ul": "en-gb",
        "sr": "2560x1440",
        # The contract's fields, under the keys the spec lists (D-027).
        "evnid": uuid4(),
        "uid": "9999",
        "ep.schema_version": "1.0.0",
        "ep.event_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "ep.anonymous_id": uuid4(),
        "ep.app_session_id": uuid4(),
        "dl": f"{DEV_ORIGIN}/tp4-test/{run_id}/{name}",
        "dp": f"/tp4-test/{run_id}/{name}",
        "dt": "tp4 test",
    }
    params.update(case.params)
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    return f"{base_url.rstrip('/')}/g/collect?{query}"


def send(url: str, origin: str | None) -> int:
    headers = {"User-Agent": "tp4-test-events"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url, data=b"", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


# --- Checking -----------------------------------------------------------------


def bq(project: str, sql: str) -> list[dict]:
    result = subprocess.run(
        ["bq", f"--project_id={project}", "query", "--nouse_legacy_sql", "--format=json", sql],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout or "[]")


def stored_rows(project: str, run_id: str) -> dict[str, dict]:
    sql = f"""
      SELECT JSON_VALUE(properties, '$.page_path') AS path, event_name, source,
             consent.analytics_storage AS consent, user_id, anonymous_id, session_id,
             TO_JSON_STRING(t) AS whole_row
      FROM `{project}.analytics.events` AS t
      WHERE server_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 6 HOUR)
        AND JSON_VALUE(properties, '$.page_path') LIKE '/tp4-test/{run_id}/%'
    """
    return {row["path"].rsplit("/", 1)[1]: row for row in bq(project, sql)}


def rejected_rows(project: str, run_id: str) -> dict[str, dict]:
    sql = f"""
      SELECT reason, source, payload, TO_JSON_STRING(t) AS whole_row
      FROM `{project}.analytics.events_rejected` AS t
      WHERE received_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 6 HOUR)
        AND payload LIKE '%/tp4-test/{run_id}/%'
    """
    rows = {}
    for row in bq(project, sql):
        marker = f"/tp4-test/{run_id}/"
        tail = row["payload"].split(marker, 1)[1]
        rows[tail.split('"', 1)[0].split("\\", 1)[0]] = row
    return rows


def outcome(case_name: str, stored: dict, rejected: dict) -> str:
    if case_name in stored:
        return "stored"
    if case_name in rejected:
        return f"rejected:{rejected[case_name]['reason']}"
    return "absent"


def leaks(rows: list[dict]) -> list[str]:
    """Google's own details must not appear anywhere in a stored row."""
    found = []
    for row in rows:
        for secret in (FAKE_IP, FAKE_CLIENT_ID, "2560x1440", "en-gb"):
            if secret in row["whole_row"]:
                found.append(secret)
    return sorted(set(found))


def check(project: str, run_id: str, expected: dict[str, str], burst: int, wait: int) -> bool:
    print(f"\nWaiting for BigQuery (up to {wait}s)...")
    deadline = time.time() + wait
    while True:
        stored, rejected = stored_rows(project, run_id), rejected_rows(project, run_id)
        done = all(
            outcome(name, stored, rejected) == want for name, want in expected.items() if want != "absent"
        ) and sum(1 for name in stored if name.startswith("burst-")) >= burst
        if done or time.time() > deadline:
            break
        time.sleep(10)

    ok = True
    print(f"\n{'case':22} {'expected':48} result")
    for name, want in expected.items():
        got = outcome(name, stored, rejected)
        ok &= got == want
        print(f"{name:22} {want:48} {'ok' if got == want else 'FAILED: ' + got}")

    if "valid" in stored:
        row = stored["valid"]
        checks = {
            "source is frontend": row["source"] == "frontend",
            "consent is granted": row["consent"] == "granted",
            "user_id is kept": row["user_id"] == "9999",
            "session_id is kept": bool(row["session_id"]),
        }
        for label, passed in checks.items():
            ok &= passed
            print(f"valid row: {label:30} {'ok' if passed else 'FAILED'}")

    print(
        "impossible-date: check the log for a bigquery_insert_failed entry:\n"
        "  gcloud logging read 'resource.labels.service_name=\"sgtm-tagging\" AND jsonPayload.type=\"bigquery_insert_failed\"'"
        f" --project={project} --freshness=10m --limit=3"
    )
    found = leaks(list(stored.values()) + list(rejected.values()))
    ok &= not found
    print(f"Google's own details in stored rows: {'none (ok)' if not found else 'FOUND ' + ', '.join(found)}")

    if burst:
        count = sum(1 for name in stored if name.startswith("burst-"))
        ok &= count == burst
        print(f"burst: {count} of {burst} events stored {'(ok)' if count == burst else '(FAILED)'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEV_URL, help="the tagging service (default: dev)")
    parser.add_argument("--project", default=DEV_PROJECT, help="the GCP project to check")
    parser.add_argument("--measurement-id", default="G-TEST000000", help="any value: the GA4 client doesn't check it")
    parser.add_argument("--burst", type=int, default=0, help="also send this many valid events at once")
    parser.add_argument("--wait", type=int, default=90, help="seconds to wait for rows to appear")
    parser.add_argument("--no-check", action="store_true", help="send only; skip the BigQuery check")
    parser.add_argument("--allow-prod", action="store_true", help="allow a prod URL or project")
    args = parser.parse_args()

    if not args.allow_prod and ("prod" in args.project or "//tracking.huaben.app" in args.url):
        print("Refusing to write test events to prod. Pass --allow-prod if you mean it.", file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex[:8]
    print(f"Run {run_id}, sending to {args.url}")
    base = {"base_url": args.url, "measurement_id": args.measurement_id}

    for case in CASES:
        status = send(build_url(case, run_id, **base), case.origin)
        print(f"  {case.name:22} HTTP {status}  {case.why}")

    burst_case = Case("burst", "a valid event in a burst", "stored")
    if args.burst:
        urls = [build_url(burst_case, run_id, burst_index=i, **base) for i in range(args.burst)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(lambda url: send(url, DEV_ORIGIN), urls))
        print(f"  burst: {args.burst} events sent, HTTP statuses {sorted(set(statuses))}")

    if args.no_check:
        print(f"\nFind the rows with page paths starting /tp4-test/{run_id}/")
        return 0
    try:
        return 0 if check(args.project, run_id, {case.name: case.expect for case in CASES}, args.burst, args.wait) else 1
    except RuntimeError as error:
        print(f"\nThe BigQuery check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
