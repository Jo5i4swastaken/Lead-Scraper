from __future__ import annotations

import csv
import json
from pathlib import Path

from lead_scraper.export.identity import lead_identity
from lead_scraper.export.schema import CSV_COLUMNS, lead_to_export_dict
from lead_scraper.models import Lead


class CsvExporter:
    def __init__(self, out_path: str, *, incremental: bool = True):
        self._out_path = Path(out_path)
        self._incremental = incremental

    def export(self, leads: list[Lead]) -> str:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)

        existing_ids: set[str] = set()
        existing_rows: list[dict[str, str]] | None = None
        needs_rewrite = False

        if self._incremental and self._out_path.exists():
            with self._out_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if list(reader.fieldnames or []) != list(CSV_COLUMNS):
                    needs_rewrite = True
                    existing_rows = []
                for row in reader:
                    key = str(row.get("lead_id") or "").strip()
                    if key:
                        existing_ids.add(key)
                    if existing_rows is not None:
                        existing_rows.append(dict(row))

        to_write: list[dict[str, object]] = []
        seen_this_run: set[str] = set()
        for lead in leads:
            key = lead_identity(lead)
            if key in existing_ids or key in seen_this_run:
                continue
            seen_this_run.add(key)
            to_write.append(lead_to_export_dict(lead))

        if needs_rewrite:
            all_rows: list[dict[str, object]] = []
            if existing_rows:
                for row in existing_rows:
                    normalized: dict[str, object] = {}
                    for col in CSV_COLUMNS:
                        value = row.get(col)
                        if col in {"social_links_json", "flags_json", "evidence_json"}:
                            try:
                                normalized[col] = json.loads(value) if value else {}
                            except Exception:
                                normalized[col] = value
                        else:
                            normalized[col] = value
                    all_rows.append(normalized)
            all_rows.extend(to_write)
            with self._out_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
                writer.writeheader()
                for row in all_rows:
                    writer.writerow(_stringify_row(row))
            return str(self._out_path)

        file_exists = self._out_path.exists()
        mode = "a" if (self._incremental and file_exists) else "w"
        with self._out_path.open(mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
            if mode == "w" or not file_exists:
                writer.writeheader()
            for row in to_write:
                writer.writerow(_stringify_row(row))

        return str(self._out_path)


def _stringify_row(row: dict[str, object]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in row.items():
        if key in {"social_links_json", "flags_json", "evidence_json"}:
            out[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif value is None:
            out[key] = ""
        else:
            out[key] = str(value)
    return out

