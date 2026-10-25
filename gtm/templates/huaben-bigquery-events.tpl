___INFO___

{
  "type": "TAG",
  "id": "cvt_temp_public_id",
  "version": 1,
  "securityGroups": [],
  "displayName": "Huaben BigQuery events",
  "categories": [
    "ANALYTICS"
  ],
  "description": "Maps an event to the tracking contract's row, validates it, and writes it to analytics.events. An event that fails validation goes to analytics.events_rejected instead (D-040).",
  "containerContexts": [
    "SERVER"
  ]
}


___TEMPLATE_PARAMETERS___

[
  {
    "type": "SELECT",
    "name": "path",
    "displayName": "Path",
    "macrosInSelect": false,
    "selectItems": [
      {
        "value": "frontend",
        "displayValue": "Browser events (the GA4 client)"
      },
      {
        "value": "backend",
        "displayValue": "Backend events (the custom client)"
      }
    ],
    "simpleValueType": true,
    "defaultValue": "frontend",
    "help": "Which client's events this tag handles. Use one tag per path, each with a trigger on its own client."
  },
  {
    "type": "TEXT",
    "name": "projectId",
    "displayName": "BigQuery project ID",
    "simpleValueType": true,
    "help": "The environment's GCP project, e.g. huaben-tracking-platform-dev. Use a constant variable that differs per environment. The template's BigQuery permission must allow this project.",
    "valueValidators": [
      {
        "type": "NON_EMPTY"
      }
    ]
  },
  {
    "type": "TEXT",
    "name": "allowedOrigins",
    "displayName": "Allowed origins",
    "simpleValueType": true,
    "help": "Comma-separated, e.g. https://huaben.app,https://www.huaben.app. A browser event from any other Origin is logged and not stored (D-041). Use a constant variable that differs per environment.",
    "enablingConditions": [
      {
        "paramName": "path",
        "paramValue": "frontend",
        "type": "EQUALS"
      }
    ],
    "valueValidators": [
      {
        "type": "NON_EMPTY"
      }
    ]
  }
]


___SANDBOXED_JS_FOR_SERVER___

const BigQuery = require('BigQuery');
const getAllEventData = require('getAllEventData');
const getRequestHeader = require('getRequestHeader');
const getTimestampMillis = require('getTimestampMillis');
const getType = require('getType');
const JSON = require('JSON');
const logToConsole = require('logToConsole');
const makeInteger = require('makeInteger');
const makeString = require('makeString');
const Math = require('Math');
const Object = require('Object');

// The contract (D-018) is generated into this block by
// scripts/generate_contract.py. Do not edit it by hand.
// BEGIN GENERATED CONTRACT
const CONTRACT_VERSION = "1.0.1";
const SOURCE_FIELDS = ["event_id", "event_name", "schema_version", "source", "event_timestamp", "user_id", "anonymous_id", "session_id", "consent", "properties"];
const EVENTS = {
  "page_view": {
    "source": "frontend",
    "properties": {
      "page_location": {
        "type": "string",
        "required": true
      },
      "page_path": {
        "type": "string",
        "required": true
      },
      "page_title": {
        "type": "string",
        "required": false
      },
      "page_referrer": {
        "type": "string",
        "required": false
      }
    }
  },
  "story_generated": {
    "source": "backend",
    "properties": {
      "story_id": {
        "type": "string",
        "required": true
      },
      "generation_request_id": {
        "type": "string",
        "required": true
      },
      "target_hsk_level": {
        "type": "integer",
        "required": true,
        "minimum": 1,
        "maximum": 6
      },
      "target_word_count": {
        "type": "integer",
        "required": true,
        "minimum": 1
      },
      "target_vocabulary_count": {
        "type": "integer",
        "required": true,
        "minimum": 1
      },
      "has_topic": {
        "type": "boolean",
        "required": true
      },
      "provider": {
        "type": "string",
        "required": true
      },
      "model": {
        "type": "string",
        "required": true
      },
      "prompt_version": {
        "type": "string",
        "required": false
      },
      "attempt_count": {
        "type": "integer",
        "required": true,
        "minimum": 1
      },
      "total_tokens": {
        "type": "integer",
        "required": false,
        "minimum": 0
      },
      "latency_ms": {
        "type": "integer",
        "required": false,
        "minimum": 0
      }
    }
  },
  "login": {
    "source": "backend",
    "properties": {
      "method": {
        "type": "string",
        "required": true,
        "enum": [
          "password"
        ]
      }
    }
  },
  "quiz_submitted": {
    "source": "backend",
    "properties": {
      "story_id": {
        "type": "string",
        "required": true
      },
      "quiz_attempt_id": {
        "type": "string",
        "required": true
      },
      "question_count": {
        "type": "integer",
        "required": true,
        "minimum": 1
      },
      "correct_count": {
        "type": "integer",
        "required": true,
        "minimum": 0
      }
    }
  }
};
// END GENERATED CONTRACT

