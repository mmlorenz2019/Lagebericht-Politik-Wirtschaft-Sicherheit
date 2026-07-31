from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        return self.response


class FakeHttpResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit):
        return self.body[:limit]


def load_client_class():
    try:
        from lagebericht.anthropic_client import AnthropicMessagesClient
    except ModuleNotFoundError as exc:
        raise AssertionError("AnthropicMessagesClient is not implemented") from exc
    return AnthropicMessagesClient


def load_error_class():
    try:
        from lagebericht.anthropic_client import AnthropicError
    except ImportError as exc:
        raise AssertionError("AnthropicError is not implemented") from exc
    return AnthropicError


class AnthropicClientTests(unittest.TestCase):
    def assert_client_error(self, response, pattern):
        client_class = load_client_class()
        error_class = load_error_class()
        try:
            client_class("secret", transport=RecordingTransport(response)).generate_json(
                "model", "Rules", "Input", "example", {}
            )
        except Exception as exc:
            self.assertIsInstance(exc, error_class)
            self.assertRegex(str(exc), pattern)
        else:
            self.fail("AnthropicError not raised")

    def test_generates_json_through_a_structured_messages_request(self):
        client_class = load_client_class()
        transport = RecordingTransport({
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 4},
        })
        client = client_class("secret", transport=transport)

        result = client.generate_json(
            "claude-haiku-4-5-20251001",
            "Rules",
            "Input",
            "example",
            {"type": "object"},
        )

        self.assertEqual(result, {"ok": True})
        url, headers, payload, timeout = transport.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers, {
            "x-api-key": "secret",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        self.assertEqual(payload, {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 8192,
            "system": "Rules",
            "messages": [{"role": "user", "content": "Input"}],
            "output_config": {
                "format": {"type": "json_schema", "schema": {"type": "object"}}
            },
        })
        self.assertEqual(timeout, 60.0)

    def test_removes_unsupported_schema_constraints_without_mutating_original(self):
        client_class = load_client_class()
        transport = RecordingTransport({
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": '{"value":"ok"}'}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 4},
        })
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.invalid/schema.json",
            "type": "object",
            "properties": {
                "value": {"type": "string", "format": "uri", "maxLength": 20}
            },
            "required": ["value"],
            "additionalProperties": False,
        }
        original = deepcopy(schema)

        client_class("secret", transport=transport).generate_json(
            "model", "Rules", "Input", "example", schema
        )

        sent = transport.calls[0][2]["output_config"]["format"]["schema"]
        self.assertNotIn("$schema", sent)
        self.assertNotIn("$id", sent)
        self.assertNotIn("format", sent["properties"]["value"])
        self.assertNotIn("maxLength", sent["properties"]["value"])
        self.assertEqual(schema, original)

    def test_uses_the_bounded_https_transport_by_default(self):
        client_class = load_client_class()
        body = (
            b'{"id":"msg_test","type":"message","role":"assistant",'
            b'"model":"claude-haiku-4-5-20251001","content":'
            b'[{"type":"text","text":"{\\"ok\\":true}"}],'
            b'"stop_reason":"end_turn","stop_sequence":null,'
            b'"usage":{"input_tokens":10,"output_tokens":4}}'
        )
        with patch(
            "lagebericht.anthropic_client.urlopen",
            return_value=FakeHttpResponse(body),
            create=True,
        ) as opener:
            try:
                client = client_class("secret")
            except TypeError as exc:
                self.fail(f"default transport is unavailable: {exc}")
            result = client.generate_json("model", "Rules", "Input", "example", {})

        self.assertEqual(result, {"ok": True})
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(opener.call_args.kwargs["timeout"], 60.0)

    def test_rejects_an_http_response_larger_than_two_megabytes(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with patch(
            "lagebericht.anthropic_client.urlopen",
            return_value=FakeHttpResponse(b"x" * 2_000_001),
        ):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "size limit")
            else:
                self.fail("AnthropicError not raised")

    def test_wraps_http_errors_without_exposing_the_api_key(self):
        client_class = load_client_class()
        error_class = load_error_class()
        error = HTTPError(
            "https://api.anthropic.com/v1/messages",
            400,
            "Bad Request",
            {},
            BytesIO(b"invalid request"),
        )
        with patch("lagebericht.anthropic_client.urlopen", side_effect=error):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "Anthropic HTTP 400")
                self.assertNotIn("secret", str(exc))
            else:
                self.fail("AnthropicError not raised")
        self.assertTrue(error.closed)

    def test_wraps_network_errors(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with patch(
            "lagebericht.anthropic_client.urlopen",
            side_effect=URLError("offline"),
        ):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "request failed")
            else:
                self.fail("AnthropicError not raised")

    def test_wraps_timeout_errors(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with patch(
            "lagebericht.anthropic_client.urlopen",
            side_effect=TimeoutError("late"),
        ):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "request failed")
            else:
                self.fail("AnthropicError not raised")

    def test_wraps_operating_system_errors(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with patch(
            "lagebericht.anthropic_client.urlopen",
            side_effect=OSError("socket closed"),
        ):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "request failed")
            else:
                self.fail("AnthropicError not raised")

    def test_wraps_invalid_json_in_the_http_response(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with patch(
            "lagebericht.anthropic_client.urlopen",
            return_value=FakeHttpResponse(b"not json"),
        ):
            try:
                client_class("secret").generate_json(
                    "model", "Rules", "Input", "example", {}
                )
            except Exception as exc:
                self.assertIsInstance(exc, error_class)
                self.assertRegex(str(exc), "request failed")
            else:
                self.fail("AnthropicError not raised")

    def test_rejects_a_missing_api_key_before_transport(self):
        client_class = load_client_class()
        error_class = load_error_class()
        with self.assertRaisesRegex(error_class, "ANTHROPIC_API_KEY"):
            client_class("", transport=RecordingTransport({}))

    def test_rejects_a_refusal_even_when_the_body_is_valid_json(self):
        client_class = load_client_class()
        error_class = load_error_class()
        response = {
            "id": "msg_refusal",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "refusal",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        with self.assertRaisesRegex(error_class, "refused"):
            client_class("secret", transport=RecordingTransport(response)).generate_json(
                "model", "Rules", "Input", "example", {}
            )

    def test_rejects_output_cut_off_at_the_token_limit(self):
        client_class = load_client_class()
        error_class = load_error_class()
        response = {
            "id": "msg_limited",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "max_tokens",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 8192},
        }
        with self.assertRaisesRegex(error_class, "token limit"):
            client_class("secret", transport=RecordingTransport(response)).generate_json(
                "model", "Rules", "Input", "example", {}
            )

    def test_rejects_any_unexpected_stop_reason(self):
        client_class = load_client_class()
        error_class = load_error_class()
        response = {
            "id": "msg_stopped",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "stop_sequence",
            "stop_sequence": "END",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        with self.assertRaisesRegex(error_class, "finish safely"):
            client_class("secret", transport=RecordingTransport(response)).generate_json(
                "model", "Rules", "Input", "example", {}
            )

    def test_rejects_a_non_object_api_response(self):
        self.assert_client_error([], "response was invalid")

    def test_rejects_a_response_without_a_text_block(self):
        response = {
            "id": "msg_empty",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }
        self.assert_client_error(response, "no text")

    def test_rejects_invalid_json_in_the_text_block(self):
        response = {
            "id": "msg_invalid_json",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "not json"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        self.assert_client_error(response, "invalid JSON")

    def test_rejects_structured_json_that_is_not_an_object(self):
        response = {
            "id": "msg_array",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "[]"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        self.assert_client_error(response, "must be an object")


if __name__ == "__main__":
    unittest.main()
