import json
import unittest

from lagebericht.openai_client import OpenAIError, OpenAIResponsesClient


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        return self.response


class OpenAIClientTests(unittest.TestCase):
    def test_sends_structured_response_request_without_tools_or_storage(self):
        transport = RecordingTransport({
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}],
        })
        client = OpenAIResponsesClient("secret", transport=transport)
        result = client.generate_json("gpt-5.6-luna", "Rules", "Input", "example", {"type": "object"})
        self.assertEqual(result, {"ok": True})
        _, headers, payload, _ = transport.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertFalse(payload["store"])
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])

    def test_rejects_missing_api_key(self):
        with self.assertRaisesRegex(OpenAIError, "OPENAI_API_KEY"):
            OpenAIResponsesClient("")

    def test_rejects_refusal(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}
        with self.assertRaisesRegex(OpenAIError, "refused"):
            OpenAIResponsesClient("secret", transport=RecordingTransport(response)).generate_json("gpt-5.6-terra", "R", "I", "x", {})

    def test_rejects_incomplete_or_invalid_json_response(self):
        with self.assertRaisesRegex(OpenAIError, "not completed"):
            OpenAIResponsesClient("secret", transport=RecordingTransport({"status": "failed", "output": []})).generate_json("m", "R", "I", "x", {})
        invalid = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "not json"}]}]}
        with self.assertRaisesRegex(OpenAIError, "invalid JSON"):
            OpenAIResponsesClient("secret", transport=RecordingTransport(invalid)).generate_json("m", "R", "I", "x", {})


if __name__ == "__main__":
    unittest.main()

