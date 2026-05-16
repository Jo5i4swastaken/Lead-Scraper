from __future__ import annotations

from pathlib import Path

from lead_scraper.export.csv_export import CsvExporter
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.export.sqlite import SqliteExporter
from lead_scraper.models import Lead


def filter_leads(
    leads: list[Lead], *, only_qualified: bool = False, min_score: float | None = None
) -> list[Lead]:
    out: list[Lead] = []
    for lead in leads:
        if only_qualified and lead.qualified is not True:
            continue
        if min_score is not None:
            score = lead.lead_score
            if score is None or score < min_score:
                continue
        out.append(lead)
    return out


def export_leads(
    leads: list[Lead],
    *,
    fmt: str,
    out_path: str,
    incremental: bool = True,
    only_qualified: bool = False,
    min_score: float | None = None,
) -> dict[str, str]:
    filtered = filter_leads(leads, only_qualified=only_qualified, min_score=min_score)
    out: dict[str, str] = {}
    path = Path(out_path)

    if fmt == "csv":
        out["csv"] = CsvExporter(str(path), incremental=incremental).export(filtered)
        return out
    if fmt == "jsonl":
        out["jsonl"] = JsonlExporter(str(path), incremental=incremental).export(filtered)
        return out
    if fmt == "sqlite":
        out["sqlite"] = SqliteExporter(str(path)).export(filtered)
        return out
    if fmt == "both":
        if path.suffix:
            base = path.with_suffix("")
            csv_path = str(base) + ".csv"
            jsonl_path = str(base) + ".jsonl"
        else:
            path.mkdir(parents=True, exist_ok=True)
            csv_path = str(path / "leads.csv")
            jsonl_path = str(path / "leads.jsonl")
        out["jsonl"] = JsonlExporter(jsonl_path, incremental=incremental).export(filtered)
        out["csv"] = CsvExporter(csv_path, incremental=incremental).export(filtered)
        return out

    raise ValueError(f"unsupported export format: {fmt}")
