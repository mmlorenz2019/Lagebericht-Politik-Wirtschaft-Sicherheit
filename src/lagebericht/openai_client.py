from __future__ import annotations

import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAIError(RuntimeError):
    """Raised when the Responses API does not return safe structured output."""


_LOCAL_ONLY_SCHEMA_KEYS = {
    "$schema", "$id", "format", "pattern", "minLength", "maxLength",
    "minItems", "maxItems", "uniqueItems", "minimum", "maximum",
}


def _response_schema(value):
    if isinstance(value, dict):
        return {key: _response_schema(item) for key, item in value.items() if key not in _LOCAL_ONLY_SCHEMA_KEYS}
    if isinstance(value, list):
        return [_response_schema(item) for item in value]
    return value


def _default_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise OpenAIError("OpenAI response exceeded size limit")
            return json.loads(body)
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace")
        raise OpenAIError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise OpenAIError(f"OpenAI request failed: {exc}") from exc


class OpenAIResponsesClient:
    def __init__(self, api_key: str, *, transport: Callable | None = None, timeout_seconds: float = 60.0):
        if not api_key or not api_key.strip():
            raise OpenAIError("OPENAI_API_KEY is required for model processing")
        self.api_key = api_key.strip()
        self.transport = transport or _default_transport
        self.timeout_seconds = timeout_seconds

    def generate_json(self, model: str, instructions: str, input_text: str, schema_name: str, schema: dict) -> dict:
        payload = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": _response_schema(schema),
                    "strict": True,
                }
            },
        }
        response = self.transport(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload,
            self.timeout_seconds,
        )
        if not isinstance(response, dict) or response.get("status") != "completed":
            raise OpenAIError(f"OpenAI response was not completed: {response.get('status') if isinstance(response, dict) else 'invalid'}")
        output_text: str | None = None
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "refusal":
                    raise OpenAIError(f"OpenAI refused the request: {part.get('refusal', '')}")
                if part.get("type") == "output_text":
                    output_text = part.get("text")
        if not output_text:
            raise OpenAIError("OpenAI response contained no output_text")
        try:
            result = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIError(f"OpenAI returned invalid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise OpenAIError("OpenAI structured output must be an object")
        return result
