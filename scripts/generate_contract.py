"""Generate the BigQuery schema, dbt source tests, and Pydantic models from the contract.

    python scripts/generate_contract.py           # write the generated files
    python scripts/generate_contract.py --check   # fail if they are out of date

The contract is contract/events.yaml (D-018). Generated files are committed, and
the pre-commit hook runs `--check`, so CI fails when they don't match the contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "events.yaml"
BIGQUERY_SCHEMA = ROOT / "contract" / "generated" / "bigquery" / "events.schema.json"
DBT_SOURCES = ROOT / "dbt" / "models" / "staging" / "_contract__sources.yml"
PYTHON_PACKAGE = ROOT / "contract" / "python"
PYTHON_MODELS = PYTHON_PACKAGE / "src" / "huaben_tracking_contract" / "models.py"
PYTHON_PYPROJECT = PYTHON_PACKAGE / "pyproject.toml"

HEADER = "Generated from contract/events.yaml by scripts/generate_contract.py. Do not edit."

SOURCES = ("frontend", "backend")
SETTERS = ("source", "sgtm")
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

BIGQUERY_TYPES = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "FLOAT",
    "boolean": "BOOLEAN",
    "timestamp": "TIMESTAMP",
    "json": "JSON",
    "record": "RECORD",
}
PROPERTY_TYPES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


class ContractError(Exception):
    """The contract file breaks one of its own rules."""


def load_contract() -> dict[str, Any]:
    contract = yaml.safe_load(CONTRACT.read_text())
    validate(contract)
    return contract


def validate(contract: dict[str, Any]) -> None:
    if not SEMVER.match(str(contract.get("version", ""))):
        raise ContractError("version must be a semantic version, e.g. 1.0.0")

    names = set()
    for field in contract["common_fields"]:
        validate_field(field, where="common_fields")
        if field["name"] in names:
            raise ContractError(f"common field {field['name']} is defined twice")
        names.add(field["name"])
        if field.get("set_by") not in SETTERS:
            raise ContractError(f"{field['name']}: set_by must be one of {SETTERS}")
        for sub_field in field.get("fields", []):
            validate_field(sub_field, where=field["name"])

    for name, event in contract["events"].items():
        if not EVENT_NAME.match(name):
            raise ContractError(f"event {name}: names are snake_case, at most 40 characters")
        if event.get("source") not in SOURCES:
            raise ContractError(f"event {name}: source must be one of {SOURCES}")
        if not event.get("description"):
            raise ContractError(f"event {name}: description is required")
        if not event.get("event_time"):
            raise ContractError(f"event {name}: event_time must say which moment event_timestamp is")
        for prop_name, prop in (event.get("properties") or {}).items():
            validate_field({"name": prop_name, **prop}, where=f"event {name}")
            if prop["type"] not in PROPERTY_TYPES:
                raise ContractError(
                    f"event {name}: property {prop_name} must be one of {sorted(PROPERTY_TYPES)}"
                )


def validate_field(field: dict[str, Any], *, where: str) -> None:
    name = field.get("name", "")
    if not FIELD_NAME.match(name):
        raise ContractError(f"{where}: field name {name!r} must be snake_case")
    if field.get("type") not in BIGQUERY_TYPES:
        raise ContractError(f"{where}: {name} has unknown type {field.get('type')!r}")
    if not isinstance(field.get("required"), bool):
        raise ContractError(f"{where}: {name} must say required: true or false")
    if not field.get("description"):
        raise ContractError(f"{where}: {name} needs a description")


# --- BigQuery ---------------------------------------------------------------


def bigquery_field(field: dict[str, Any]) -> dict[str, Any]:
    column = {
        "name": field["name"],
        "type": BIGQUERY_TYPES[field["type"]],
        "mode": "REQUIRED" if field["required"] else "NULLABLE",
        "description": field["description"],
    }
    if field["type"] == "record":
        column["fields"] = [bigquery_field(sub_field) for sub_field in field["fields"]]
    return column


def render_bigquery_schema(contract: dict[str, Any]) -> str:
    schema = [bigquery_field(field) for field in contract["common_fields"]]
    return json.dumps(schema, indent=2) + "\n"


# --- dbt --------------------------------------------------------------------


def dbt_tests(field: dict[str, Any], accepted: list[str] | None) -> list[Any]:
    tests: list[Any] = []
    if field["required"]:
        tests.append("not_null")
    if accepted:
        tests.append({"accepted_values": {"arguments": {"values": accepted}}})
    return tests


def render_dbt_sources(contract: dict[str, Any]) -> str:
    columns = []
    for field in contract["common_fields"]:
        accepted = field.get("enum")
        if field["name"] == "event_name":
            accepted = list(contract["events"])
        column: dict[str, Any] = {"name": field["name"], "description": field["description"]}
        if tests := dbt_tests(field, accepted):
            column["data_tests"] = tests
        columns.append(column)
        # dbt addresses a nested field by its dotted path.
        for sub_field in field.get("fields", []):
            sub_column: dict[str, Any] = {
                "name": f"{field['name']}.{sub_field['name']}",
                "description": sub_field["description"],
            }
            if tests := dbt_tests(sub_field, sub_field.get("enum")):
                sub_column["data_tests"] = tests
            columns.append(sub_column)

    sources = {
        "version": 2,
        "sources": [
            {
                "name": "analytics",
                "description": "Raw events written by sGTM.",
                "database": "{{ target.database }}",
                "schema": "analytics",
                "tables": [
                    {
                        "name": "events",
                        "description": (
                            f"One row per received event, contract version {contract['version']}. "
                            "Delivery is at-least-once, so event_id is not unique here."
                        ),
                        "columns": columns,
                    }
                ],
            }
        ],
    }
    body = yaml.safe_dump(sources, sort_keys=False, width=1000, allow_unicode=True)
    return f"# {HEADER}\n{body}"


# --- Pydantic ---------------------------------------------------------------


def class_name(event_name: str) -> str:
    return "".join(part.capitalize() for part in event_name.split("_"))


def literal(values: list[str]) -> str:
    return "Literal[" + ", ".join(json.dumps(value) for value in values) + "]"


def python_type(field: dict[str, Any]) -> str:
    if field.get("enum"):
        return literal(field["enum"])
    if field.get("format") == "uuid":
        return "UUID"
    if field["type"] == "timestamp":
        return "AwareDatetime"
    return PROPERTY_TYPES[field["type"]]


def field_line(field: dict[str, Any], annotation: str | None = None) -> str:
    """One model attribute, e.g. `name: str | None = Field(default=None, description=...)`."""
    annotation = annotation or python_type(field)
    arguments = []
    if not field["required"]:
        annotation += " | None"
        arguments.append("default=None")
    if "minimum" in field:
        arguments.append(f"ge={field['minimum']}")
    if "maximum" in field:
        arguments.append(f"le={field['maximum']}")
    arguments.append(f"description={json.dumps(field['description'])}")
    return f"    {field['name']}: {annotation} = Field({', '.join(arguments)})"


def render_python_models(contract: dict[str, Any]) -> str:
    version = contract["version"]
    backend_events = {
        name: event for name, event in contract["events"].items() if event["source"] == "backend"
    }
    lines = [
        f'"""Pydantic models for the backend\'s events.\n\n{HEADER}\n"""',
        "",
        "from typing import Literal",
        "from uuid import UUID, uuid4",
        "",
        "from pydantic import AwareDatetime, BaseModel, ConfigDict, Field",
        "",
        f"SCHEMA_VERSION = {json.dumps(version)}",
        "",
        "",
        "class _Model(BaseModel):",
        '    model_config = ConfigDict(extra="forbid")',
    ]

    # Nested records, such as consent, become their own models.
    for field in contract["common_fields"]:
        if field["type"] == "record" and field["set_by"] == "source":
            lines += ["", "", f"class {class_name(field['name'])}(_Model):"]
            lines.append(f'    """{field["description"]}"""')
            lines.append("")
            lines += [field_line(sub_field) for sub_field in field["fields"]]

    for name, event in backend_events.items():
        model = class_name(name)
        lines += ["", "", f"class {model}Properties(_Model):"]
        lines.append(f'    """Properties of `{name}`."""')
        lines.append("")
        properties = event.get("properties") or {}
        lines += [field_line({"name": prop, **spec}) for prop, spec in properties.items()]

        lines += ["", "", f"class {model}(_Model):"]
        lines.append(f'    """{event["description"]}"""')
        lines.append("")
        for field in contract["common_fields"]:
            if field["set_by"] != "source":
                continue
            field_name = field["name"]
            if field_name == "event_id":
                lines.append("    event_id: UUID = Field(default_factory=uuid4)")
            elif field_name == "event_name":
                lines.append(f"    event_name: {literal([name])} = {json.dumps(name)}")
            elif field_name == "schema_version":
                lines.append(f"    schema_version: {literal([version])} = SCHEMA_VERSION")
            elif field_name == "source":
                lines.append(f'    source: {literal(["backend"])} = "backend"')
            elif field_name == "event_timestamp":
                # Required, with no default: the caller passes the business time.
                description = json.dumps(event["event_time"])
                lines.append(f"    event_timestamp: AwareDatetime = Field(description={description})")
            elif field_name == "properties":
                lines.append(f"    properties: {model}Properties")
            elif field["type"] == "record":
                lines.append(f"    {field_name}: {class_name(field_name)}")
            else:
                lines.append(field_line(field))

    exported = ["SCHEMA_VERSION"]
    exported += [
        class_name(field["name"])
        for field in contract["common_fields"]
        if field["type"] == "record" and field["set_by"] == "source"
    ]
    for name in backend_events:
        exported += [class_name(name), f"{class_name(name)}Properties"]
    lines += ["", "", "__all__ = ["]
    lines += [f"    {json.dumps(symbol)}," for symbol in sorted(exported)]
    lines.append("]")
    return "\n".join(lines) + "\n"


