import unittest

from local_llm_benchmark.ollama import (
    OllamaClient,
    OllamaError,
    decode_ndjson_line,
    normalize_host,
)


class OllamaHelpersTest(unittest.TestCase):
    def test_normalize_host(self) -> None:
        self.assertEqual(normalize_host("127.0.0.1:11434"), "http://127.0.0.1:11434/")
        self.assertEqual(normalize_host("http://localhost:11434/"), "http://localhost:11434/")

    def test_decode_ndjson(self) -> None:
        event = decode_ndjson_line(b'{"message":{"content":"Hallo"},"done":false}\n')
        self.assertEqual(event["message"]["content"], "Hallo")
        self.assertIsNone(decode_ndjson_line(b"\n"))

    def test_decode_ndjson_rejects_stream_error(self) -> None:
        with self.assertRaises(OllamaError):
            decode_ndjson_line(b'{"error":"model failed"}\n')

    def test_unload_model_uses_generate_keep_alive_zero(self) -> None:
        calls = []

        class RecordingClient:
            def _request_json(self, method, path, payload=None):
                calls.append((method, path, payload))
                return {"done": True}

        client = RecordingClient()
        result = OllamaClient.unload_model(client, "model:test")
        self.assertEqual(result, {"done": True})
        self.assertEqual(
            calls,
            [
                (
                    "POST",
                    "/api/generate",
                    {"model": "model:test", "stream": False, "keep_alive": 0},
                )
            ],
        )

    def test_preload_model_uses_requested_keep_alive(self) -> None:
        calls = []

        class RecordingClient:
            def _request_json(self, method, path, payload=None):
                calls.append((method, path, payload))
                return {"done": True}

        client = RecordingClient()
        result = OllamaClient.preload_model(client, "model:test", "10m")
        self.assertEqual(result, {"done": True})
        self.assertEqual(
            calls,
            [
                (
                    "POST",
                    "/api/generate",
                    {"model": "model:test", "stream": False, "keep_alive": "10m"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