const DATASET = 'analytics';
const EVENTS_TABLE = 'events';
const REJECTED_TABLE = 'events_rejected';

// Limits on what a sender can post (D-041).
const MAX_STRING = 2048;
const MAX_ID = 64;
const MAX_PAYLOAD = 8000;

// --- Writing ---------------------------------------------------------------

function insert(table, row, eventId, done) {
  BigQuery.insert(
    // The permission only allows a call that names its project, so the project
    // comes from a per-environment variable, like the allowed origins.
    {projectId: data.projectId, datasetId: DATASET, tableId: table},
    [row],
    {ignoreUnknownValues: false, skipInvalidRows: false},
    function() {
      done(true);
    },
    function(errors) {
      // TP-8's alert fires on this entry.
      logToConsole(JSON.stringify({type: 'bigquery_insert_failed', table: table, event_id: eventId, error: errorReasons(errors)}));
      done(false);
    }
  );
}

// The properties column is JSON, and the streaming insert wants a JSON column's
// value as a string. An object would be read as a RECORD and refused.
function storedRow(row) {
  const stored = {};
  const names = Object.keys(row);
  for (let i = 0; i < names.length; i++) stored[names[i]] = row[names[i]];
  stored.properties = JSON.stringify(row.properties);
  return stored;
}

// BigQuery's error for a row echoes the whole row back, with the user's
// identifiers, and its messages can quote values. Logs outlive an erasure
// request (D-022), so only the reasons and field names are logged.
function errorReasons(errors) {
  // Anything unexpected is reported as unknown, never passed through: it
  // could be, or contain, the row.
  const unknown = [{reason: 'unknown', field: ''}];
  if (getType(errors) !== 'array') return unknown;
  const reasons = [];
  for (let i = 0; i < errors.length; i++) {
    const item = errors[i];
    const inner = getType(item) === 'object' && getType(item.errors) === 'array' ? item.errors : [item];
    for (let j = 0; j < inner.length; j++) {
      const error = inner[j];
      if (getType(error) !== 'object') {
        reasons.push(unknown[0]);
      } else {
        // Not the message: BigQuery's wording can quote the value that failed.
        // The field's name is enough to find the problem.
        reasons.push({
          reason: isString(error.reason) ? error.reason : 'unknown',
          field: isString(error.location) && error.location.length <= 100 ? error.location : ''
        });
      }
    }
  }
  return reasons.length > 0 ? reasons : unknown;
}

