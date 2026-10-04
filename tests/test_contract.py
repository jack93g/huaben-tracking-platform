"""Tests for the contract generator and the models it generates."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import generate_contract
from huaben_tracking_contract import (
    SCHEMA_VERSION,
    Consent,
    Login,
    LoginProperties,
    QuizSubmitted,
    QuizSubmittedProperties,
    StoryGenerated,
    StoryGeneratedProperties,
)


def story_properties(**overrides):
    properties = {
        "story_id": "7",
        "generation_request_id": "9",
        "target_hsk_level": 3,
        "target_word_count": 300,
        "target_vocabulary_count": 10,
        "has_topic": False,
        "provider": "openrouter",
        "model": "example-model",
        "attempt_count": 1,
    }
    return StoryGeneratedProperties(**(properties | overrides))


def story_generated(**overrides):
    fields = {
        "event_timestamp": datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc),
        "consent": Consent(analytics_storage="denied"),
        "properties": story_properties(),
    }
    return StoryGenerated(**(fields | overrides))


def test_generated_files_match_the_contract():
    contract = generate_contract.load_contract()
    for path, content in generate_contract.render_all(contract).items():
        assert path.read_text() == content, f"{path} is out of date"


def test_bigquery_schema_has_every_common_field_in_order():
    contract = generate_contract.load_contract()
    schema = json.loads(generate_contract.BIGQUERY_SCHEMA.read_text())
    assert [column["name"] for column in schema] == [
        field["name"] for field in contract["common_fields"]
    ]


def test_backend_event_serialises_to_the_contract_shape():
    payload = story_generated(user_id="42").model_dump(mode="json")

    assert payload["event_name"] == "story_generated"
    assert payload["source"] == "backend"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["event_timestamp"] == "2026-10-04T09:30:00Z"
    # sGTM sets server_timestamp, so the backend must not send it.
    assert "server_timestamp" not in payload


def test_each_event_gets_its_own_event_id():
    assert story_generated().event_id != story_generated().event_id


def test_event_timestamp_has_no_default():
    # The caller must pass the business time; "now" at delivery would be wrong.
    with pytest.raises(ValidationError):
        StoryGenerated(
            consent=Consent(analytics_storage="denied"), properties=story_properties()
        )


def test_event_without_any_identifier_is_valid():
    event = story_generated()
    assert (event.user_id, event.anonymous_id, event.session_id) == (None, None, None)


def test_out_of_range_property_is_rejected():
    with pytest.raises(ValidationError):
        story_properties(target_hsk_level=7)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        story_properties(topic="a free-text topic")


def test_anonymous_id_must_be_a_uuid():
    with pytest.raises(ValidationError):
        story_generated(anonymous_id="not-a-uuid")


def test_login_and_quiz_submitted_validate():
    common = {
        "event_timestamp": datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc),
        "user_id": "42",
        "consent": Consent(analytics_storage="granted"),
    }
    login = Login(properties=LoginProperties(method="password"), **common)
    quiz = QuizSubmitted(
        properties=QuizSubmittedProperties(
            story_id="7", quiz_attempt_id="3", question_count=5, correct_count=4
        ),
        **common,
    )
    assert login.event_name == "login"
    assert quiz.event_name == "quiz_submitted"
    with pytest.raises(ValidationError):
        LoginProperties(method="magic_link")


def test_every_backend_event_has_a_model():
    import huaben_tracking_contract

    contract = generate_contract.load_contract()
    for name, event in contract["events"].items():
        model = generate_contract.class_name(name)
        assert hasattr(huaben_tracking_contract, model) == (event["source"] == "backend")


@pytest.mark.parametrize("field", ["event_id", "anonymous_id", "session_id"])
@pytest.mark.parametrize(
    "value",
    [
        "c232ab00-9414-11ec-b3c8-9f6bdeced846",  # v1
        "0192e4a1-7b5c-7def-8a3b-1234567890ab",  # v7
    ],
)
def test_uuids_must_be_version_4(field, value):
    with pytest.raises(ValidationError):
        story_generated(**{field: value})


def test_unknown_format_is_refused():
    contract = generate_contract.load_contract()
    contract["common_fields"][0]["format"] = "uuid"
    with pytest.raises(generate_contract.ContractError):
        generate_contract.validate(contract)


@pytest.mark.parametrize(
    "broken",
    [
        None,
        {"version": "1.0.0"},
        {"version": "1.0.0", "common_fields": [], "events": {"login": None}},
        {"version": "1.0.0", "common_fields": ["event_id"], "events": {}},
    ],
)
def test_malformed_contract_gives_a_contract_error(broken):
    with pytest.raises(generate_contract.ContractError):
        generate_contract.validate(broken)


def test_second_json_common_field_is_refused():
    contract = generate_contract.load_contract()
    extra = dict(contract["common_fields"][-1], name="context")
    contract["common_fields"].append(extra)
    with pytest.raises(generate_contract.ContractError):
        generate_contract.validate(contract)


def test_hand_written_package_files_exist():
    package = generate_contract.PYTHON_MODELS.parent
    assert (package / "__init__.py").is_file()
    # Without this marker, type checkers ignore the package's type hints.
    assert (package / "py.typed").is_file()


def test_invalid_contract_is_refused():
    contract = generate_contract.load_contract()
    contract["events"]["StoryGenerated"] = contract["events"]["story_generated"]
    with pytest.raises(generate_contract.ContractError):
        generate_contract.validate(contract)
