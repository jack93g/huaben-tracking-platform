"""Pydantic models for the backend's events.

Generated from contract/events.yaml by scripts/generate_contract.py. Do not edit.
"""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Consent(_Model):
    """Consent Mode v2 signals at the time of the event."""

    analytics_storage: Literal["granted", "denied"] = Field(description="Consent for analytics identifiers. Unknown counts as denied.")
    ad_storage: Literal["granted", "denied"] | None = Field(default=None, description="Consent for advertising identifiers. Null when not collected.")
    ad_user_data: Literal["granted", "denied"] | None = Field(default=None, description="Consent to send user data to advertising platforms. Null when not collected.")
    ad_personalization: Literal["granted", "denied"] | None = Field(default=None, description="Consent for personalised advertising. Null when not collected.")


class StoryGeneratedProperties(_Model):
    """Properties of `story_generated`."""

    story_id: str = Field(description="The app's ID of the story that was created.")
    generation_request_id: str = Field(description="The app's ID of the generation request.")
    target_hsk_level: int = Field(ge=1, le=6, description="HSK level the story was requested at.")
    target_word_count: int = Field(ge=1, description="Requested length of the story, in words.")
    target_vocabulary_count: int = Field(ge=1, description="Number of vocabulary items the story was asked to use.")
    has_topic: bool = Field(description="Whether the user gave a topic. The topic text itself is never sent.")
    provider: str = Field(description="The AI provider that generated the story.")
    model: str = Field(description="The model that generated the story.")
    prompt_version: str | None = Field(default=None, description="Version of the prompt template.")
    attempt_count: int = Field(ge=1, description="Number of attempts the request took, including the successful one.")
    total_tokens: int | None = Field(default=None, ge=0, description="Prompt plus completion tokens used by the successful attempt.")
    latency_ms: int | None = Field(default=None, ge=0, description="Time the provider took for the successful attempt, in milliseconds.")


class StoryGenerated(_Model):
    """The worker finished generating a story successfully. Failed generations send nothing."""

    event_id: UUID = Field(default_factory=uuid4)
    event_name: Literal["story_generated"] = "story_generated"
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    source: Literal["backend"] = "backend"
    event_timestamp: AwareDatetime = Field(description="When the generation completed, the same value as the request's completed_at in the app. Not when it was requested or delivered.")
    user_id: str | None = Field(default=None, description="The app's user ID as a string. Null when nobody is logged in.")
    anonymous_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser. Null without analytics consent.")
    session_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser session. Null without analytics consent.")
    consent: Consent
    properties: StoryGeneratedProperties


class LoginProperties(_Model):
    """Properties of `login`."""

    method: Literal["password"] = Field(description="How the user logged in. GA4's standard parameter for login.")


class Login(_Model):
    """A user logged in successfully. Failed attempts send nothing."""

    event_id: UUID = Field(default_factory=uuid4)
    event_name: Literal["login"] = "login"
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    source: Literal["backend"] = "backend"
    event_timestamp: AwareDatetime = Field(description="When the login succeeded.")
    user_id: str | None = Field(default=None, description="The app's user ID as a string. Null when nobody is logged in.")
    anonymous_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser. Null without analytics consent.")
    session_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser session. Null without analytics consent.")
    consent: Consent
    properties: LoginProperties


class QuizSubmittedProperties(_Model):
    """Properties of `quiz_submitted`."""

    story_id: str = Field(description="The app's ID of the story the quiz belongs to.")
    quiz_attempt_id: str = Field(description="The app's ID of the quiz attempt.")
    question_count: int = Field(ge=1, description="Number of questions in the quiz.")
    correct_count: int = Field(ge=0, description="Number of questions answered correctly. The answers themselves are never sent.")


class QuizSubmitted(_Model):
    """A user submitted their answers to a story's quiz and the attempt was saved."""

    event_id: UUID = Field(default_factory=uuid4)
    event_name: Literal["quiz_submitted"] = "quiz_submitted"
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    source: Literal["backend"] = "backend"
    event_timestamp: AwareDatetime = Field(description="When the quiz attempt was saved.")
    user_id: str | None = Field(default=None, description="The app's user ID as a string. Null when nobody is logged in.")
    anonymous_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser. Null without analytics consent.")
    session_id: UUID | None = Field(default=None, description="UUID v4 identifying the browser session. Null without analytics consent.")
    consent: Consent
    properties: QuizSubmittedProperties


__all__ = [
    "Consent",
    "Login",
    "LoginProperties",
    "QuizSubmitted",
    "QuizSubmittedProperties",
    "SCHEMA_VERSION",
    "StoryGenerated",
    "StoryGeneratedProperties",
]