function rejectedRow(reason) {
  let source = eventData;
  if (path === 'frontend') {
    // The browser path also carries Google's own details: the IP address,
    // client ID, user agent, and more. None of it is stored, so only the
    // contract's own keys are kept.
    source = {};
    const keys = payloadKeys();
    for (let i = 0; i < keys.length; i++) {
      if (eventData[keys[i]] !== undefined) source[keys[i]] = eventData[keys[i]];
    }
  }
  let payload = JSON.stringify(source);
  const truncated = payload.length > MAX_PAYLOAD;
  if (truncated) payload = payload.substring(0, MAX_PAYLOAD);
  return {
    received_at: receivedAtSeconds,
    reason: reason,
    source: path === 'frontend' || path === 'backend' ? path : 'unknown',
    event_id: safeId(eventData.event_id),
    payload: payload,
    payload_truncated: truncated
  };
}

function payloadKeys() {
  const keys = SOURCE_FIELDS.concat(['app_session_id']);
  const names = Object.keys(EVENTS);
  for (let i = 0; i < names.length; i++) {
    const properties = Object.keys(EVENTS[names[i]].properties);
    for (let j = 0; j < properties.length; j++) {
      if (keys.indexOf(properties[j]) === -1) keys.push(properties[j]);
    }
  }
  return keys;
}

// An event_id is not trusted until it has been validated.
function safeId(value) {
  return getType(value) === 'string' && value.length <= MAX_ID ? value : null;
}

// --- Mapping ---------------------------------------------------------------

function orNull(value) {
  return value === undefined ? null : value;
}

// The GA4 client's event, in GA4's shape, to the contract's row (D-027).
// Only the contract's fields are copied. The rest of the request (the client
// ID, IP address, region, screen size, language, browser details) is dropped.
function mapBrowserEvent(e) {
  const properties = {};
  if (isKnownEvent(e.event_name)) {
    const names = Object.keys(EVENTS[e.event_name].properties);
    for (let i = 0; i < names.length; i++) {
      if (e[names[i]] !== undefined) properties[names[i]] = e[names[i]];
    }
  }
  return {
    event_id: orNull(e.event_id),
    event_name: orNull(e.event_name),
    schema_version: orNull(e.schema_version),
    source: 'frontend',
    event_timestamp: orNull(e.event_timestamp),
    server_timestamp: receivedAtSeconds,
    user_id: getType(e.user_id) === 'number' ? makeString(e.user_id) : orNull(e.user_id),
    anonymous_id: orNull(e.anonymous_id),
    // Sent as app_session_id, because Google's tag takes session_id as its own.
    session_id: orNull(e.app_session_id),
    // Only analytics_storage is known; the other signals stay null (spec).
    consent: {analytics_storage: analyticsStorageGranted(e) ? 'granted' : 'denied'},
    properties: properties
  };
}

// Server containers have no consent API. The GA4 client puts Google's consent
// state in the event data as x-ga-gcs: G1, then ad_storage and analytics_storage
// as 1 (granted) or 0 (denied), e.g. G101. Missing or malformed counts as denied.
function analyticsStorageGranted(e) {
  const gcs = e['x-ga-gcs'];
  return isString(gcs) && gcs.length === 4 && gcs.substring(0, 2) === 'G1' &&
    '01'.indexOf(gcs.charAt(2)) !== -1 && gcs.charAt(3) === '1';
}

// The backend's event arrives in the contract's shape, without server_timestamp.
function mapBackendEvent(e) {
  return {
    event_id: orNull(e.event_id),
    event_name: orNull(e.event_name),
    schema_version: orNull(e.schema_version),
    source: orNull(e.source),
    event_timestamp: orNull(e.event_timestamp),
    server_timestamp: receivedAtSeconds,
    user_id: orNull(e.user_id),
    anonymous_id: orNull(e.anonymous_id),
    session_id: orNull(e.session_id),
    consent: orNull(e.consent),
    properties: orNull(e.properties)
  };
}

// --- Origin ----------------------------------------------------------------

