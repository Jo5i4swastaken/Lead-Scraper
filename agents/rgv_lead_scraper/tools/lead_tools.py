from __future__ import annotations

import asyncio
from typing import Any, Literal

from omniagents import function_tool

from lead_scraper.config.settings import load_settings
from lead_scraper.enrichers.noop import NoopEnricher
from lead_scraper.export.csv_export import CsvExporter
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.pipeline import run_enrich, run_scrape, run_score
from lead_scraper.scorers.simple import SimpleHeuristicScorer
from lead_scraper.scrapers.serpapi_maps import SerpApiGoogleMapsScraper


@function_tool
def get_settings_summary(config_path: str) -> dict[str, Any]:
    """Load settings and return a safe summary (no secrets)."""
    settings = load_settings(config_path)
    return {
        "config_path": config_path,
        "cities": settings.cities,
        "categories": settings.categories,
        "serpapi": {
            "engine": settings.serpapi.engine,
            "rate_limit_per_sec": settings.serpapi.rate_limit_per_sec,
            "concurrency": settings.serpapi.concurrency,
            "timeout_sec": settings.serpapi.timeout_sec,
        },
        "export": {
            "out_dir": settings.export.out_dir,
            "jsonl_name": settings.export.jsonl_name,
            "csv_name": settings.export.csv_name,
        },
    }


@function_tool
def run_pipeline(
    config_path: str,
    export_format: Literal["jsonl", "csv", "both"] = "both",
) -> dict[str, Any]:
    """Run scrape -> enrich -> score -> export and return output paths + counts."""
    settings = load_settings(config_path)
    leads = asyncio.run(_scrape(settings))
    leads = asyncio.run(run_enrich(enricher=NoopEnricher(), leads=leads))
    leads = run_score(scorer=SimpleHeuristicScorer(), leads=leads)

    outputs: dict[str, str] = {}
    if export_format in ("jsonl", "both"):
        outputs["jsonl"] = JsonlExporter(f"{settings.export.out_dir}/{settings.export.jsonl_name}").export(leads)
    if export_format in ("csv", "both"):
        outputs["csv"] = CsvExporter(f"{settings.export.out_dir}/{settings.export.csv_name}").export(leads)

    return {"lead_count": len(leads), "outputs": outputs}


@function_tool
def run_stage(
    config_path: str,
    stage: Literal["scrape", "enrich", "score", "export"],
    export_format: Literal["jsonl", "csv"] = "jsonl",
) -> dict[str, Any]:
    """Run a single stage (later stages may implicitly depend on earlier ones)."""
    settings = load_settings(config_path)

    if stage == "scrape":
        leads = asyncio.run(_scrape(settings))
        return {"stage": "scrape", "lead_count": len(leads)}

    leads = asyncio.run(_scrape(settings))

    if stage == "enrich":
        leads = asyncio.run(run_enrich(enricher=NoopEnricher(), leads=leads))
        return {"stage": "enrich", "lead_count": len(leads)}

    leads = asyncio.run(run_enrich(enricher=NoopEnricher(), leads=leads))

    if stage == "score":
        leads = run_score(scorer=SimpleHeuristicScorer(), leads=leads)
        return {"stage": "score", "lead_count": len(leads)}

    leads = run_score(scorer=SimpleHeuristicScorer(), leads=leads)

    if export_format == "jsonl":
        out = JsonlExporter(f"{settings.export.out_dir}/{settings.export.jsonl_name}").export(leads)
        return {"stage": "export", "lead_count": len(leads), "output": out}

    out = CsvExporter(f"{settings.export.out_dir}/{settings.export.csv_name}").export(leads)
    return {"stage": "export", "lead_count": len(leads), "output": out}


async def _scrape(settings):
    scraper = SerpApiGoogleMapsScraper(settings.serpapi)
    return await run_scrape(settings=settings, scraper=scraper)
