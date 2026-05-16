from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from lead_scraper.config.settings import load_settings
from lead_scraper.enrichers.noop import NoopEnricher
from lead_scraper.export.csv_export import CsvExporter
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.logging_utils import configure_logging
from lead_scraper.pipeline import run_enrich, run_scrape, run_score
from lead_scraper.scorers.simple import SimpleHeuristicScorer
from lead_scraper.scrapers.maps_serpapi import SerpApiGoogleMapsScraper

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="lead-scraper")
    parser.add_argument("--config", default=None)
    parser.add_argument("--log-level", default="INFO")

    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run end-to-end pipeline")
    run_cmd.add_argument("--export-format", choices=["jsonl", "csv", "both"], default="both")

    stage_cmd = sub.add_parser("stage", help="Run a single stage")
    stage_cmd.add_argument("name", choices=["scrape", "enrich", "score", "export"])
    stage_cmd.add_argument("--export-format", choices=["jsonl", "csv"], default="jsonl")

    args = parser.parse_args()
    configure_logging(args.log_level)

    settings = load_settings(args.config)

    if args.command == "run":
        leads = asyncio.run(_stage_scrape(settings))
        leads = asyncio.run(_stage_enrich(leads))
        leads = _stage_score(leads)
        out = _stage_export(settings, leads, fmt=args.export_format)
        logger.info("done: %s", out)
        return

    if args.command == "stage":
        if args.name == "scrape":
            asyncio.run(_stage_scrape(settings))
            return
        if args.name == "enrich":
            leads = asyncio.run(_stage_scrape(settings))
            asyncio.run(_stage_enrich(leads))
            return
        if args.name == "score":
            leads = asyncio.run(_stage_scrape(settings))
            leads = asyncio.run(_stage_enrich(leads))
            _stage_score(leads)
            return
        if args.name == "export":
            leads = asyncio.run(_stage_scrape(settings))
            leads = asyncio.run(_stage_enrich(leads))
            leads = _stage_score(leads)
            _stage_export(settings, leads, fmt=args.export_format)
            return


if __name__ == "__main__":
    main()


async def _stage_scrape(settings):
    trace_dir = Path(settings.export.out_dir) / "trace" / "maps_serpapi"
    scraper = SerpApiGoogleMapsScraper(settings.serpapi, trace_dir=trace_dir)
    return await run_scrape(settings=settings, scraper=scraper)


async def _stage_enrich(leads):
    return await run_enrich(enricher=NoopEnricher(), leads=leads)


def _stage_score(leads):
    return run_score(scorer=SimpleHeuristicScorer(), leads=leads)


def _stage_export(settings, leads, *, fmt: str):
    out_dir = Path(settings.export.out_dir)
    outputs: dict[str, str] = {}

    if fmt in ("jsonl", "both"):
        outputs["jsonl"] = JsonlExporter(str(out_dir / settings.export.jsonl_name)).export(leads)
    if fmt in ("csv", "both"):
        outputs["csv"] = CsvExporter(str(out_dir / settings.export.csv_name)).export(leads)

    logger.info("export complete: %s", outputs)
    return outputs
