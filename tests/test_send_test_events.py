"""Tests for the pieces of the test-event script that don't need a network (TP-4)."""

import urllib.parse

import send_test_events as script

BASE = {"base_url": "https://tracking.example", "measurement_id": "G-TEST"}


def params(case, **kwargs):
    url = script.build_url(case, "run1", **BASE, **kwargs)
    assert url.startswith("https://tracking.example/g/collect?")
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


def case(name):
    return next(c for c in script.CASES if c.name == name)


def test_a_valid_event_uses_the_keys_the_spec_lists():
    sent = params(case("valid"))
    assert sent["en"] == "page_view"
    for key in ("evnid", "uid", "ep.schema_version", "ep.event_timestamp", "ep.anonymous_id", "ep.app_session_id"):
        assert key in sent
    assert sent["dp"] == "/tp4-test/run1/valid"
    assert sent["gcs"] == script.CONSENT_GRANTED


def test_identifiers_are_uuid_v4_and_new_each_time():
    first, second = params(case("valid")), params(case("valid"))
    assert first["evnid"] != second["evnid"]
    assert len(first["evnid"]) == 36 and first["evnid"][14] == "4"


def test_a_case_can_remove_a_parameter():
    sent = params(case("valid-anonymous"))
    assert "uid" not in sent and "ep.anonymous_id" not in sent and "ep.app_session_id" not in sent


def test_a_case_can_override_a_parameter():
    assert params(case("bad-event-id"))["evnid"] == "12345"
    assert params(case("consent-denied"))["gcs"] == script.CONSENT_DENIED
    assert params(case("backend-event-name"))["en"] == "story_generated"


def test_a_burst_event_is_named_for_its_index():
    assert params(case("valid"), burst_index=7)["dp"] == "/tp4-test/run1/burst-7"


def test_google_details_are_sent_so_the_check_can_look_for_them():
    sent = params(case("valid"))
    assert sent["uip"] == script.FAKE_IP and sent["cid"] == script.FAKE_CLIENT_ID


def test_outcome_reads_stored_then_rejected_then_absent():
    stored, rejected = {"a": {}}, {"b": {"reason": "invalid_event_id"}}
    assert script.outcome("a", stored, rejected) == "stored"
    assert script.outcome("b", stored, rejected) == "rejected:invalid_event_id"
    assert script.outcome("c", stored, rejected) == "absent"


def test_leaks_names_google_details_found_in_a_stored_row():
    assert script.leaks([{"whole_row": "{}"}]) == []
    row = {"whole_row": f'{{"x": "{script.FAKE_IP}", "y": "{script.FAKE_CLIENT_ID}"}}'}
    assert script.leaks([row]) == ["IP address", "client ID"]


def test_only_dev_runs_without_being_asked(monkeypatch, capsys):
    for argv in (
        ["--project", "huaben-tracking-platform-prod"],
        ["--url", "https://tracking.huaben.app"],
        ["--url", "https://some-other-host.example"],
    ):
        monkeypatch.setattr("sys.argv", ["send_test_events.py", "--no-check", *argv])
        assert script.main() == 2
        assert "Refusing" in capsys.readouterr().err


def test_every_case_expects_something_the_template_can_produce():
    allowed = ("stored", "absent", "rejected:")
    assert all(c.expect.startswith(allowed) for c in script.CASES)
    assert len({c.name for c in script.CASES}) == len(script.CASES)


def test_the_page_location_uses_the_site_origin():
    sent = params(case("valid"), site_origin="https://huaben.app")
    assert sent["dl"] == "https://huaben.app/tp4-test/run1/valid"


def test_a_case_sends_the_site_origin_unless_it_is_about_another():
    assert script.request_origin(case("valid"), "https://huaben.app") == "https://huaben.app"
    assert script.request_origin(case("foreign-origin"), "https://huaben.app") == "https://evil.example"


def test_only_selects_cases_by_name():
    assert [c.name for c in script.select_cases("valid, bad-event-id")] == ["valid", "bad-event-id"]
    assert script.select_cases(None) == script.CASES


def test_only_refuses_a_name_that_is_not_a_case():
    try:
        script.select_cases("valid,nope")
    except ValueError as error:
        assert "nope" in str(error)
    else:
        raise AssertionError("expected a ValueError")