function originAllowed() {
  let origin = getRequestHeader('origin');
  if (!origin) {
    // A request without an Origin (an image request, say) is judged by its Referer.
    const referer = getRequestHeader('referer');
    if (referer) {
      const parts = referer.split('/');
      if (parts.length >= 3) origin = parts[0] + '//' + parts[2];
    }
  }
  if (!origin) return false;
  const allowed = (data.allowedOrigins || '').split(',');
  for (let i = 0; i < allowed.length; i++) {
    if (allowed[i].trim() === origin) return true;
  }
  return false;
}

// --- Validation ------------------------------------------------------------

// Returns the reason a row is rejected, or null when it is valid. The reasons
// are short codes, so they can be counted.
function validate(row) {
  if (!isKnownEvent(row.event_name)) return 'unknown_event_name';
  const spec = EVENTS[row.event_name];
  if (spec.source !== path) return 'event_not_allowed_on_' + path + '_path';
  if (!isUuid4(row.event_id)) return 'invalid_event_id';
  if (!isCompatibleVersion(row.schema_version)) return 'invalid_schema_version';
  if (row.source !== path) return 'invalid_source';
  if (!isTimestamp(row.event_timestamp)) return 'invalid_event_timestamp';
  if (row.user_id !== null && !(isString(row.user_id) && row.user_id.length >= 1 && row.user_id.length <= MAX_ID)) {
    return 'invalid_user_id';
  }
  if (row.anonymous_id !== null && !isUuid4(row.anonymous_id)) return 'invalid_anonymous_id';
  if (row.session_id !== null && !isUuid4(row.session_id)) return 'invalid_session_id';
  const consentReason = validateConsent(row.consent);
  if (consentReason !== null) return consentReason;
  return validateProperties(spec, row.properties);
}

function validateConsent(consent) {
  if (getType(consent) !== 'object') return 'invalid_consent';
  if (!isOneOf(consent.analytics_storage, ['granted', 'denied'])) return 'invalid_consent';
  const optional = ['ad_storage', 'ad_user_data', 'ad_personalization'];
  for (let i = 0; i < optional.length; i++) {
    const value = consent[optional[i]];
    if (value !== undefined && value !== null && !isOneOf(value, ['granted', 'denied'])) return 'invalid_consent';
  }
  // Consent Mode blocks the browser tag until analytics_storage is granted
  // (D-027), so a browser event that says otherwise did not come from it.
  if (path === 'frontend' && consent.analytics_storage !== 'granted') return 'consent_not_granted';
  return null;
}

function validateProperties(spec, properties) {
  if (getType(properties) !== 'object') return 'invalid_properties';
  const names = Object.keys(spec.properties);
  const given = Object.keys(properties);
  // Compared by name: a lookup like spec.properties[name] also finds inherited
  // members such as `constructor`.
  for (let i = 0; i < given.length; i++) {
    if (names.indexOf(given[i]) === -1) return 'unknown_property:' + given[i];
  }
  for (let i = 0; i < names.length; i++) {
    const reason = validateProperty(names[i], spec.properties[names[i]], properties[names[i]]);
    if (reason !== null) return reason;
  }
  return null;
}

function validateProperty(name, spec, value) {
  if (value === undefined || value === null) return spec.required ? 'missing_property:' + name : null;
  const type = getType(value);
  const invalid = 'invalid_property:' + name;
  if (spec.type === 'string') {
    if (type !== 'string' || value.length > MAX_STRING) return invalid;
    if (spec.enum && !isOneOf(value, spec.enum)) return invalid;
  } else if (spec.type === 'integer' || spec.type === 'number') {
    if (type !== 'number') return invalid;
    if (spec.type === 'integer' && Math.floor(value) !== value) return invalid;
    if (spec.minimum !== undefined && value < spec.minimum) return invalid;
    if (spec.maximum !== undefined && value > spec.maximum) return invalid;
  } else if (spec.type === 'boolean') {
    if (type !== 'boolean') return invalid;
  }
  return null;
}

function isKnownEvent(name) {
  return isString(name) && Object.keys(EVENTS).indexOf(name) !== -1;
}

function isString(value) {
  return getType(value) === 'string';
}

