// Runs the tag template's sandboxed JS against mocked sGTM APIs (TP-4).
//   node --test tests/gtm/
// GTM's own template tests only run in its UI, so this is what lets a change be checked here.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const TEMPLATE = new URL("../../gtm/templates/huaben-bigquery-events.tpl", import.meta.url);
const NOW_MS = 1791_000_000_000;

function sandboxedJs() {
  const text = readFileSync(TEMPLATE, "utf8");
  const start = text.indexOf("___SANDBOXED_JS_FOR_SERVER___") + "___SANDBOXED_JS_FOR_SERVER___".length;
  return text.slice(start, text.indexOf("___NOTES___"));
}

const UUID = "11111111-1111-4111-8111-111111111111";
const UUID2 = "22222222-2222-4222-8222-222222222222";
const UUID3 = "33333333-3333-4333-8333-333333333333";

// What the GA4 client gives the template for a page_view, plus the details
// Google adds, which must never be stored.
const browserEvent = (overrides = {}) => ({
  event_name: "page_view",
  event_id: UUID,
  schema_version: "1.0.0",
  event_timestamp: "2026-10-25T08:30:31.029Z",
  anonymous_id: UUID2,
  app_session_id: UUID3,
  user_id: "2",
  page_location: "http://localhost:3000/",
  page_path: "/",
  page_title: "话本 Huaben",
  client_id: "fake-client-id.1700000000",
  ip_override: "203.0.113.7",
  user_agent: "Mozilla/5.0",
  language: "en-gb",
  screen_resolution: "2560x1440",
  event_location: { country: "XX", region: "YY" },
  ...overrides,
});

const backendEvent = (overrides = {}) => ({
  event_id: UUID,
  event_name: "story_generated",
  schema_version: "1.0.1",
  source: "backend",
  event_timestamp: "2026-10-25T08:30:31Z",
  user_id: "2",
  anonymous_id: null,
  session_id: null,
  consent: { analytics_storage: "denied" },
  properties: {
    story_id: "7",
    generation_request_id: "9",
    target_hsk_level: 3,
    target_word_count: 300,
    target_vocabulary_count: 10,
    has_topic: false,
    provider: "openrouter",
    model: "example-model",
    attempt_count: 1,
  },
  ...overrides,
});

