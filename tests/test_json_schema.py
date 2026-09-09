import unittest

from local_llm_benchmark.json_schema import JsonSchemaError, validate_json


class JsonSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "when", "items", "score", "optional"],
            "properties": {
                "id": {"type": "string", "pattern": "^item-[0-9]+$", "minLength": 6},
                "when": {"type": "string", "format": "date-time"},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/entry"},
                },
                "score": {"type": "number", "minimum": 0, "maximum": 100},
                "optional": {"type": ["string", "null"]},
            },
            "$defs": {
                "entry": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["value"],
                    "properties": {"value": {"enum": ["a", "b"]}},
                }
            },
        }
        self.value = {
            "id": "item-1",
            "when": "2026-09-09T08:00:00Z",
            "items": [{"value": "a"}],
            "score": 91.5,
            "optional": None,
        }

    def test_supported_contract_validates(self) -> None:
        self.assertIsNone(validate_json(self.value, self.schema))

    def test_missing_extra_type_pattern_range_and_uniqueness_are_rejected(self) -> None:
        mutations = [
            {key: value for key, value in self.value.items() if key != "id"},
            {**self.value, "extra": True},
            {**self.value, "score": True},
            {**self.value, "id": "wrong"},
            {**self.value, "score": 101},
            {**self.value, "items": [{"value": "a"}, {"value": "a"}]},
        ]
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(JsonSchemaError):
                validate_json(value, self.schema)

    def test_date_time_requires_valid_explicit_timezone(self) -> None:
        for value in ("2026-09-09T08:00:00", "not-a-date"):
            with self.subTest(value=value), self.assertRaises(JsonSchemaError):
                validate_json({**self.value, "when": value}, self.schema)

    def test_unknown_assertion_keyword_is_not_silently_ignored(self) -> None:
        with self.assertRaisesRegex(JsonSchemaError, "unsupported schema keyword"):
            validate_json("x", {"type": "string", "maxLength": 2})
        with self.assertRaisesRegex(JsonSchemaError, "unsupported schema keyword"):
            validate_json(
                {},
                {
                    "type": "object",
                    "properties": {
                        "optional": {"type": "string", "maxLength": 2}
                    },
                },
            )

    def test_boolean_is_not_a_json_number(self) -> None:
        with self.assertRaises(JsonSchemaError):
            validate_json(True, {"type": "integer"})


if __name__ == "__main__":
    unittest.main()
