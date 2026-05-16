from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SerpApiSettings:
    engine: str
    rate_limit_per_sec: float
    concurrency: int
    timeout_sec: int


@dataclass(frozen=True, slots=True)
class ExportSettings:
    out_dir: str
    jsonl_name: str
    csv_name: str


@dataclass(frozen=True, slots=True)
class Settings:
    cities: list[str]
    categories: list[str]
    serpapi: SerpApiSettings
    export: ExportSettings
    scoring: dict[str, object]


def load_settings(config_path: str | None = None) -> Settings:
    resolved = config_path or os.environ.get("LEAD_SCRAPER_CONFIG_PATH") or "config/config.json"
    path = Path(resolved)
    raw = json.loads(path.read_text(encoding="utf-8"))

    serpapi_raw = raw.get("serpapi", {})
    export_raw = raw.get("export", {})
    scoring_raw = raw.get("scoring", {})

    serpapi = SerpApiSettings(
        engine=str(serpapi_raw.get("engine", "google_maps")),
        rate_limit_per_sec=float(serpapi_raw.get("rate_limit_per_sec", 1.0)),
        concurrency=int(serpapi_raw.get("concurrency", 4)),
        timeout_sec=int(serpapi_raw.get("timeout_sec", 30)),
    )
    export = ExportSettings(
        out_dir=str(export_raw.get("out_dir", "out")),
        jsonl_name=str(export_raw.get("jsonl_name", "leads.jsonl")),
        csv_name=str(export_raw.get("csv_name", "leads.csv")),
    )

    return Settings(
        cities=list(raw.get("cities", [])),
        categories=list(raw.get("categories", [])),
        serpapi=serpapi,
        export=export,
        scoring=dict(scoring_raw) if isinstance(scoring_raw, dict) else {},
    )


def require_serpapi_api_key() -> str:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY is required (set via environment variable)")
    return api_key
