from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lead_scraper.export.schema import lead_to_export_dict
from lead_scraper.models import Lead


class SqliteExporter:
    def __init__(self, out_path: str):
        self._out_path = Path(out_path)

    def export(self, leads: list[Lead]) -> str:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._out_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    name TEXT,
                    category TEXT,
                    address TEXT,
                    phone TEXT,
                    website TEXT,
                    review_count INTEGER,
                    rating REAL,
                    maps_url TEXT,
                    social_links_json TEXT,
                    flags_json TEXT,
                    lead_score REAL,
                    qualified INTEGER,
                    qualification_reasons TEXT,
                    evidence_json TEXT,
                    exported_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(lead_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_qualified ON leads(qualified)")

            rows = [lead_to_export_dict(lead) for lead in leads]
            conn.executemany(
                """
                INSERT OR IGNORE INTO leads (
                    lead_id,
                    name,
                    category,
                    address,
                    phone,
                    website,
                    review_count,
                    rating,
                    maps_url,
                    social_links_json,
                    flags_json,
                    lead_score,
                    qualified,
                    qualification_reasons,
                    evidence_json,
                    exported_at
                ) VALUES (
                    :lead_id,
                    :name,
                    :category,
                    :address,
                    :phone,
                    :website,
                    :review_count,
                    :rating,
                    :maps_url,
                    :social_links_json,
                    :flags_json,
                    :lead_score,
                    :qualified,
                    :qualification_reasons,
                    :evidence_json,
                    :exported_at
                )
                """,
                [
                    {
                        **row,
                        "social_links_json": json.dumps(
                            row["social_links_json"], ensure_ascii=False, sort_keys=True
                        ),
                        "flags_json": json.dumps(row["flags_json"], ensure_ascii=False, sort_keys=True),
                        "evidence_json": json.dumps(row["evidence_json"], ensure_ascii=False),
                        "qualified": _to_int(row.get("qualified")),
                    }
                    for row in rows
                ],
            )
            conn.commit()
        finally:
            conn.close()
        return str(self._out_path)


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    if value is True:
        return 1
    if value is False:
        return 0
    return None

