"""Small dependency-free validator for the project's frozen judge schemas.

This is deliberately not a general JSON Schema implementation. It implements
the closed subset used by the repository's judge-result schemas and rejects
unknown assertion keywords instead of silently accepting a weaker contract.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any


class JsonSchemaError(ValueError):
    """Raised when a value violates a supported JSON Schema contract."""


_ANNOTATION_KEYWORDS = {
    "$schema",
    "$id",
    "$defs",
    "title",
    "description",
    "default",
    "examples",
}
_ASSERTION_KEYWORDS = {
    "$ref",
    "type",
    "const",
    "enum",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
}
_SUPPORTED_KEYWORDS = _ANNOTATION_KEYWORDS | _ASSERTION_KEYWORDS


def _fail(path: str, message: str) -> None:
    raise JsonSchemaError(f"{path}: {message}")


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def _resolve_ref(root: dict[str, Any], reference: str, path: str) -> Any:
    if not reference.startswith("#/"):
        _fail(path, f"unsupported non-local $ref {reference!r}")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            _fail(path, f"unresolvable $ref {reference!r}")
        current = current[part]
    return current


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    return False


def _validate_schema(
    schema: Any,
    root: dict[str, Any],
    path: str,
    visited: set[int],
) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        _fail(path, "schema node must be an object or boolean")
    identity = id(schema)
    if identity in visited:
        return
    visited.add(identity)
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        _fail(path, "unsupported schema keyword(s): " + ", ".join(sorted(unknown)))
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str):
            _fail(path, "$ref must be a string")
        if set(schema) - _ANNOTATION_KEYWORDS - {"$ref"}:
            _fail(path, "sibling assertions beside $ref are not supported")
        _validate_schema(_resolve_ref(root, reference, path), root, reference, visited)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        _fail(path, "schema properties must be an object")
    for key, child in properties.items():
        _validate_schema(child, root, f"{path}.properties.{key}", visited)
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        _fail(path, "$defs must be an object")
    for key, child in definitions.items():
        _validate_schema(child, root, f"{path}.$defs.{key}", visited)
    if "items" in schema:
        _validate_schema(schema["items"], root, f"{path}.items", visited)
    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], bool
    ):
        _fail(path, "only boolean additionalProperties is supported")
    if "format" in schema and schema["format"] != "date-time":
        _fail(path, f"unsupported format {schema['format']!r}")


def _validate_datetime(value: str, path: str) -> None:
    if not re.search(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$", value):
        _fail(path, "must be an RFC 3339 date-time with an explicit time zone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        _fail(path, f"must be a valid date-time ({error})")
    if parsed.tzinfo is None:
        _fail(path, "date-time must include a time zone")


def _validate(value: Any, schema: Any, root: dict[str, Any], path: str) -> None:
    if isinstance(schema, bool):
        if not schema:
            _fail(path, "is rejected by the boolean schema")
        return
    if not isinstance(schema, dict):
        _fail(path, "schema node must be an object or boolean")

    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        _fail(path, "unsupported schema keyword(s): " + ", ".join(sorted(unknown)))

    if "$ref" in schema:
        if set(schema) - _ANNOTATION_KEYWORDS - {"$ref"}:
            _fail(path, "sibling assertions beside $ref are not supported")
        reference = schema["$ref"]
        if not isinstance(reference, str):
            _fail(path, "$ref must be a string")
        _validate(value, _resolve_ref(root, reference, path), root, path)
        return

    if "type" in schema:
        declared = schema["type"]
        expected = declared if isinstance(declared, list) else [declared]
        if not expected or not all(isinstance(item, str) for item in expected):
            _fail(path, "schema type must be a string or non-empty string array")
        unsupported = set(expected) - {
            "null",
            "boolean",
            "object",
            "array",
            "string",
            "integer",
            "number",
        }
        if unsupported:
            _fail(path, "unsupported schema type(s): " + ", ".join(sorted(unsupported)))
        if not any(_matches_type(value, item) for item in expected):
            _fail(path, f"expected type {declared!r}")

    if "const" in schema and not _json_equal(value, schema["const"]):
        _fail(path, f"must equal {schema['const']!r}")
    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or not any(
            _json_equal(value, option) for option in options
        ):
            _fail(path, f"must be one of {options!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            _fail(path, "schema required must be a string array")
        missing = [key for key in required if key not in value]
        if missing:
            _fail(path, "missing required properties: " + ", ".join(missing))
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            _fail(path, "schema properties must be an object")
        extras = set(value) - set(properties)
        additional = schema.get("additionalProperties", True)
        if not isinstance(additional, bool):
            _fail(path, "only boolean additionalProperties is supported")
        if extras and not additional:
            _fail(path, "unexpected properties: " + ", ".join(sorted(extras)))
        for key, child_schema in properties.items():
            if key in value:
                _validate(value[key], child_schema, root, f"{path}.{key}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            _fail(path, f"must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            _fail(path, f"must contain at most {schema['maxItems']} items")
        if schema.get("uniqueItems") is True:
            encoded = [
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            if len(set(encoded)) != len(encoded):
                _fail(path, "items must be unique")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], root, f"{path}[{index}]")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            _fail(path, f"must contain at least {schema['minLength']} characters")
        if "pattern" in schema:
            pattern = schema["pattern"]
            if not isinstance(pattern, str):
                _fail(path, "schema pattern must be a string")
            if re.search(pattern, value) is None:
                _fail(path, f"must match pattern {pattern!r}")
        if "format" in schema:
            if schema["format"] != "date-time":
                _fail(path, f"unsupported format {schema['format']!r}")
            _validate_datetime(value, path)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            _fail(path, "number must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            _fail(path, f"must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            _fail(path, f"must be at most {schema['maximum']}")


def validate_json(value: Any, schema: dict[str, Any]) -> None:
    """Validate *value* against the supported schema subset.

    The function returns ``None`` on success and raises :class:`JsonSchemaError`
    with a value path on the first violation.
    """

    if not isinstance(schema, dict):
        raise JsonSchemaError("$: root schema must be an object")
    _validate_schema(schema, schema, "$schema", set())
    _validate(value, schema, schema, "$")
