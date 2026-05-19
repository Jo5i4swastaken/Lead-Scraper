from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from omniagents import function_tool

from lead_scraper.config.settings import Settings, load_settings
from lead_scraper.enrichers.noop import NoopEnricher
from lead_scraper.export.csv_export import CsvExporter
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.pipeline import run_enrich, run_scrape, run_score
from lead_scraper.scorers.simple import SimpleHeuristicScorer
from lead_scraper.scrapers.maps_serpapi import SerpApiGoogleMapsScraper


def _resolved_settings(
    config_path: str | None,
    city: str | None,
    category: str | None,
) -> Settings:
    settings = load_settings(config_path)
    cities = [city] if city else settings.cities
    categories = [category] if category else settings.categories
    return replace(settings, cities=cities, categories=categories)


@function_tool
def get_settings_summary(
    config_path: str | None = None,
    city: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Load settings (with optional city/category overrides) and return a safe summary (no secrets)."""
    settings = _resolved_settings(config_path, city, category)
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
async def run_pipeline(
    city: str | None = None,
    category: str | None = None,
    export_format: Literal["jsonl", "csv", "both"] = "both",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Run scrape -> enrich -> score -> export and return output paths + counts.

    Pass `city` and `category` straight from the user's prompt (e.g. city="McAllen",
    category="plumbers"). When omitted, falls back to the cities/categories lists in
    the config file for batch runs.
    """
    settings = _resolved_settings(config_path, city, category)
    leads = await _scrape(settings)
    leads = await run_enrich(enricher=NoopEnricher(), leads=leads)
    leads = run_score(scorer=SimpleHeuristicScorer(), leads=leads)

    outputs: dict[str, str] = {}
    if export_format in ("jsonl", "both"):
        outputs["jsonl"] = JsonlExporter(f"{settings.export.out_dir}/{settings.export.jsonl_name}").export(leads)
    if export_format in ("csv", "both"):
        outputs["csv"] = CsvExporter(f"{settings.export.out_dir}/{settings.export.csv_name}").export(leads)

    return {"lead_count": len(leads), "outputs": outputs}


@function_tool
async def run_stage(
    stage: Literal["scrape", "enrich", "score", "export"],
    city: str | None = None,
    category: str | None = None,
    export_format: Literal["jsonl", "csv"] = "jsonl",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Run a single stage (later stages may implicitly depend on earlier ones).

    Pass `city` and `category` for ad-hoc targets; falls back to the config lists otherwise.
    """
    settings = _resolved_settings(config_path, city, category)

    if stage == "scrape":
        leads = await _scrape(settings)
        return {"stage": "scrape", "lead_count": len(leads)}

    leads = await _scrape(settings)

    if stage == "enrich":
        leads = await run_enrich(enricher=NoopEnricher(), leads=leads)
        return {"stage": "enrich", "lead_count": len(leads)}

    leads = await run_enrich(enricher=NoopEnricher(), leads=leads)

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
    from pathlib import Path

    trace_dir = Path(settings.export.out_dir) / "trace" / "maps_serpapi"
    scraper = SerpApiGoogleMapsScraper(settings.serpapi, trace_dir=trace_dir)
    return await run_scrape(settings=settings, scraper=scraper)
