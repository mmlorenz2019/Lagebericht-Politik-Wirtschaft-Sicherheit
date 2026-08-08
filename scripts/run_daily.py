from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from lagebericht.config import all_allowed_domains, load_sources
from lagebericht.costs import CostRecorder, context_from_environment
from lagebericht.fetch import SafeFetcher
from lagebericht.anthropic_client import AnthropicError, AnthropicMessagesClient
from lagebericht.pipeline import DailyPipeline, PipelineError
from lagebericht.publish import Publisher
from lagebericht.schedule import berlin_now
from lagebericht.translate import TranslationError, publish_translation


ROOT = Path(__file__).parents[1]


def build_daily_client(
    api_key: str,
    data_root: Path,
    report_date: date,
    *,
    transport=None,
    environ=None,
) -> AnthropicMessagesClient:
    """Build a paid client while keeping cost setup failures non-fatal."""
    observer = None
    try:
        context = context_from_environment("daily", report_date.isoformat(), environ)
        recorder = CostRecorder(
            data_root, ROOT / "config" / "api-pricing.json", context
        )
        observer = recorder.observe
    except Exception:
        pass
    options = {"usage_observer": observer}
    if transport is not None:
        options["transport"] = transport
    return AnthropicMessagesClient(api_key, **options)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Erzeugt einen validierten Tagesbericht.")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Berichtsdatum im Format YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Bericht prüfen und ausgeben, aber nicht speichern")
    parser.add_argument("--sources", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY fehlt; es wurde nichts veröffentlicht.", file=sys.stderr)
        return 2
    try:
        report_date = args.date or berlin_now().date()
        sources = load_sources(args.sources)
        allowed_domains = all_allowed_domains(sources)
        client = build_daily_client(api_key, args.data_root, report_date)
        pipeline = DailyPipeline(
            sources,
            SafeFetcher(),
            client,
            allowed_domains,
            extraction_model=os.environ.get("ANTHROPIC_EXTRACTION_MODEL", "claude-haiku-4-5-20251001"),
            summary_model=os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6"),
        )
        report = pipeline.run(report_date)
        if args.dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            path = Publisher(args.data_root, allowed_domains).publish_daily(report)
            print(path)
            try:
                en_path = publish_translation(
                    report,
                    client,
                    allowed_domains,
                    ROOT / "schemas" / "daily-report.schema.json",
                    args.data_root,
                    "publish_daily",
                    model=os.environ.get("ANTHROPIC_TRANSLATION_MODEL", "claude-haiku-4-5-20251001"),
                )
                print(en_path)
            except TranslationError as exc:
                print(f"Übersetzung fehlgeschlagen, deutscher Bericht bleibt veröffentlicht: {exc}", file=sys.stderr)
        return 0
    except (AnthropicError, PipelineError, ValueError, OSError) as exc:
        print(f"Tageslauf fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
