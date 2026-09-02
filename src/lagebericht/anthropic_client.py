from __future__ import annotations

import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AnthropicError(RuntimeError):
    """Raised when the Messages API does not return safe structured output."""


_LOCAL_ONLY_SCHEMA_KEYS = {
    "$schema",
    "$id",
    "format",
    "pattern",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minimum",
    "maximum",
}


def _anthropic_schema(value):
    if isinstance(value, dict):
        return {
            key: _anthropic_schema(item)
            for key, item in value.items()
            if key not in _LOCAL_ONLY_SCHEMA_KEYS
        }
    if isinstance(value, list):
        return [_anthropic_schema(item) for item in value]
    return value


def _parse_sse_response(body: bytes) -> dict:
    """Reassemble a non-streaming-shaped result from raw SSE bytes.

    Wire format is the Anthropic Messages API's documented SSE stream:
    message_start carries the initial usage (input_tokens; output_tokens
    starts at 0 or a small placeholder), content_block_delta text_delta
    events carry the growing text per block index, and message_delta
    carries the final stop_reason plus the final output_tokens - which
    must overwrite, not add to, message_start's placeholder.
    """
    text_by_index: dict[int, str] = {}
    stop_reason = None
    usage: dict | None = None
    for raw_line in body.decode("utf-8", errors="replace").split("\n"):
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        try:
            data = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        event_type = data.get("type")
        if event_type == "message_start":
            message = data.get("message")
            if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                usage = dict(message["usage"])
        elif event_type == "content_block_delta":
            delta = data.get("delta")
            index = data.get("index")
            if (
                isinstance(delta, dict)
                and delta.get("type") == "text_delta"
                and isinstance(index, int)
                and isinstance(delta.get("text"), str)
            ):
                text_by_index[index] = text_by_index.get(index, "") + delta["text"]
        elif event_type == "message_delta":
            delta = data.get("delta")
            if isinstance(delta, dict) and "stop_reason" in delta:
                stop_reason = delta["stop_reason"]
            delta_usage = data.get("usage")
            if isinstance(delta_usage, dict):
                usage = {**(usage or {}), **delta_usage}
    content = [{"type": "text", "text": text_by_index[index]} for index in sorted(text_by_index)]
    return {"content": content, "stop_reason": stop_reason, "usage": usage}


def _default_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise AnthropicError("Anthropic response exceeded size limit")
            if payload.get("stream"):
                return _parse_sse_response(body)
            return json.loads(body)
    except HTTPError as exc:
        try:
            exc.read(4096)
        finally:
            exc.close()
        raise AnthropicError(f"Anthropic HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc


class AnthropicMessagesClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: Callable | None = None,
        usage_observer: Callable[[str, dict | None, str], None] | None = None,
        timeout_seconds: float = 180.0,
        max_tokens: int = 8192,
        stream: bool = False,
    ):
        if not api_key or not api_key.strip():
            raise AnthropicError("ANTHROPIC_API_KEY is required for model processing")
        self.api_key = api_key.strip()
        self.transport = transport or _default_transport
        self.usage_observer = usage_observer
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.stream = stream

    def _observe(self, model: str, usage: dict | None, outcome: str) -> None:
        if self.usage_observer is None:
            return
        try:
            self.usage_observer(model, usage, outcome)
        except Exception:
            pass

    def generate_json(
        self,
        model: str,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict,
    ) -> dict:
        del schema_name
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "system": instructions,
            "messages": [{"role": "user", "content": input_text}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": _anthropic_schema(schema),
                }
            },
        }
        if self.stream:
            payload["stream"] = True
        try:
            response = self.transport(
                url,
                headers,
                payload,
                self.timeout_seconds,
            )
        except Exception as exc:
            self._observe(model, None, "transport_error")
            if isinstance(exc, AnthropicError):
                raise
            raise AnthropicError(f"Anthropic request failed: {exc}") from exc
        if not isinstance(response, dict):
            self._observe(model, None, "invalid_response")
            raise AnthropicError("Anthropic response was invalid")
        stop_reason = response.get("stop_reason")
        outcome = (
            stop_reason
            if stop_reason in {"end_turn", "max_tokens", "refusal"}
            else "invalid_response"
        )
        usage = response.get("usage")
        self._observe(model, usage if isinstance(usage, dict) else None, outcome)
        if stop_reason == "refusal":
            raise AnthropicError("Anthropic refused the request")
        if stop_reason == "max_tokens":
            raise AnthropicError("Anthropic response reached the token limit")
        if stop_reason != "end_turn":
            raise AnthropicError(
                f"Anthropic response did not finish safely: {stop_reason}"
            )
        content = response.get("content")
        if not isinstance(content, list):
            raise AnthropicError("Anthropic response contained no text")
        text = next(
            (
                block.get("text")
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ),
            None,
        )
        if not text:
            raise AnthropicError("Anthropic response contained no text")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError(f"Anthropic returned invalid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise AnthropicError("Anthropic structured output must be an object")
        return result
