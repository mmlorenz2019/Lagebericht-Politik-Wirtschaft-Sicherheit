# Anthropic API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the productive OpenAI Responses API integration with the Anthropic Messages API while preserving the validated daily, weekly, and monthly report contracts.

**Architecture:** A focused `AnthropicMessagesClient` keeps the existing `generate_json(...)` boundary and calls the first-party Messages API through Python's standard library. Daily extraction uses Claude Haiku 4.5, final daily and period summaries use Claude Sonnet 4.6, and local validation remains the publication gate.

**Tech Stack:** Python 3.12 standard library, `unittest`, Anthropic Messages API, JSON Schema structured outputs, GitHub Actions, GitHub Pages.

## Global Constraints

- Use the direct Anthropic Messages API; do not add an SDK dependency or a multi-provider runtime switch.
- Use `claude-haiku-4-5-20251001` for extraction and `claude-sonnet-4-6` for selection, summaries, weekly reports, and monthly reports.
- Read the API key only from `ANTHROPIC_API_KEY`; never expose it to the frontend, repository, test fixtures, or logs.
- Use `POST https://api.anthropic.com/v1/messages` with `x-api-key`, `anthropic-version: 2023-06-01`, and `content-type: application/json`.
- Send structured output as `output_config.format` with `type: json_schema`; set no tools, web search, or other actions.
- Preserve all existing frontend, source, report-schema, archive, weekly, and monthly behavior.
- Reject refusal, `max_tokens`, missing text, invalid JSON, HTTP failure, timeout, and local schema/domain validation failure without publishing partial data.
- Keep Python 3.12 and the standard library as the only runtime dependency.

---

## File map

- Create `src/lagebericht/anthropic_client.py`: bounded Anthropic HTTP transport, schema transformation, response parsing, and `AnthropicError`.
- Create `tests/test_anthropic_client.py`: request-contract and failure-mode coverage for the new client.
- Remove `src/lagebericht/openai_client.py` and `tests/test_openai_client.py`: eliminate the obsolete provider integration only after all runtime imports have migrated in Task 2.
- Modify `src/lagebericht/pipeline.py`: Claude defaults for the two daily model roles.
- Modify `src/lagebericht/aggregate.py`: Claude Sonnet default for period reports.
- Modify `scripts/run_daily.py` and `scripts/run_period.py`: Anthropic imports, secret, variables, defaults, and errors.
- Modify `tests/test_pipeline.py`, `tests/test_aggregate.py`, and `tests/test_cli.py`: assert Claude model routing and fail-closed CLI configuration.
- Modify `.github/workflows/daily-report.yml` and `tests/test_workflow_contract.py`: use only the Anthropic secret and model settings.
- Modify `README.md`, `SECURITY.md`, `docs/security-audit-2026-07-31.md`, and `docs/2026-07-31-implementierungsplan.md`: document the live provider and mark the old plan as historical.

### Task 1: Anthropic Messages client

**Files:**
- Create: `tests/test_anthropic_client.py`
- Create: `src/lagebericht/anthropic_client.py`

**Interfaces:**
- Consumes: `model: str`, `instructions: str`, `input_text: str`, `schema_name: str`, and `schema: dict` from the existing pipelines.
- Produces: `AnthropicMessagesClient.generate_json(model, instructions, input_text, schema_name, schema) -> dict` and `AnthropicError(RuntimeError)`.

- [ ] **Step 1: Write failing request-contract and success tests**

Create `tests/test_anthropic_client.py` with a recording transport and assertions equivalent to:

```python
from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from lagebericht.anthropic_client import AnthropicError, AnthropicMessagesClient, _default_transport


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        return self.response


class AnthropicClientTests(unittest.TestCase):
    def test_sends_structured_message_without_tools(self):
        transport = RecordingTransport({
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"ok":true}'}],
        })
        client = AnthropicMessagesClient("secret", transport=transport)

        result = client.generate_json(
            "claude-haiku-4-5-20251001", "Rules", "Input", "example", {"type": "object"}
        )

        self.assertEqual(result, {"ok": True})
        url, headers, payload, timeout = transport.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "secret")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(payload["system"], "Rules")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Input"}])
        self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(payload["output_config"]["format"]["schema"], {"type": "object"})
        self.assertNotIn("tools", payload)
        self.assertGreater(payload["max_tokens"], 0)
        self.assertEqual(timeout, 60.0)
```