def render_python_pyproject(contract: dict[str, Any]) -> str:
    return f"""# {HEADER}
[project]
name = "huaben-tracking-contract"
version = "{contract["version"]}"
description = "Pydantic models for the Huaben tracking contract's backend events."
requires-python = ">=3.11"
dependencies = ["pydantic>=2.7,<3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/huaben_tracking_contract"]
"""


# ----------------------------------------------------------------------------


def render_all(contract: dict[str, Any]) -> dict[Path, str]:
    return {
        BIGQUERY_SCHEMA: render_bigquery_schema(contract),
        DBT_SOURCES: render_dbt_sources(contract),
        PYTHON_MODELS: render_python_models(contract),
        PYTHON_PYPROJECT: render_python_pyproject(contract),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the generated files are out of date"
    )
    args = parser.parse_args()

    try:
        rendered = render_all(load_contract())
    except ContractError as error:
        print(f"contract/events.yaml: {error}", file=sys.stderr)
        return 1

    stale = [
        path for path, content in rendered.items()
        if not path.exists() or path.read_text() != content
    ]
    if args.check:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}", file=sys.stderr)
        if stale:
            print("Run `python scripts/generate_contract.py` and commit the result.", file=sys.stderr)
        return 1 if stale else 0

    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered[path])
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