function isOneOf(value, allowed) {
  return isString(value) && allowed.indexOf(value) !== -1;
}

function isDigits(text) {
  if (text.length === 0) return false;
  for (let i = 0; i < text.length; i++) {
    if ('0123456789'.indexOf(text.charAt(i)) === -1) return false;
  }
  return true;
}

function isUuid4(value) {
  if (!isString(value) || value.length !== 36) return false;
  for (let i = 0; i < 36; i++) {
    const c = value.charAt(i);
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      if (c !== '-') return false;
    } else if ('0123456789abcdef'.indexOf(c) === -1) {
      return false;
    }
  }
  return value.charAt(14) === '4' && '89ab'.indexOf(value.charAt(19)) !== -1;
}

// Senders built against an earlier minor or patch version stay valid (D-018).
function isCompatibleVersion(value) {
  if (!isString(value) || value.length > 20) return false;
  const parts = value.split('.');
  return parts.length === 3 && isDigits(parts[0]) && isDigits(parts[1]) && isDigits(parts[2]) &&
    parts[0] === CONTRACT_VERSION.split('.')[0];
}

// RFC 3339, e.g. 2026-10-04T09:30:00.123Z, with a Z or an offset.
function isTimestamp(value) {
  if (!isString(value) || value.length < 20 || value.length > 40) return false;
  if (value.charAt(4) !== '-' || value.charAt(7) !== '-' || value.charAt(10) !== 'T' ||
      value.charAt(13) !== ':' || value.charAt(16) !== ':') return false;
  const parts = [
    value.substring(0, 4), value.substring(5, 7), value.substring(8, 10),
    value.substring(11, 13), value.substring(14, 16), value.substring(17, 19)
  ];
  for (let i = 0; i < parts.length; i++) {
    if (!isDigits(parts[i])) return false;
  }
  const month = makeInteger(parts[1]);
  const day = makeInteger(parts[2]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  if (makeInteger(parts[3]) > 23 || makeInteger(parts[4]) > 59 || makeInteger(parts[5]) > 59) return false;
  let rest = value.substring(19);
  if (rest.charAt(0) === '.') {
    let i = 1;
    while (i < rest.length && '0123456789'.indexOf(rest.charAt(i)) !== -1) i++;
    if (i === 1) return false;
    rest = rest.substring(i);
  }
  if (rest === 'Z') return true;
  return rest.length === 6 && '+-'.indexOf(rest.charAt(0)) !== -1 && rest.charAt(3) === ':' &&
    isDigits(rest.substring(1, 3)) && isDigits(rest.substring(4, 6));
}

// --- Run -------------------------------------------------------------------

const path = data.path;
const eventData = getAllEventData();
const receivedAtSeconds = getTimestampMillis() / 1000;

if (path === 'frontend' && !originAllowed()) {
  // Not stored: forged traffic must not be able to fill events_rejected (D-041).
  logToConsole(JSON.stringify({type: 'origin_rejected', origin: getRequestHeader('origin') || null}));
  data.gtmOnSuccess();
} else {
  const row = path === 'frontend' ? mapBrowserEvent(eventData) : mapBackendEvent(eventData);
  const reason = validate(row);
  if (reason === null) {
    insert(EVENTS_TABLE, storedRow(row), row.event_id, function(ok) {
      if (ok) data.gtmOnSuccess(); else data.gtmOnFailure();
    });
  } else {
    logToConsole(JSON.stringify({type: 'event_rejected', reason: reason, source: path}));
    insert(REJECTED_TABLE, rejectedRow(reason), safeId(eventData.event_id), function(ok) {
      if (ok) data.gtmOnSuccess(); else data.gtmOnFailure();
    });
  }
}


___NOTES___

The contract block is generated: run `python scripts/generate_contract.py` after editing contract/events.yaml.
The permissions this template needs are listed in gtm/templates/README.md.