- [ ] **Step 2: Run the new test and verify the expected import failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_anthropic_client -v
```

Expected: `ERROR` with `ModuleNotFoundError: No module named 'lagebericht.anthropic_client'`.

- [ ] **Step 3: Add failing schema and response-safety tests**

Add tests that verify unsupported local constraints are removed from the sent schema while the original dictionary is unchanged, and that each unsafe response raises `AnthropicError`:

```python
def test_removes_local_only_schema_constraints_without_mutating_input(self):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/schema.json",
        "type": "object",
        "properties": {"value": {"type": "string", "format": "uri", "maxLength": 20}},
        "required": ["value"],
        "additionalProperties": False,
    }
    original = deepcopy(schema)
    transport = RecordingTransport({"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"value":"ok"}'}]})
    AnthropicMessagesClient("secret", transport=transport).generate_json("model", "R", "I", "x", schema)
    sent = transport.calls[0][2]["output_config"]["format"]["schema"]
    self.assertNotIn("$schema", sent)
    self.assertNotIn("$id", sent)
    self.assertNotIn("format", sent["properties"]["value"])
    self.assertNotIn("maxLength", sent["properties"]["value"])
    self.assertEqual(schema, original)

def test_rejects_missing_key_refusal_limit_missing_text_invalid_json_and_non_object(self):
    with self.assertRaisesRegex(AnthropicError, "ANTHROPIC_API_KEY"):
        AnthropicMessagesClient("")
    unsafe = (
        ({"stop_reason": "refusal", "content": [{"type": "text", "text": "No"}]}, "refused"),
        ({"stop_reason": "max_tokens", "content": [{"type": "text", "text": "{}"}]}, "token limit"),
        ({"stop_reason": "end_turn", "content": []}, "no text"),
        ({"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json"}]}, "invalid JSON"),
        ({"stop_reason": "end_turn", "content": [{"type": "text", "text": "[]"}]}, "must be an object"),
    )
    for response, message in unsafe:
        with self.subTest(message=message), self.assertRaisesRegex(AnthropicError, message):
            AnthropicMessagesClient("secret", transport=RecordingTransport(response)).generate_json("m", "R", "I", "x", {})
```

Add bounded-transport tests with concrete fake responses:

```python
class FakeHttpResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit):
        return self.body[:limit]


class AnthropicTransportTests(unittest.TestCase):
    def test_wraps_http_errors_without_exposing_request_key(self):
        error = HTTPError(
            "https://api.anthropic.com/v1/messages", 400, "Bad Request", {}, BytesIO(b"invalid request")
        )
        with patch("lagebericht.anthropic_client.urlopen", side_effect=error):
            with self.assertRaisesRegex(AnthropicError, "Anthropic HTTP 400") as raised:
                _default_transport("https://api.anthropic.com/v1/messages", {"x-api-key": "secret"}, {}, 1.0)
        self.assertNotIn("secret", str(raised.exception))

    def test_wraps_network_and_timeout_errors(self):
        for error in (URLError("offline"), TimeoutError("late")):
            with self.subTest(error=type(error).__name__):
                with patch("lagebericht.anthropic_client.urlopen", side_effect=error):
                    with self.assertRaisesRegex(AnthropicError, "request failed"):
                        _default_transport("https://api.anthropic.com/v1/messages", {}, {}, 1.0)

    def test_rejects_response_over_two_megabytes(self):
        response = FakeHttpResponse(b"x" * 2_000_001)
        with patch("lagebericht.anthropic_client.urlopen", return_value=response):
            with self.assertRaisesRegex(AnthropicError, "size limit"):
                _default_transport("https://api.anthropic.com/v1/messages", {}, {}, 1.0)
```

- [ ] **Step 4: Implement the minimal standard-library client**

Create `src/lagebericht/anthropic_client.py` with this shape:

```python
from __future__ import annotations

import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AnthropicError(RuntimeError):
    """Raised when the Messages API does not return safe structured output."""


