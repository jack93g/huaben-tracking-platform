"""Tests for the GTM export script, against a fake Tag Manager API."""

import io
import json
import urllib.error

import pytest

import export_gtm


def not_found():
    return urllib.error.HTTPError("url", 404, "Not Found", {}, io.BytesIO(b"{}"))


def fake_api(containers, versions, pages=None):
    """A fetch function over fixed data. `versions` maps a container path to a version."""

    def fetch(token, path, params=None):
        assert token == "token"
        if path == "accounts":
            return {"account": [{"path": "accounts/1"}]}
        if path == "accounts/1/containers":
            if pages and not (params or {}).get("pageToken"):
                return {"container": containers[:1], "nextPageToken": "next"}
            if pages:
                return {"container": containers[1:]}
            return {"container": containers}
        if path.endswith("/versions:live"):
            version = versions[path.removesuffix("/versions:live")]
            if version is None:
                raise not_found()
            return version
        raise AssertionError(f"unexpected path {path}")

    return fetch


WEB = {"path": "accounts/1/containers/10", "publicId": "GTM-WEB1"}
SERVER = {"path": "accounts/1/containers/20", "publicId": "GTM-SRV1"}


def version(container_id, **extra):
    return {
        "accountId": "1",
        "path": f"accounts/1/containers/{container_id}/versions/3",
        "tagManagerUrl": "https://tagmanager.google.com/#/versions/accounts/1/",
        "fingerprint": "123",
        "containerVersionId": "3",
        "container": {"accountId": "1", "publicId": f"GTM-{container_id}"},
        "tag": [{"accountId": "1", "name": "GA4", "path": "x", "type": "gaawe"}],
        **extra,
    }


def test_writes_one_scrubbed_file_per_container(tmp_path):
    fetch = fake_api(
        [WEB, SERVER],
        {WEB["path"]: version(10), SERVER["path"]: version(20)},
    )

    written = export_gtm.export("token", tmp_path, fetch=fetch)

    assert written == ["GTM-SRV1.json", "GTM-WEB1.json"]
    data = json.loads((tmp_path / "GTM-WEB1.json").read_text())
    assert data["containerVersionId"] == "3"
    assert data["tag"] == [{"name": "GA4", "type": "gaawe"}]
    text = (tmp_path / "GTM-WEB1.json").read_text()
    for dropped in ("accountId", "tagManagerUrl", "fingerprint", "accounts/1"):
        assert dropped not in text


def test_output_is_stable_and_ends_with_a_newline(tmp_path):
    fetch = fake_api([WEB], {WEB["path"]: version(10)})

    export_gtm.export("token", tmp_path, fetch=fetch)
    first = (tmp_path / "GTM-WEB1.json").read_text()
    export_gtm.export("token", tmp_path, fetch=fetch)

    assert first == (tmp_path / "GTM-WEB1.json").read_text()
    assert first.endswith("}\n")


def test_a_container_without_a_live_version_is_skipped(tmp_path):
    fetch = fake_api([WEB, SERVER], {WEB["path"]: version(10), SERVER["path"]: None})

    assert export_gtm.export("token", tmp_path, fetch=fetch) == ["GTM-WEB1.json"]


def test_follows_pages_of_containers(tmp_path):
    fetch = fake_api(
        [WEB, SERVER],
        {WEB["path"]: version(10), SERVER["path"]: version(20)},
        pages=True,
    )

    assert export_gtm.export("token", tmp_path, fetch=fetch) == ["GTM-SRV1.json", "GTM-WEB1.json"]


@pytest.mark.parametrize("public_id", ["../x", "GTM-a", "", "GTM-1/../2"])
def test_refuses_a_public_id_that_is_not_one(tmp_path, public_id):
    container = {"path": "accounts/1/containers/10", "publicId": public_id}
    fetch = fake_api([container], {container["path"]: version(10)})

    with pytest.raises(ValueError):
        export_gtm.export("token", tmp_path, fetch=fetch)
    assert list(tmp_path.iterdir()) == []


def test_other_http_errors_are_not_swallowed(tmp_path):
    def fetch(token, path, params=None):
        if path == "accounts":
            return {"account": [{"path": "accounts/1"}]}
        if path == "accounts/1/containers":
            return {"container": [WEB]}
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, io.BytesIO(b"{}"))

    with pytest.raises(urllib.error.HTTPError):
        export_gtm.export("token", tmp_path, fetch=fetch)


def test_main_fails_when_it_sees_no_containers(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GTM_ACCESS_TOKEN", "token")
    monkeypatch.setattr(export_gtm, "get", lambda token, path, params=None: {})

    assert export_gtm.main(["export_gtm.py", str(tmp_path)]) == 1
    assert "No containers were exported" in capsys.readouterr().err


def test_main_needs_a_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GTM_ACCESS_TOKEN", raising=False)

    assert export_gtm.main(["export_gtm.py", str(tmp_path)]) == 2


def test_error_bodies_lose_long_numbers_before_they_are_logged(tmp_path, monkeypatch, capsys):
    body = (
        b'{"error": {"message": "No access to accounts/6295841021 in project 1234567890123 '
        b'for someone@example.com"}}'
    )

    def denied(token, path, params=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, io.BytesIO(body))

    monkeypatch.setenv("GTM_ACCESS_TOKEN", "token")
    monkeypatch.setattr(export_gtm, "get", denied)

    assert export_gtm.main(["export_gtm.py", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "403" in err
    assert "6295841021" not in err and "1234567890123" not in err
    assert "<id>" in err
    assert "someone@example.com" not in err and "<email>" in err