function getType(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

// Runs the template once and returns what it wrote, logged, and reported.
function run({ path = "frontend", event, headers = { origin: "http://localhost:3000" }, consent = true, insertFails = false, allowedOrigins = "http://localhost:3000, https://huaben.app" }) {
  const result = { inserts: [], logs: [], outcome: null };
  const apis = {
    BigQuery: {
      insert(connection, rows, options, onSuccess, onFailure) {
        result.inserts.push({ connection, rows, options });
        insertFails ? onFailure([{ reason: "invalid", message: "forced failure" }]) : onSuccess();
      },
    },
    getAllEventData: () => event,
    getRequestHeader: (name) => headers[name],
    getTimestampMillis: () => NOW_MS,
    getType,
    isConsentGranted: () => consent,
    JSON,
    logToConsole: (message) => result.logs.push(message),
    makeInteger: (value) => parseInt(value, 10),
    makeString: (value) => String(value),
    Math,
    Object,
  };
  const data = {
    path,
    allowedOrigins,
    gtmOnSuccess: () => (result.outcome = "success"),
    gtmOnFailure: () => (result.outcome = "failure"),
  };
  new Function("require", "data", sandboxedJs())((name) => apis[name], data);
  return result;
}

const only = (result, table) => {
  assert.equal(result.inserts.length, 1);
  assert.equal(result.inserts[0].connection.tableId, table);
  assert.equal(result.inserts[0].connection.datasetId, "analytics");
  return result.inserts[0].rows[0];
};

// --- Browser path ------------------------------------------------------------

test("a browser page_view becomes the contract's row", () => {
  const result = run({ event: browserEvent() });
  const row = only(result, "events");
  assert.deepEqual(row, {
    event_id: UUID,
    event_name: "page_view",
    schema_version: "1.0.0",
    source: "frontend",
    event_timestamp: "2026-10-25T08:30:31.029Z",
    server_timestamp: NOW_MS / 1000,
    user_id: "2",
    anonymous_id: UUID2,
    session_id: UUID3,
    consent: { analytics_storage: "granted" },
    properties: { page_location: "http://localhost:3000/", page_path: "/", page_title: "话本 Huaben" },
  });
  assert.equal(result.outcome, "success");
});

test("nothing from Google's own details reaches the row", () => {
  const row = only(run({ event: browserEvent() }), "events");
  const stored = JSON.stringify(row);
  for (const leaked of ["203.0.113.7", "fake-client-id", "Mozilla", "2560x1440", "en-gb", "XX"]) {
    assert.ok(!stored.includes(leaked), `${leaked} was stored`);
  }
  assert.deepEqual(Object.keys(row).sort(), [
    "anonymous_id", "consent", "event_id", "event_name", "event_timestamp", "properties",
    "schema_version", "server_timestamp", "session_id", "source", "user_id",
  ]);
});

test("a browser event without identifiers is valid", () => {
  const event = browserEvent({ user_id: undefined, anonymous_id: undefined, app_session_id: undefined });
  const row = only(run({ event }), "events");
  assert.equal(row.user_id, null);
  assert.equal(row.anonymous_id, null);
  assert.equal(row.session_id, null);
});

test("a numeric user_id is stored as a string", () => {
  assert.equal(only(run({ event: browserEvent({ user_id: 42 }) }), "events").user_id, "42");
});

test("a browser event from the Referer is accepted when there is no Origin", () => {
  const result = run({ event: browserEvent(), headers: { referer: "http://localhost:3000/story?id=1" } });
  assert.equal(only(result, "events").event_id, UUID);
});

test("a foreign Origin is logged and nothing is stored", () => {
  const result = run({ event: browserEvent(), headers: { origin: "https://evil.example" } });
  assert.equal(result.inserts.length, 0);
  assert.match(result.logs[0], /origin_rejected/);
  assert.equal(result.outcome, "success");
});

test("a browser request with neither Origin nor Referer is not stored", () => {
  const result = run({ event: browserEvent(), headers: {} });
  assert.equal(result.inserts.length, 0);
});

test("a prefix of an allowed origin is not allowed", () => {
  const result = run({ event: browserEvent(), headers: { origin: "https://huaben.app.evil.example" } });
  assert.equal(result.inserts.length, 0);
});

// --- Rejects -------------------------------------------------------------------

const rejected = (overrides, options = {}) => {
  const result = run({ event: browserEvent(overrides), ...options });
  return { row: only(result, "events_rejected"), result };
};

test("a backend event name on the browser path is rejected", () => {
  const { row } = rejected({ event_name: "story_generated" });
  assert.equal(row.reason, "event_not_allowed_on_frontend_path");
  assert.equal(row.source, "frontend");
});

test("an unknown event name is rejected", () => {
  assert.equal(rejected({ event_name: "constructor" }).row.reason, "unknown_event_name");
  assert.equal(rejected({ event_name: "purchase" }).row.reason, "unknown_event_name");
});

for (const [name, overrides, reason] of [
  ["a missing event_id", { event_id: undefined }, "invalid_event_id"],
  ["an event_id that is not a UUID v4", { event_id: "12345" }, "invalid_event_id"],
  ["an upper-case UUID", { event_id: "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA" }, "invalid_event_id"],
  ["a UUID of another version", { event_id: "11111111-1111-1111-8111-111111111111" }, "invalid_event_id"],
  ["a major version the contract does not know", { schema_version: "2.0.0" }, "invalid_schema_version"],
  ["a version that is not a version", { schema_version: "latest" }, "invalid_schema_version"],
  ["a timestamp without a time zone", { event_timestamp: "2026-10-25T08:30:31" }, "invalid_event_timestamp"],
  ["a timestamp that is a number", { event_timestamp: 1791000000 }, "invalid_event_timestamp"],
  ["a month of 13", { event_timestamp: "2026-13-25T08:30:31Z" }, "invalid_event_timestamp"],
  ["an anonymous_id that is not a UUID", { anonymous_id: "abc" }, "invalid_anonymous_id"],
  ["a session_id that is not a UUID", { app_session_id: "abc" }, "invalid_session_id"],
  ["a user_id that is too long", { user_id: "9".repeat(65) }, "invalid_user_id"],
  ["a missing page_location", { page_location: undefined }, "missing_property:page_location"],
  ["a page_path that is a number", { page_path: 5 }, "invalid_property:page_path"],
  ["a page_location that is too long", { page_location: "http://localhost:3000/" + "a".repeat(2100) }, "invalid_property:page_location"],
]) {
  test(`${name} is rejected as ${reason}`, () => {
    assert.equal(rejected(overrides).row.reason, reason);
  });
}

test("a browser event without analytics consent is rejected", () => {
  const { row } = rejected({}, { consent: false });
  assert.equal(row.reason, "consent_not_granted");
});

test("a rejected event keeps its raw payload and nothing of Google's details", () => {
  const { row } = rejected({ event_id: "not-a-uuid" });
  assert.equal(row.event_id, "not-a-uuid");
  assert.equal(row.received_at, NOW_MS / 1000);
  assert.equal(row.payload_truncated, false);
  const payload = JSON.parse(row.payload);
  assert.equal(payload.page_path, "/");
  for (const leaked of ["203.0.113.7", "fake-client-id", "Mozilla", "2560x1440"]) {
    assert.ok(!row.payload.includes(leaked), `${leaked} was stored`);
  }
});

test("a long payload is cut and says so", () => {
  const { row } = rejected({ event_id: "x", page_location: "h".repeat(20000) });
  assert.equal(row.payload.length, 8000);
  assert.equal(row.payload_truncated, true);
});

test("an event_id that is not a short string is not stored as one", () => {
  assert.equal(rejected({ event_id: "x".repeat(100) }).row.event_id, null);
  assert.equal(rejected({ event_id: { nested: true } }).row.event_id, null);
});

// --- Backend path --------------------------------------------------------------

test("a backend event is stored as it arrives, with server_timestamp added", () => {
  const result = run({ path: "backend", event: backendEvent(), headers: {} });
  const row = only(result, "events");
  assert.equal(row.source, "backend");
  assert.equal(row.server_timestamp, NOW_MS / 1000);
  assert.deepEqual(row.properties, backendEvent().properties);
  assert.deepEqual(row.consent, { analytics_storage: "denied" });
  assert.equal(result.outcome, "success");
});

test("the backend path does not check the Origin", () => {
  const result = run({ path: "backend", event: backendEvent(), headers: { origin: "https://evil.example" } });
  assert.equal(only(result, "events").event_id, UUID);
});

test("a backend event may have consent denied", () => {
  assert.equal(only(run({ path: "backend", event: backendEvent() }), "events").consent.analytics_storage, "denied");
});

for (const [name, overrides, reason] of [
  ["a browser event name on the backend path", { event_name: "page_view" }, "event_not_allowed_on_backend_path"],
  ["a source that says frontend", { source: "frontend" }, "invalid_source"],
  ["a missing property", { properties: { ...backendEvent().properties, story_id: undefined } }, "missing_property:story_id"],
  ["an HSK level of 7", { properties: { ...backendEvent().properties, target_hsk_level: 7 } }, "invalid_property:target_hsk_level"],
  ["a fractional count", { properties: { ...backendEvent().properties, attempt_count: 1.5 } }, "invalid_property:attempt_count"],
  ["a boolean that is a string", { properties: { ...backendEvent().properties, has_topic: "no" } }, "invalid_property:has_topic"],
  ["a property the contract does not have", { properties: { ...backendEvent().properties, topic: "secret" } }, "unknown_property:topic"],
  ["an inherited object member as a property name", { properties: { ...backendEvent().properties, constructor: "x" } }, "unknown_property:constructor"],
  ["another inherited member as a property name", { properties: { ...backendEvent().properties, toString: "x" } }, "unknown_property:toString"],
  ["properties that are not an object", { properties: "x" }, "invalid_properties"],
  ["a missing consent record", { consent: undefined }, "invalid_consent"],
  ["a consent value that is not granted or denied", { consent: { analytics_storage: "maybe" } }, "invalid_consent"],
]) {
  test(`${name} is rejected as ${reason}`, () => {
    const result = run({ path: "backend", event: backendEvent(overrides), headers: {} });
    assert.equal(only(result, "events_rejected").reason, reason);
    assert.equal(result.inserts[0].rows[0].source, "backend");
  });
}

test("optional properties may be left out", () => {
  const result = run({ path: "backend", event: backendEvent(), headers: {} });
  assert.equal(only(result, "events").properties.latency_ms, undefined);
});

// --- Insert failures -------------------------------------------------------------

test("a failed insert is logged with the event_id and the error, and the tag fails", () => {
  const result = run({ event: browserEvent(), insertFails: true });
  assert.equal(result.outcome, "failure");
  const entry = JSON.parse(result.logs.at(-1));
  assert.equal(entry.type, "bigquery_insert_failed");
  assert.equal(entry.table, "events");
  assert.equal(entry.event_id, UUID);
  assert.match(JSON.stringify(entry.error), /forced failure/);
});

test("a failed insert of a rejected event is logged too", () => {
  const result = run({ event: browserEvent({ page_path: 5 }), insertFails: true });
  assert.equal(result.outcome, "failure");
  assert.equal(JSON.parse(result.logs.at(-1)).table, "events_rejected");
});

test("the insert names no project and does not skip invalid rows", () => {
  const result = run({ event: browserEvent() });
  assert.equal("projectId" in result.inserts[0].connection, false);
  assert.deepEqual(result.inserts[0].options, { ignoreUnknownValues: false, skipInvalidRows: false });
});