_LOCAL_ONLY_SCHEMA_KEYS = {
    "$schema", "$id", "format", "pattern", "minLength", "maxLength",
    "minItems", "maxItems", "uniqueItems", "minimum", "maximum",
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


def _default_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise AnthropicError("Anthropic response exceeded size limit")
            return json.loads(body)
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace")
        raise AnthropicError(f"Anthropic HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AnthropicError(f"Anthropic request failed: {exc}") from exc


class AnthropicMessagesClient:
    def __init__(self, api_key: str, *, transport: Callable | None = None,
                 timeout_seconds: float = 60.0, max_tokens: int = 8192):
        if not api_key or not api_key.strip():
            raise AnthropicError("ANTHROPIC_API_KEY is required for model processing")
        self.api_key = api_key.strip()
        self.transport = transport or _default_transport
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    def generate_json(self, model: str, instructions: str, input_text: str,
                      schema_name: str, schema: dict) -> dict:
        del schema_name  # Kept only for compatibility with the pipeline boundary.
        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "system": instructions,
            "messages": [{"role": "user", "content": input_text}],
            "output_config": {
                "format": {"type": "json_schema", "schema": _anthropic_schema(schema)}
            },
        }
        response = self.transport(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload,
            self.timeout_seconds,
        )
        if not isinstance(response, dict):
            raise AnthropicError("Anthropic response was invalid")
        stop_reason = response.get("stop_reason")
        if stop_reason == "refusal":
            raise AnthropicError("Anthropic refused the request")
        if stop_reason == "max_tokens":
            raise AnthropicError("Anthropic response reached the token limit")
        if stop_reason != "end_turn":
            raise AnthropicError(f"Anthropic response did not finish safely: {stop_reason}")
        text = next(
            (block.get("text") for block in response.get("content", []) if block.get("type") == "text"),
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
```

- [ ] **Step 5: Run the focused client suite until green**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_anthropic_client -v
```

Expected: all Anthropic client tests pass, including transport error tests.

- [ ] **Step 6: Commit the independently testable Anthropic client**

Keep the old client temporarily because the existing scripts still import it until Task 2. Commit only the new client and its tests:

```powershell
git add src/lagebericht/anthropic_client.py tests/test_anthropic_client.py
git commit -m "feat: add structured Anthropic client"
```

### Task 2: Route daily and period generation through Claude

**Files:**
- Modify: `src/lagebericht/pipeline.py`
- Modify: `src/lagebericht/aggregate.py`
- Modify: `scripts/run_daily.py`
- Modify: `scripts/run_period.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_aggregate.py`
- Modify: `tests/test_cli.py`
- Remove: `src/lagebericht/openai_client.py`
- Remove: `tests/test_openai_client.py`

**Interfaces:**
- Consumes: `AnthropicMessagesClient` and `AnthropicError` from Task 1.
- Produces: daily and period CLIs configured by `ANTHROPIC_API_KEY`, `ANTHROPIC_EXTRACTION_MODEL`, and `ANTHROPIC_SUMMARY_MODEL`.

- [ ] **Step 1: Change model-routing tests first**

In `tests/test_pipeline.py`, change the expected defaults to:

```python
self.assertEqual(ai.models, ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"])
```

Extend `ContentAI` in `tests/test_aggregate.py` to record models and assert:

```python
self.assertEqual(ai.models, ["claude-sonnet-4-6"])
```

In `tests/test_cli.py`, remove `ANTHROPIC_API_KEY` from the subprocess environment and assert the fail-closed message names that exact variable. Also remove any inherited `OPENAI_API_KEY` so it cannot make the test pass accidentally.

- [ ] **Step 2: Run the routing and CLI tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_pipeline tests.test_aggregate tests.test_cli -v
```

Expected: failures show the old GPT defaults and `OPENAI_API_KEY` message/imports.

- [ ] **Step 3: Replace runtime imports, defaults, and environment variables**

Use these exact defaults:

```python
# src/lagebericht/pipeline.py
extraction_model: str = "claude-haiku-4-5-20251001"
summary_model: str = "claude-sonnet-4-6"

# src/lagebericht/aggregate.py
model: str = "claude-sonnet-4-6"
```

In both scripts import:

```python
from lagebericht.anthropic_client import AnthropicError, AnthropicMessagesClient
```

In `scripts/run_daily.py`, use:

```python
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("ANTHROPIC_API_KEY fehlt; es wurde nichts veröffentlicht.", file=sys.stderr)
    return 2
client = AnthropicMessagesClient(api_key)
extraction_model = os.environ.get("ANTHROPIC_EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
summary_model = os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6")
```

In `scripts/run_period.py`, use the same secret/client and:

```python
model = os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6")
```

Catch `AnthropicError` in place of `OpenAIError`. Do not retain fallback reads of `OPENAI_API_KEY` or old model variables.

After all runtime imports use `lagebericht.anthropic_client`, remove `src/lagebericht/openai_client.py` and its replaced test file `tests/test_openai_client.py`.

- [ ] **Step 4: Run the focused suites and verify green**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_anthropic_client tests.test_pipeline tests.test_aggregate tests.test_cli -v
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the runtime migration**

```powershell
git add src/lagebericht/pipeline.py src/lagebericht/aggregate.py src/lagebericht/openai_client.py scripts/run_daily.py scripts/run_period.py tests/test_openai_client.py tests/test_pipeline.py tests/test_aggregate.py tests/test_cli.py
git commit -m "feat: route reports through Claude models"
```

### Task 3: Migrate GitHub Actions and operating documentation

**Files:**
- Modify: `.github/workflows/daily-report.yml`
- Modify: `tests/test_workflow_contract.py`
- Modify: `README.md`
- Modify: `SECURITY.md`
- Modify: `docs/security-audit-2026-07-31.md`
- Modify: `docs/2026-07-31-implementierungsplan.md`

**Interfaces:**
- Consumes: environment-variable and model names from Task 2.
- Produces: a workflow that requires only `secrets.ANTHROPIC_API_KEY` and documentation matching the deployed system.

- [ ] **Step 1: Write the failing workflow contract**

Replace the provider-specific assertions in `tests/test_workflow_contract.py` with:

```python
def test_daily_workflow_uses_anthropic_secret_models_and_two_dst_crons(self):
    text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
    self.assertIn("secrets.ANTHROPIC_API_KEY", text)
    self.assertIn("ANTHROPIC_EXTRACTION_MODEL: claude-haiku-4-5-20251001", text)
    self.assertIn("ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6", text)
    self.assertNotIn("OPENAI_", text)
    self.assertIn("30 4 * * *", text)
    self.assertIn("30 5 * * *", text)
    self.assertIn("Europe/Berlin", text)
    self.assertNotIn("pull_request:", text)
```

- [ ] **Step 2: Run the workflow contract and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract -v
```

Expected: failure because the workflow still references the OpenAI secret and models.

- [ ] **Step 3: Update the GitHub Actions environment**

For daily generation set:

```yaml
env:
  PYTHONPATH: src
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  ANTHROPIC_EXTRACTION_MODEL: claude-haiku-4-5-20251001
  ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6
```

For weekly and monthly generation set only the secret plus `ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6`. Preserve conditions, `continue-on-error`, permissions, pinned action SHAs, schedules, and publishing steps exactly.

- [ ] **Step 4: Run workflow tests and verify green**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract -v
```

Expected: all workflow-contract tests pass.

- [ ] **Step 5: Update the live documentation with exact setup instructions**

Update `README.md` so its local example uses:

```powershell
$env:ANTHROPIC_API_KEY='...'
$env:PYTHONPATH='src'
python scripts/run_daily.py --date 2026-07-31 --dry-run
```

Name the direct Messages API, structured outputs through `output_config.format`, no tools, the two Claude defaults, and the override variables. Replace the GitHub setup steps with creating an Anthropic project key, setting a spending limit in the Anthropic Console, and saving only `ANTHROPIC_API_KEY` under Actions secrets.

Update `SECURITY.md` and `docs/security-audit-2026-07-31.md` to name Anthropic instead of OpenAI while preserving the existing security boundary. Add this notice near the top of `docs/2026-07-31-implementierungsplan.md`:

```markdown
> **Historischer Stand:** Dieser ursprüngliche Plan beschreibt die erste OpenAI-Implementierung. Die produktive Migration auf Anthropic ist in `docs/superpowers/specs/2026-07-31-anthropic-migration-design.md` und `docs/superpowers/plans/2026-07-31-anthropic-migration.md` festgelegt.
```

- [ ] **Step 6: Scan active files for stale provider configuration**

Run:

```powershell
rg -n "OPENAI_API_KEY|OPENAI_EXTRACTION_MODEL|OPENAI_SUMMARY_MODEL|openai_client" . -g "!docs/2026-07-31-implementierungsplan.md" -g "!docs/superpowers/specs/2026-07-31-anthropic-migration-design.md" -g "!docs/superpowers/plans/2026-07-31-anthropic-migration.md"
```

Expected: no matches. Historical prose mentioning the earlier migration target is allowed only in the explicitly excluded planning/specification files.

- [ ] **Step 7: Commit workflow and documentation**

```powershell
git add .github/workflows/daily-report.yml tests/test_workflow_contract.py README.md SECURITY.md docs/security-audit-2026-07-31.md docs/2026-07-31-implementierungsplan.md
git commit -m "docs: configure Anthropic production setup"
```

### Task 4: Full verification and deployment handoff

**Files:**
- Verify: all repository files
- Modify only if verification exposes a defect covered by the approved specification.

**Interfaces:**
- Consumes: completed client, runtime, workflow, tests, and documentation from Tasks 1–3.
- Produces: a pushed `main` branch ready for the user to add the Anthropic secret and start a supervised production run.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

Expected: every test passes with no skips or errors.

- [ ] **Step 2: Run repository consistency and secret scans**

Run:

```powershell
git diff --check
rg -n "sk-ant-|ANTHROPIC_API_KEY\s*[:=]\s*['\"][^$]" . -g "!docs/superpowers/**"
rg -n "OPENAI_API_KEY|OPENAI_EXTRACTION_MODEL|OPENAI_SUMMARY_MODEL|openai_client" . -g "!docs/2026-07-31-implementierungsplan.md" -g "!docs/superpowers/**"
```

Expected: `git diff --check` exits successfully and both scans return no matches. The absence of a real API key is mandatory.

- [ ] **Step 3: Review the final diff against every success criterion**

Confirm from the diff that:

```text
[x] no active OpenAI runtime or workflow configuration remains
[x] only ANTHROPIC_API_KEY is required
[x] Haiku handles extraction and Sonnet handles summaries
[x] structured output and local validation both remain active
[x] no frontend or report-data behavior changed
[x] errors cannot publish partial output
```

- [ ] **Step 4: Commit any verification-only correction, then push**

If Step 1–3 required a correction, rerun the focused failing test first, then the full suite, and commit only the correction:

```powershell
git add -- src/lagebericht/anthropic_client.py src/lagebericht/pipeline.py src/lagebericht/aggregate.py scripts/run_daily.py scripts/run_period.py tests/test_anthropic_client.py tests/test_pipeline.py tests/test_aggregate.py tests/test_cli.py tests/test_workflow_contract.py .github/workflows/daily-report.yml README.md SECURITY.md docs/security-audit-2026-07-31.md docs/2026-07-31-implementierungsplan.md
git commit -m "fix: complete Anthropic migration verification"
git push origin main
```

If no correction was needed, push the three existing task commits directly with `git push origin main`.

- [ ] **Step 5: User-only secret setup and supervised live run**

Ask Michael to create or copy an Anthropic project API key without posting it in chat, then add it at:

```text
GitHub repository → Settings → Secrets and variables → Actions
Name: ANTHROPIC_API_KEY
Value: the private Anthropic project key
```

After the secret exists, manually run **Actions → Täglicher Lagebericht → Run workflow**. Verify that the job succeeds, the generated `data/daily/YYYY-MM-DD.json` passes the schema tests, no secret appears in logs, GitHub Pages deploys the commit, and the live app shows the new report. Record the observed token/cost usage from the Anthropic Console as the initial cost baseline.

## Official API references

- Anthropic Messages API: https://platform.claude.com/docs/en/api/messages
- Structured outputs and failure cases: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Model IDs and versioning: https://platform.claude.com/docs/en/about-claude/models/overview
