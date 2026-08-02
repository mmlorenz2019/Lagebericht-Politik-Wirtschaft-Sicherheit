from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from lagebericht.aggregate import PeriodAggregator
from lagebericht.config import all_allowed_domains, load_sources
from lagebericht.anthropic_client import AnthropicError, AnthropicMessagesClient
from lagebericht.publish import Publisher
from lagebericht.schedule import berlin_now


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
        aggregator = PeriodAggregator(
            args.data_root,
            AnthropicMessagesClient(api_key),
            domains,
            model=os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6"),
        )
        today = berlin_now().date()
        if args.mode == "week":
            report = aggregator.build_week(args.end_date or today)
        else:
            year, month = map(int, (args.month or today.strftime("%Y-%m")).split("-"))
            report = aggregator.build_month(year, month)
        if report is None:
            print("Keine gültigen Tagesberichte für diesen Zeitraum; Claude wurde nicht aufgerufen.", file=sys.stderr)
            return 3
        if args.dry_run:
            import json
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(Publisher(args.data_root, domains).publish_period(report))
        return 0
    except (AnthropicError, ValueError, OSError) as exc:
        print(f"Rückblick fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
