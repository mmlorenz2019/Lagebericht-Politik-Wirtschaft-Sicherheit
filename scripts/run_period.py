from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from lagebericht.aggregate import PeriodAggregator
from lagebericht.config import all_allowed_domains, load_sources
from lagebericht.costs import CostRecorder, context_from_environment
from lagebericht.anthropic_client import AnthropicError, AnthropicMessagesClient
from lagebericht.publish import Publisher
from lagebericht.schedule import berlin_now
from lagebericht.translate import TranslationError, publish_translation


ROOT = Path(__file__).parents[1]


def week_report_id(end_date: date) -> str:
    iso_year, iso_week, _ = end_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def month_report_id(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%Y-%m")


def build_period_usage_observer(
    data_root: Path,
    report_type: str,
    report_id: str,
    *,
    environ=None,
):
    """Return a recorder callback, or no callback when setup is unavailable."""
    try:
        context = context_from_environment(report_type, report_id, environ)
        recorder = CostRecorder(
            data_root, ROOT / "config" / "api-pricing.json", context
        )
        return recorder.observe
    except Exception:
        return None


def build_period_client(
    api_key: str, *, usage_observer=None, transport=None
) -> AnthropicMessagesClient:
    options = {
        "max_tokens": int(os.environ.get("ANTHROPIC_PERIOD_MAX_TOKENS", "16384")),
        "timeout_seconds": float(os.environ.get("ANTHROPIC_PERIOD_TIMEOUT_SECONDS", "600")),
        "usage_observer": usage_observer,
    }
    if transport is not None:
        options["transport"] = transport
    return AnthropicMessagesClient(api_key, **options)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Erzeugt einen Wochen- oder Monatsbericht aus validierten Tagesberichten.")
    parser.add_argument("mode", choices=("week", "month"))
    parser.add_argument("--end-date", type=date.fromisoformat, help="Sonntag des Wochenberichts als YYYY-MM-DD")
    parser.add_argument("--month", help="Monat als YYYY-MM")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--sources", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY fehlt; es wurde nichts veröffentlicht.", file=sys.stderr)
        return 2
    try:
        sources = load_sources(args.sources)
        domains = all_allowed_domains(sources)
        today = berlin_now().date()
        if args.mode == "week":
            period_end = args.end_date or today
            report_id = week_report_id(period_end)
        else:
            year, month = map(
                int, (args.month or today.strftime("%Y-%m")).split("-")
            )
            report_id = month_report_id(year, month)
        observer = build_period_usage_observer(
            args.data_root, args.mode, report_id
        )
        client = build_period_client(api_key, usage_observer=observer)
        aggregator = PeriodAggregator(
            args.data_root,
            client,
            domains,
            model=os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6"),
        )
        if args.mode == "week":
            report = aggregator.build_week(period_end)
        else:
            report = aggregator.build_month(year, month)
        if report is None:
            print("Keine gültigen Tagesberichte für diesen Zeitraum; Claude wurde nicht aufgerufen.", file=sys.stderr)
            return 3
        if args.dry_run:
            import json
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(Publisher(args.data_root, domains).publish_period(report))
            try:
                en_path = publish_translation(
                    report,
                    client,
                    domains,
                    ROOT / "schemas" / "period-report.schema.json",
                    args.data_root,
                    "publish_period",
                    model=os.environ.get("ANTHROPIC_TRANSLATION_MODEL", "claude-haiku-4-5-20251001"),
                )
                print(en_path)
            except TranslationError as exc:
                print(f"Übersetzung fehlgeschlagen, Rückblick bleibt veröffentlicht: {exc}", file=sys.stderr)
        return 0
    except (AnthropicError, ValueError, OSError) as exc:
        print(f"Rückblick fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
